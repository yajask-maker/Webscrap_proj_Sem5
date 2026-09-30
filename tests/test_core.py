from datetime import datetime, timezone
from pathlib import Path
import csv
import io

import pytest

from app.db import Database
from app.models import Record, deadline_status, normalize_doi, parse_deadline, safe_url
from app.search import export_csv, search_records
from app.sources import arxiv_records, conference_records, crossref_records

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def db(tmp_path):
    return Database(tmp_path / "test.db")


def paper(source="crossref", external_id="x", **kwargs):
    return Record(kind="paper", source=source, external_id=external_id, title="Graph machine learning", **kwargs)


def test_crossref_missing_fields_and_markup():
    records = crossref_records({"message": {"items": [{"DOI":"10.1234/EXAMPLE", "title":["A <i>graph</i> study"], "abstract":"<p>Text</p>"}, {"title": ["No ID"]}]}})
    assert len(records) == 1
    assert records[0].title == "A graph study"
    assert records[0].doi == "10.1234/example"
    assert records[0].year is None
    assert records[0].authors == []


def test_arxiv_atom_and_versions():
    record = arxiv_records((FIXTURES / "arxiv.xml").read_text())[0]
    assert record.arxiv_id == "2601.00001"
    assert record.source_url.endswith("v2")
    assert record.year == 2026
    assert record.doi == "10.1234/example"
    with pytest.raises(ValueError):
        arxiv_records("<html>error</html>")


def test_conference_parser_and_drift():
    records = conference_records((FIXTURES / "conferences.html").read_text())
    assert records[0].deadline_utc == "2027-02-01T11:59:59+00:00"
    assert records[0].location == "Mumbai, India"
    assert records[1].deadline_precision == "unknown"
    with pytest.raises(ValueError):
        conference_records("<html>blocked</html>")


def test_assumed_timezone_is_not_an_exact_deadline():
    html = (FIXTURES / "conferences.html").read_text().replace("Synthetic fixture only.", "CET assumed; no timezone stated.")
    result = conference_records(html)[0]
    assert result.deadline_precision == "date"
    assert result.deadline_utc is None


@pytest.mark.parametrize("raw,zone,expected", [
    ("2026-10-01 23:59:59", "AoE", "2026-10-02T11:59:59+00:00"),
    ("2026-10-01 23:59:59", "UTC-12", "2026-10-02T11:59:59+00:00"),
    ("2026-10-01 23:59:59", "Asia/Kolkata", "2026-10-01T18:29:59+00:00"),
    ("2026-10-01", "UTC", None), ("TBA", "", None),
    ("2026-02-30", "UTC", None), ("2026-10-01 12:00:00", "", None),
])
def test_deadline_precision(raw, zone, expected):
    assert parse_deadline(raw, zone)["deadline_utc"] == expected


def test_deadline_states():
    now = datetime(2026, 10, 1, 12, tzinfo=timezone.utc)
    assert deadline_status(parse_deadline("2026-10-01"), now)["status"] == "due_today"
    assert deadline_status(parse_deadline("2026-09-30"), now)["status"] == "expired"
    assert deadline_status(parse_deadline("2026-10-02"), now)["status"] == "date_only"
    assert deadline_status(parse_deadline("2026-10-01T11:00:00Z"), now)["status"] == "expired"


def test_idempotence_and_cross_source_merge(db):
    first = db.upsert(paper(doi="10.1234/example", abstract="Keep me"))
    second = db.upsert(paper("arxiv", "2601.00001", doi="10.1234/example", arxiv_id="2601.00001"))
    assert first == second
    assert len(db.items()) == 1
    assert len(db.items()[0]["sources"]) == 2
    assert db.items()[0]["abstract"] == "Keep me"
    db.upsert(paper("arxiv", "2601.00001", doi="10.1234/example", arxiv_id="2601.00001"))
    assert len(db.get_item(first)["history"]) == 2


def test_late_identifier_bridge_preserves_bookmark(db):
    first = db.upsert(paper(doi="10.1234/example"))
    second = db.upsert(paper("arxiv", "2601.00001", arxiv_id="2601.00001"))
    db.bookmark(second, "useful")
    canonical = db.upsert(paper("arxiv", "2601.00001", arxiv_id="2601.00001", doi="10.1234/example"))
    assert len(db.items()) == 1
    assert db.get_item(canonical)["bookmark_note"] == "useful"
    assert db.items(saved=True)[0]["id"] == canonical


def test_similar_titles_and_different_editions_stay_separate(db):
    db.upsert(paper(external_id="one"))
    db.upsert(paper(external_id="two"))
    for edition in ["2026", "2027"]:
        db.upsert(Record(kind="conference", source="test", external_id=edition, title="Same Conference"))
    assert len(db.items()) == 4


def test_merging_two_bookmarks_preserves_both_notes(db):
    first = db.upsert(paper(doi="10.1234/example"))
    second = db.upsert(paper("arxiv", "2601.00001", arxiv_id="2601.00001"))
    db.bookmark(first, "First note")
    db.bookmark(second, "Second note")
    item_id = db.upsert(paper("arxiv", "2601.00001", doi="10.1234/example", arxiv_id="2601.00001"))
    note = db.get_item(item_id)["bookmark_note"]
    assert "First note" in note and "Second note" in note


def test_deadline_change_to_unknown_removes_old_countdown(db):
    record = Record(kind="conference", source="test", external_id="conf", title="Example", **parse_deadline("2027-01-01T00:00:00Z"))
    item_id = db.upsert(record)
    db.upsert(record.model_copy(update=parse_deadline("TBA")))
    assert db.get_item(item_id)["deadline_utc"] is None
    assert len(db.get_item(item_id)["history"]) == 2


def test_demo_isolation_and_restart(db):
    from app.demo import seed_demo
    seed_demo(db)
    assert len(db.items(demo=True)) == 11
    seed_demo(db)
    assert len(db.items(demo=True)) == 11
    item_id = db.items(demo=True)[0]["id"]
    db.bookmark(item_id, "Note")
    reopened = Database(db.path)
    assert reopened.items() == []
    assert reopened.get_item(item_id)["bookmark_note"] == "Note"


def test_rank_filter_and_unknown_year(db):
    db.upsert(paper(year=2026, abstract="Graph learning for molecules"))
    db.upsert(Record(kind="paper", external_id="two", source="test", title="Robot control", year=2025))
    db.upsert(Record(kind="paper", external_id="three", source="test", title="Graph study"))
    result = search_records(db.items(), "graph", year_from=2026)
    assert len(result) == 1
    assert result[0]["score"] > 0
    assert result[0]["matched_terms"] == ["graph"]
    assert search_records(db.items(), "nonexistentkeyword") == []


def test_safe_csv_and_urls(db):
    item_id = db.upsert(Record(kind="paper", external_id="csv", source="test", title='=HYPERLINK("bad")', authors=["Unicode García"]))
    text = export_csv(db.items())
    rows = list(csv.reader(io.StringIO(text.lstrip("\ufeff"))))
    assert rows[1][2].startswith("'=")
    assert rows[1][3] == "Unicode García"
    assert safe_url("javascript:alert(1)") == ""
    assert safe_url("https://example.org/") == "https://example.org/"
    assert normalize_doi("https://doi.org/10.1234/ABC") == "10.1234/abc"
