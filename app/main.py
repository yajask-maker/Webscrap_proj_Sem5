from contextlib import asynccontextmanager
from datetime import datetime, timezone
import os
from pathlib import Path
from typing import Literal
from urllib.parse import urlsplit

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Query, Request, Response
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, field_validator
from starlette.middleware.trustedhost import TrustedHostMiddleware

from app.db import Database
from app.demo import seed_demo
from app.models import deadline_status
from app.search import export_csv, search_records
from app.service import RefreshService
from app.sources import ProviderClient

ROOT = Path(__file__).resolve().parent
PROJECT_ROOT = ROOT.parent


class RefreshBody(BaseModel):
    query: str = Field(min_length=2, max_length=200)
    sources: list[Literal["crossref", "arxiv", "mldeadlines"]] = Field(default_factory=lambda: ["crossref", "arxiv", "mldeadlines"], min_length=1, max_length=3)

    @field_validator("query")
    @classmethod
    def clean_query(cls, value):
        value = " ".join(value.split())
        if len(value) < 2 or not any(c.isalnum() for c in value):
            raise ValueError("Enter at least two characters and a letter or number")
        return value


class BookmarkBody(BaseModel):
    item_id: str = Field(min_length=1, max_length=64)
    note: str | None = Field(default=None, max_length=1000)


