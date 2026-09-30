import time

from fastapi.testclient import TestClient
import httpx
import pytest

from app.main import create_app
from app.models import Record
from app.sources import ProviderClient


class FakeProvider:
    def __init__(self):
        self.calls = []

    def fetch(self, source, query):
        self.calls.append(source)
        if source == "arxiv":
            raise httpx.ConnectError("offline")
        return [Record(kind="paper", title="Graph machine learning", source=source, external_id="one", year=2026)]

    def close(self):
        pass


@pytest.fixture
def client(tmp_path):
    provider = FakeProvider()
    app = create_app(tmp_path / "api.db", provider)
    with TestClient(app) as c:
        yield c, provider


def wait_job(client, job_id):
    for _ in range(200):
        job = client.get("/api/v1/jobs/" + job_id).json()
        if job["status"] not in {"queued", "running"}:
            return job
        time.sleep(.01)
    raise AssertionError("Job did not finish")


def test_partial_failure_and_cache(client):
    c, p = client
    response = c.post("/api/v1/refresh", json={"query":"graph", "sources":["crossref", "arxiv"]})
    assert response.status_code == 202
    job = wait_job(c, response.json()["id"])
    assert job["status"] == "partial"
    assert c.get("/api/v1/items?q=graph").json()["total"] == 1
    second = c.post("/api/v1/refresh", json={"query":"graph", "sources":["crossref"]}).json()
    assert wait_job(c, second["id"])["results"][0]["status"] == "cached"
    assert p.calls.count("crossref") == 1


def test_demo_bookmark_note_export_delete(client):
    c, _ = client
    assert c.get("/api/v1/health").json()["status"] == "ok"
    assert c.post("/api/v1/demo").status_code == 200
    data = c.get("/api/v1/items?mode=demo").json()
    assert data["total"] == 6
    record_id = data["items"][0]["id"]
    assert c.post("/api/v1/bookmarks", json={"item_id":record_id,"note":"For my report"}).status_code == 200
    assert c.get("/api/v1/items/" + record_id).json()["bookmark_note"] == "For my report"
    assert c.get("/api/v1/items?mode=demo&saved=true").json()["total"] == 1
    exported = c.get("/api/v1/export?mode=demo&saved=true")
    assert "attachment" in exported.headers["content-disposition"]
    assert data["items"][0]["title"] in exported.text
    assert c.get("/api/v1/items").json()["total"] == 0
    assert c.delete("/api/v1/bookmarks/" + record_id).status_code == 204
    assert c.delete("/api/v1/bookmarks/" + record_id).status_code == 404


@pytest.mark.parametrize("body", [{"query":" "},{"query":"!!"},{"query":"graph","sources":[]},{"query":"graph","sources":["unknown"]}])
def test_invalid_refresh(client, body):
    assert client[0].post("/api/v1/refresh", json=body).status_code == 422


def test_invalid_filters_and_missing_records(client):
    c, _ = client
    assert c.get("/api/v1/items?year_from=2027&year_to=2020").status_code == 422
    assert c.get("/api/v1/items?page_size=5000").status_code == 422
    assert c.get("/api/v1/items/missing").status_code == 404
    assert c.post("/api/v1/bookmarks", json={"item_id":"missing"}).status_code == 404
    assert c.get("/api/v1/jobs/missing").status_code == 404


def test_static_app_and_local_origin_protection(client):
    c, _ = client
    response = c.get("/")
    assert response.status_code == 200
    assert "Content-Security-Policy" in response.headers
    assert c.get("/static/app.js").status_code == 200
    assert c.post("/api/v1/demo", headers={"Origin":"https://evil.example"}).status_code == 403
    assert c.get("/api/v1/health", headers={"Host":"evil.example"}).status_code == 400


def test_provider_retries_and_allowlist(monkeypatch):
    monkeypatch.setattr("app.sources.time.sleep", lambda _: None)
    calls = []
    def handler(request):
        calls.append(request)
        return httpx.Response(429, headers={"Retry-After":"0"}) if len(calls) < 3 else httpx.Response(200, json={"message":{"items":[]}})
    provider = ProviderClient(client=httpx.Client(transport=httpx.MockTransport(handler)))
    assert provider.fetch("crossref", "graph") == []
    assert len(calls) == 3
    with pytest.raises(ValueError):
        provider.request("crossref", "http://127.0.0.1/private")
    provider.close()


def test_robots_disallow_blocks_scrape(monkeypatch):
    monkeypatch.setattr("app.sources.time.sleep", lambda _: None)
    calls = []
    def handler(request):
        calls.append(str(request.url))
        return httpx.Response(200, text="User-agent: *\nDisallow: /")
    provider = ProviderClient(client=httpx.Client(transport=httpx.MockTransport(handler)))
    with pytest.raises(ValueError, match="disallows"):
        provider.fetch("mldeadlines", "graph")
    assert len(calls) == 1
    provider.close()
