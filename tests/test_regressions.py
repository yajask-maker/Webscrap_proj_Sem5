"""Regressions found during the implementation and usage audit."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
import csv
import gzip
import io
import threading

from fastapi.testclient import TestClient
import httpx
import pytest

from app.db import Database
from app.main import create_app
from app.models import Record
from app.service import RefreshService
from app.sources import ProviderClient
from test_api import FakeProvider, wait_job


@pytest.mark.parametrize('error', [httpx.ConnectError, httpx.ReadTimeout, httpx.RemoteProtocolError])
def test_transient_network_failure_recovers(monkeypatch, error):
    monkeypatch.setattr('app.sources.time.sleep', lambda _: None)
    calls = []
    def handler(request):
        calls.append(request)
        if len(calls) < 3:
            raise error('temporary failure', request=request)
        return httpx.Response(200, json={'message': {'items': []}})
    p = ProviderClient(client=httpx.Client(transport=httpx.MockTransport(handler)))
    try:
        assert p.fetch('crossref', 'graph') == []
        assert len(calls) == 3
    finally:
        p.close()


def test_network_retry_is_bounded_and_throttled(monkeypatch):
    clock = [100.0]
    monkeypatch.setattr('app.sources.time.monotonic', lambda: clock[0])
    monkeypatch.setattr('app.sources.time.sleep', lambda seconds: clock.__setitem__(0, clock[0] + seconds))
    attempts = []
    def handler(request):
        attempts.append(clock[0])
        raise httpx.ReadTimeout('offline', request=request)
    p = ProviderClient(client=httpx.Client(transport=httpx.MockTransport(handler)))
    try:
        with pytest.raises(httpx.ReadTimeout):
            p.fetch('arxiv', 'graph')
        assert len(attempts) == 3
        assert all(b-a >= 3.1-1e-9 for a,b in zip(attempts, attempts[1:]))
    finally:
        p.close()


def test_size_limit_stops_stream_early():
    chunks = []
    class Stream(httpx.SyncByteStream):
        def __iter__(self):
            for i in range(10):
                chunks.append(i)
                yield b'x' * 1_000_000
    p = ProviderClient(client=httpx.Client(transport=httpx.MockTransport(
        lambda request: httpx.Response(200, stream=Stream()))))
    try:
        with pytest.raises(ValueError, match='size limit'):
            p.fetch('crossref', 'graph')
        assert len(chunks) == 5
    finally:
        p.close()


def test_compressed_response_is_decoded_once():
    content = gzip.compress(b'{"message":{"items":[]}}')
    p = ProviderClient(client=httpx.Client(transport=httpx.MockTransport(
        lambda request: httpx.Response(200, content=content, headers={'Content-Encoding': 'gzip'}))))
    try:
        assert p.fetch('crossref', 'graph') == []
    finally:
        p.close()


@pytest.mark.parametrize('status,headers', [(400, {}), (403, {}), (429, {'Retry-After': '120'})])
def test_permanent_failure_or_long_retry_does_not_hammer_provider(status, headers):
    calls = []
    def handler(request):
        calls.append(request)
        return httpx.Response(status, headers=headers)
    p = ProviderClient(client=httpx.Client(transport=httpx.MockTransport(handler)))
    try:
        with pytest.raises((httpx.HTTPStatusError, ValueError)):
            p.fetch('crossref', 'graph')
        assert len(calls) == 1
    finally:
        p.close()


def test_bookmark_without_note_preserves_existing_note_and_csv(tmp_path):
    with TestClient(create_app(tmp_path/'notes.db', FakeProvider())) as c:
        c.post('/api/v1/demo')
        record_id = c.get('/api/v1/items?mode=demo').json()['items'][0]['id']
        note = '=SUM(1,2)\nGarcía — useful'
        c.post('/api/v1/bookmarks', json={'item_id': record_id, 'note': note})
        c.post('/api/v1/bookmarks', json={'item_id': record_id})
        assert c.get('/api/v1/items/'+record_id).json()['bookmark_note'] == note
        rows = list(csv.DictReader(io.StringIO(c.get('/api/v1/export?mode=demo&saved=true').text.lstrip('\ufeff'))))
        assert len(rows) == 1
        assert rows[0]['bookmark_note'] == "'" + note
        c.post('/api/v1/bookmarks', json={'item_id': record_id, 'note': ''})
        assert c.get('/api/v1/items/'+record_id).json()['bookmark_note'] == ''


def test_timeout_partial_failure_and_retry_preserves_success(tmp_path):
    class Provider(FakeProvider):
        def fetch(self, source, query):
            if source == 'arxiv':
                self.calls.append(source)
                raise httpx.ReadTimeout('offline')
            return super().fetch(source, query)
    provider = Provider()
    with TestClient(create_app(tmp_path/'timeout.db', provider)) as c:
        for _ in range(2):
            response = c.post('/api/v1/refresh', json={'query': 'graph', 'sources': ['crossref','arxiv']})
            assert response.json()['status'] == 'queued'
            job = wait_job(c, response.json()['id'])
            assert job['status'] == 'partial'
            assert 'timed out' in job['results'][1]['error']
            assert c.get('/api/v1/items?q=graph').json()['total'] == 1
        assert provider.calls.count('crossref') == 1
        assert provider.calls.count('arxiv') == 2


def test_refresh_rejects_overlap_then_releases_lock(tmp_path):
    entered, release = threading.Event(), threading.Event()
    class SlowProvider(FakeProvider):
        def fetch(self, source, query):
            entered.set()
            assert release.wait(5)
            return super().fetch(source, query)
    with TestClient(create_app(tmp_path/'overlap.db', SlowProvider())) as c:
        try:
            first = c.post('/api/v1/refresh', json={'query': 'graph', 'sources':['crossref']})
            assert entered.wait(2)
            assert c.post('/api/v1/refresh', json={'query':'other'}).status_code == 409
        finally:
            release.set()
        assert wait_job(c, first.json()['id'])['status'] == 'completed'
        second = c.post('/api/v1/refresh', json={'query':'graph','sources':['crossref']})
        assert wait_job(c, second.json()['id'])['status'] == 'completed'


def test_refresh_lock_released_even_when_job_storage_fails(tmp_path):
    db = Database(tmp_path/'broken.db')
    service = RefreshService(db, FakeProvider())
    service.guard.acquire()
    def fail(job):
        raise OSError('disk unavailable')
    db.save_job = fail
    try:
        with pytest.raises(OSError):
            service.run({'id':'x','status':'queued','sources':['crossref'],'query':'graph','results':[]})
        assert service.guard.acquire(blocking=False)
        service.guard.release()
    finally:
        service.close()


def test_failed_run_is_not_reported_as_fresh_cache(tmp_path):
    db = Database(tmp_path/'cache.db')
    db.save_run('crossref:graph', {'source':'crossref','status':'error','count':0,
        'last_success_at':datetime.now(timezone.utc).isoformat(), 'attempted_at':datetime.now(timezone.utc).isoformat(), 'error':'failed'})
    provider = FakeProvider()
    service = RefreshService(db, provider)
    service.guard.acquire()
    try:
        service.run({'id':'x','status':'queued','query':'graph','sources':['crossref'],'results':[]})
        assert db.get_job('x')['results'][0]['status'] == 'ok'
        assert provider.calls == ['crossref']
    finally:
        service.close()


def test_database_default_is_independent_of_launch_directory(tmp_path, monkeypatch):
    import app.main as main
    project = tmp_path/'project'
    project.mkdir()
    elsewhere = tmp_path/'elsewhere'
    elsewhere.mkdir()
    monkeypatch.setattr(main, 'PROJECT_ROOT', project)
    monkeypatch.delenv('EUREKA_DB', raising=False)
    monkeypatch.chdir(elsewhere)
    with TestClient(create_app(provider=FakeProvider())) as c:
        assert c.get('/api/v1/health').status_code == 200
    assert (project/'data/eureka.db').exists()
    assert not (elsewhere/'data').exists()


def test_invalid_origin_and_export_filters(tmp_path):
    with TestClient(create_app(tmp_path/'validation.db', FakeProvider())) as c:
        assert c.post('/api/v1/demo', headers={'Origin':'http://['}).status_code == 403
        assert c.post('/api/v1/demo', headers={'Origin':'https://testserver'}).status_code == 403
        assert c.post('/api/v1/demo', headers={'Origin':'http://testserver'}).status_code == 200
        assert c.get('/api/v1/export?source=unknown').status_code == 422
        assert c.get('/api/v1/export?year_from=2027&year_to=2020').status_code == 422


def test_filter_pagination_export_and_restart(tmp_path):
    path = tmp_path/'paging.db'
    with TestClient(create_app(path, FakeProvider())) as c:
        for i in range(25):
            c.app.state.db.upsert(Record(kind='paper', source='crossref', external_id=str(i), title=f'Graph paper {i:02}', year=2026 if i<13 else 2020))
        first = c.get('/api/v1/items?year_from=2026&page=1').json()
        second = c.get('/api/v1/items?year_from=2026&page=2').json()
        assert first['total'] == second['total'] == 13
        assert len(first['items']) == 12 and len(second['items']) == 1
        assert not {r['id'] for r in first['items']} & {r['id'] for r in second['items']}
        exported = list(csv.DictReader(io.StringIO(c.get('/api/v1/export?year_from=2026').text.lstrip('\ufeff'))))
        assert len(exported) == 13
        record_id = first['items'][0]['id']
        c.post('/api/v1/bookmarks', json={'item_id':record_id, 'note':'Persisted'})
    with TestClient(create_app(path, FakeProvider())) as c:
        assert c.get('/api/v1/items?saved=true').json()['items'][0]['bookmark_note'] == 'Persisted'
        assert c.get('/api/v1/items').json()['total'] == 25


def test_crossref_null_optional_fields():
    from app.sources import crossref_records
    records = crossref_records({'message':{'items':[None, {'DOI':'10.1234/nullable', 'title':['Example'], 'author':None, 'published':None}]}})
    assert len(records) == 1
    assert records[0].authors == [] and records[0].year is None
    with pytest.raises(ValueError, match='schema changed'):
        crossref_records([])


def test_source_health_remembers_success_for_another_query(tmp_path):
    db = Database(tmp_path/'health.db')
    stamp = datetime.now(timezone.utc).isoformat()
    db.save_run('arxiv:first', {'source':'arxiv', 'status':'ok','attempted_at':stamp,'last_success_at':stamp,'count':30})
    later = (datetime.now(timezone.utc)+timedelta(seconds=1)).isoformat()
    db.save_run('arxiv:other', {'source':'arxiv', 'status':'error','attempted_at':later,'last_success_at':None,'count':0})
    status = db.source_status()['arxiv']
    assert status['status'] == 'error'
    assert status['last_success_at'] == stamp


def test_concurrent_identifier_merge_is_atomic(tmp_path):
    db = Database(tmp_path/'concurrent.db')
    records = [Record(kind='paper', source=source, external_id=source, title='Same paper', doi='10.1234/shared') for source in ['crossref','arxiv']]
    with ThreadPoolExecutor(max_workers=2) as pool:
        ids = list(pool.map(db.upsert, records))
    assert ids[0] == ids[1]
    assert len(db.items()) == 1
    assert len(db.items()[0]['sources']) == 2
