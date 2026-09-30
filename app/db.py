from contextlib import contextmanager
import json
from pathlib import Path
import sqlite3

from app.models import now_iso, stable_id


class Database:
    def __init__(self, path):
        self.path = str(path)
        Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            db.executescript("""
                PRAGMA journal_mode=WAL;
                CREATE TABLE IF NOT EXISTS items (
                    id TEXT PRIMARY KEY, kind TEXT NOT NULL, demo INTEGER NOT NULL, data TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS aliases (
                    alias TEXT PRIMARY KEY, item_id TEXT NOT NULL REFERENCES items(id));
                CREATE TABLE IF NOT EXISTS bookmarks (
                    item_id TEXT PRIMARY KEY REFERENCES items(id), note TEXT NOT NULL DEFAULT '', saved_at TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS observations (
                    id TEXT PRIMARY KEY, item_id TEXT NOT NULL REFERENCES items(id), data TEXT NOT NULL, observed_at TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS source_runs (
                    cache_key TEXT PRIMARY KEY, source TEXT NOT NULL, data TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS jobs (id TEXT PRIMARY KEY, data TEXT NOT NULL);
                CREATE INDEX IF NOT EXISTS items_kind ON items(kind, demo);
                PRAGMA user_version=1;
            """)
            for row in db.execute("SELECT id, data FROM jobs").fetchall():
                data = json.loads(row["data"])
                if data["status"] in {"queued", "running"}:
                    data.update(status="failed", error="Server restarted. Please retry.", finished_at=now_iso())
                    db.execute("UPDATE jobs SET data=? WHERE id=?", (json.dumps(data), row["id"]))

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=15)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys=ON")
        try:
            with db:
                yield db
        finally:
            db.close()

    def upsert(self, record):
        data = record.model_dump()
        namespace = "demo:" if data["demo"] else "live:"
        keys = [namespace + data["source"] + ":" + data["external_id"]]
        if data["kind"] == "paper":
            if data["doi"]:
                keys.append(namespace + "doi:" + data["doi"])
            if data["arxiv_id"]:
                keys.append(namespace + "arxiv:" + data["arxiv_id"])
        with self.connect() as db:
            ids = sorted({row[0] for key in keys for row in db.execute("SELECT item_id FROM aliases WHERE alias=?", (key,))})
            item_id = ids[0] if ids else stable_id(keys[0])
            merged = {}
            sources = {}
            for old_id in ids:
                old = json.loads(db.execute("SELECT data FROM items WHERE id=?", (old_id,)).fetchone()[0])
                merged.update({k: v for k, v in old.items() if v not in (None, "", [])})
                for source in old.get("sources", []):
                    sources[(source["source"], source["external_id"])] = source
            merged.update({k: v for k, v in data.items() if v not in (None, "", [])})
            if data["kind"] == "conference":
                for key in ("deadline_raw", "deadline_timezone", "deadline_utc", "deadline_date", "deadline_precision"):
                    merged[key] = data[key]
            for k, v in data.items():
                merged.setdefault(k, v)
            sources[(data["source"], data["external_id"])] = {
                "source": data["source"], "external_id": data["external_id"],
                "url": data["source_url"] or data["url"], "retrieved_at": data["retrieved_at"]}
            merged.update(id=item_id, sources=list(sources.values()))
            db.execute("INSERT INTO items VALUES(?,?,?,?) ON CONFLICT(id) DO UPDATE SET data=excluded.data",
                       (item_id, data["kind"], int(data["demo"]), json.dumps(merged)))
            for old_id in ids[1:]:
                old_bookmark = db.execute("SELECT note FROM bookmarks WHERE item_id=?", (old_id,)).fetchone()
                current_bookmark = db.execute("SELECT note FROM bookmarks WHERE item_id=?", (item_id,)).fetchone()
                if old_bookmark and current_bookmark and old_bookmark[0] and old_bookmark[0] != current_bookmark[0]:
                    notes = "\n\n".join(filter(None, [current_bookmark[0], old_bookmark[0]]))
                    db.execute("UPDATE bookmarks SET note=? WHERE item_id=?", (notes, item_id))
                db.execute("INSERT OR IGNORE INTO bookmarks SELECT ?,note,saved_at FROM bookmarks WHERE item_id=?", (item_id, old_id))
                db.execute("DELETE FROM bookmarks WHERE item_id=?", (old_id,))
                db.execute("UPDATE aliases SET item_id=? WHERE item_id=?", (item_id, old_id))
                db.execute("UPDATE observations SET item_id=? WHERE item_id=?", (item_id, old_id))
                db.execute("DELETE FROM items WHERE id=?", (old_id,))
            for key in keys:
                db.execute("INSERT INTO aliases VALUES(?,?) ON CONFLICT(alias) DO UPDATE SET item_id=excluded.item_id", (key, item_id))
            observation = {k: v for k, v in data.items() if k != "retrieved_at"}
            digest = stable_id(namespace + json.dumps(observation, sort_keys=True))
            db.execute("INSERT OR IGNORE INTO observations VALUES(?,?,?,?)", (digest, item_id, json.dumps(observation), data["retrieved_at"]))
        return item_id

    def items(self, kind=None, demo=False, saved=False):
        sql = "SELECT i.data,b.note,b.saved_at FROM items i LEFT JOIN bookmarks b ON i.id=b.item_id WHERE i.demo=?"
        args = [int(demo)]
        if kind:
            sql += " AND i.kind=?"
            args.append(kind)
        if saved:
            sql += " AND b.item_id IS NOT NULL"
        with self.connect() as db:
            rows = db.execute(sql, args).fetchall()
        return [dict(json.loads(r["data"]), saved=r["saved_at"] is not None, bookmark_note=r["note"] or "") for r in rows]

    def get_item(self, item_id):
        with self.connect() as db:
            row = db.execute("SELECT data FROM items WHERE id=?", (item_id,)).fetchone()
            if not row:
                return None
            data = json.loads(row[0])
            bookmark = db.execute("SELECT note FROM bookmarks WHERE item_id=?", (item_id,)).fetchone()
            data["saved"] = bookmark is not None
            data["bookmark_note"] = bookmark[0] if bookmark else ""
            data["history"] = [dict(json.loads(r[0]), observed_at=r[1]) for r in db.execute(
                "SELECT data,observed_at FROM observations WHERE item_id=? ORDER BY observed_at DESC LIMIT 20", (item_id,))]
            return data

    def bookmark(self, item_id, note=""):
        with self.connect() as db:
            if not db.execute("SELECT 1 FROM items WHERE id=?", (item_id,)).fetchone():
                return False
            db.execute("INSERT INTO bookmarks VALUES(?,?,?) ON CONFLICT(item_id) DO UPDATE SET note=excluded.note", (item_id, note, now_iso()))
        return True

    def unbookmark(self, item_id):
        with self.connect() as db:
            return db.execute("DELETE FROM bookmarks WHERE item_id=?", (item_id,)).rowcount > 0

    def save_run(self, key, data):
        with self.connect() as db:
            db.execute("INSERT INTO source_runs VALUES(?,?,?) ON CONFLICT(cache_key) DO UPDATE SET data=excluded.data",
                       (key, data["source"], json.dumps(data)))

    def get_run(self, key):
        with self.connect() as db:
            row = db.execute("SELECT data FROM source_runs WHERE cache_key=?", (key,)).fetchone()
        return json.loads(row[0]) if row else None

    def source_status(self):
        with self.connect() as db:
            rows = db.execute("SELECT data FROM source_runs").fetchall()
        latest = {}
        for row in rows:
            data = json.loads(row[0])
            if data["attempted_at"] >= latest.get(data["source"], {}).get("attempted_at", ""):
                latest[data["source"]] = data
        return latest

    def save_job(self, job):
        with self.connect() as db:
            db.execute("INSERT INTO jobs VALUES(?,?) ON CONFLICT(id) DO UPDATE SET data=excluded.data", (job["id"], json.dumps(job)))

    def get_job(self, job_id):
        with self.connect() as db:
            row = db.execute("SELECT data FROM jobs WHERE id=?", (job_id,)).fetchone()
        return json.loads(row[0]) if row else None