def create_app(db_path=None, provider=None):
    load_dotenv(PROJECT_ROOT / ".env")

    @asynccontextmanager
    async def lifespan(api):
        path = Path(db_path or os.getenv("EUREKA_DB", "data/eureka.db"))
        api.state.db = Database(path if path.is_absolute() else PROJECT_ROOT / path)
        api.state.service = RefreshService(api.state.db, provider or ProviderClient(os.getenv("EUREKA_CONTACT_EMAIL", "")))
        yield
        api.state.service.close()

    api = FastAPI(title="Eureka API", version="1.0.0", lifespan=lifespan,
                  description="Local research paper and conference discovery. Interactive documentation at /docs.")
    api.add_middleware(TrustedHostMiddleware, allowed_hosts=["127.0.0.1", "localhost", "testserver", "[::1]"])

    @api.middleware("http")
    async def local_security(request: Request, call_next):
        if request.method in {"POST", "PUT", "PATCH", "DELETE"}:
            origin = request.headers.get("origin")
            try:
                invalid_origin = origin and (urlsplit(origin).netloc != request.headers.get("host") or urlsplit(origin).scheme != request.url.scheme)
            except ValueError:
                invalid_origin = True
            if request.headers.get("sec-fetch-site") == "cross-site" or invalid_origin:
                return JSONResponse({"detail": "Cross-origin writes are not allowed"}, status_code=403)
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        if request.url.path == "/":
            response.headers["Content-Security-Policy"] = "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'self'"
        return response

    def db():
        return api.state.db

    @api.get("/api/v1/health")
    def health():
        with db().connect() as conn:
            conn.execute("SELECT 1")
        return {"status": "ok", "version": "1.0.0", "mode": "local workspace"}

    @api.get("/api/v1/items")
    def items(kind: Literal["paper", "conference", "all"] = "paper", q: str = Query("", max_length=200),
              mode: Literal["live", "demo"] = "live", saved: bool = False,
              source: Literal["", "crossref", "arxiv", "mldeadlines", "demo"] = "",
              year_from: int | None = Query(None, ge=1900, le=2100), year_to: int | None = Query(None, ge=1900, le=2100),
              location: str = Query("", max_length=120), deadline: Literal["all", "open", "expired", "unknown"] = "all",
              sort: Literal["relevance", "newest", "deadline"] = "relevance",
              page: int = Query(1, ge=1), page_size: int = Query(12, ge=1, le=100)):
        if year_from and year_to and year_from > year_to:
            raise HTTPException(422, "Start year must not exceed end year")
        records = search_records(db().items(None if kind == "all" else kind, mode == "demo", saved),
                                 q, source, year_from, year_to, location, deadline, sort)
        return {"items": records[(page-1)*page_size:page*page_size], "total": len(records), "page": page,
                "page_size": page_size, "source_status": api.state.service.sources(), "mode": mode}

    @api.get("/api/v1/items/{item_id}")
    def detail(item_id: str):
        record = db().get_item(item_id)
        if not record:
            raise HTTPException(404, "Record not found")
        return dict(record, **deadline_status(record))

    @api.post("/api/v1/refresh", status_code=202)
    def refresh(body: RefreshBody):
        try:
            return api.state.service.start(body.query, list(dict.fromkeys(body.sources)))
        except RuntimeError as exc:
            raise HTTPException(409, str(exc)) from exc

    @api.get("/api/v1/jobs/{job_id}")
    def job(job_id: str):
        result = db().get_job(job_id)
        if not result:
            raise HTTPException(404, "Job not found")
        return result

    @api.get("/api/v1/sources")
    def sources():
        return {"items": api.state.service.sources()}

    @api.post("/api/v1/demo")
    def demo():
        seed_demo(db())
        return {"status": "ready", "notice": "Synthetic examples. No real papers or conferences are claimed."}

    @api.post("/api/v1/bookmarks")
    def bookmark(body: BookmarkBody):
        if not db().bookmark(body.item_id, body.note):
            raise HTTPException(404, "Record not found")
        return {"status": "saved"}

    @api.delete("/api/v1/bookmarks/{item_id}", status_code=204)
    def unbookmark(item_id: str):
        if not db().unbookmark(item_id):
            raise HTTPException(404, "Bookmark not found")
        return Response(status_code=204)

    @api.get("/api/v1/export")
    def export(kind: Literal["paper", "conference", "all"] = "all", mode: Literal["live", "demo"] = "live",
               saved: bool = False, q: str = Query("", max_length=200),
               source: Literal["", "crossref", "arxiv", "mldeadlines", "demo"] = "",
               year_from: int | None = Query(None, ge=1900, le=2100), year_to: int | None = Query(None, ge=1900, le=2100),
               location: str = Query("", max_length=120), deadline: Literal["all", "open", "expired", "unknown"] = "all",
               sort: Literal["relevance", "newest", "deadline"] = "relevance"):
        if year_from and year_to and year_from > year_to:
            raise HTTPException(422, "Start year must not exceed end year")
        records = search_records(db().items(None if kind == "all" else kind, mode == "demo", saved),
                                 q, source, year_from, year_to, location, deadline, sort)[:5000]
        return Response(export_csv(records), media_type="text/csv; charset=utf-8",
                        headers={"Content-Disposition": 'attachment; filename="eureka-' + mode + '.csv"'})

    @api.get("/api/v1/dashboard")
    def dashboard(mode: Literal["live", "demo"] = "live"):
        records = db().items(demo=mode == "demo")
        conferences = [dict(r, **deadline_status(r)) for r in records if r["kind"] == "conference"]
        upcoming = [r for r in conferences if r["status"] in {"open", "date_only", "due_today"}]
        upcoming.sort(key=lambda r: r.get("deadline_utc") or r.get("deadline_date") or "9999")
        return {"papers": sum(r["kind"] == "paper" for r in records), "conferences": len(conferences),
                "saved": sum(r["saved"] for r in records), "open_deadlines": len(upcoming),
                "upcoming": upcoming[:8], "saved_upcoming": [r for r in upcoming if r["saved"]][:8],
                "sources": api.state.service.sources(), "mode": mode, "as_of": datetime.now(timezone.utc).isoformat()}

    api.mount("/static", StaticFiles(directory=ROOT / "static"), name="static")

    @api.get("/", include_in_schema=False)
    def home():
        return FileResponse(ROOT / "static" / "index.html")

    return api


app = create_app()
