from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import threading
import uuid

import httpx

from app.models import now_iso
from app.sources import SOURCE_INFO


class RefreshService:
    def __init__(self, db, providers):
        self.db = db
        self.providers = providers
        self.pool = ThreadPoolExecutor(max_workers=1)
        self.guard = threading.Lock()

    def start(self, query, sources):
        if not self.guard.acquire(blocking=False):
            raise RuntimeError("A refresh is already running. Wait for it to finish.")
        job = {"id": uuid.uuid4().hex, "status": "queued", "query": query,
               "sources": sources, "results": [], "started_at": now_iso()}
        try:
            self.db.save_job(job)
            self.pool.submit(self.run, job)
        except Exception:
            self.guard.release()
            raise
        return job

    def run(self, job):
        job["status"] = "running"
        self.db.save_job(job)
        try:
            for source in job["sources"]:
                key = source + ":" + ("all" if source == "mldeadlines" else " ".join(job["query"].lower().split()))
                previous = self.db.get_run(key) or {}
                success_at = previous.get("last_success_at")
                age = (datetime.now(timezone.utc) - datetime.fromisoformat(success_at)).total_seconds() if success_at else float("inf")
                if age < 86400:
                    result = dict(previous, status="cached", attempted_at=now_iso(), error="")
                else:
                    result = {"source": source, "status": "ok", "count": 0, "attempted_at": now_iso(),
                              "last_success_at": success_at, "error": ""}
                    try:
                        records = self.providers.fetch(source, job["query"])
                        for record in records:
                            self.db.upsert(record)
                        result.update(count=len(records), last_success_at=now_iso())
                    except httpx.HTTPStatusError as exc:
                        result.update(status="error", error=f"Provider returned HTTP {exc.response.status_code}. Cached records remain available.")
                    except httpx.RequestError:
                        result.update(status="error", error="Connection failed or timed out. Cached records remain available.")
                    except (ValueError, KeyError, TypeError) as exc:
                        result.update(status="error", error=str(exc)[:180])
                self.db.save_run(key, result)
                job["results"].append(result)
                self.db.save_job(job)
            failures = sum(r["status"] == "error" for r in job["results"])
            job["status"] = "failed" if failures == len(job["sources"]) else "partial" if failures else "completed"
        except Exception:
            job.update(status="failed", error="Refresh interrupted by an internal error. Existing records are safe.")
        finally:
            job["finished_at"] = now_iso()
            self.db.save_job(job)
            self.guard.release()

    def sources(self):
        status = self.db.source_status()
        return [dict(info, id=key, **status.get(key, {"status": "not_fetched", "count": 0})) for key, info in SOURCE_INFO.items()]

    def close(self):
        self.pool.shutdown(wait=True)
        self.providers.close()
