import csv
import io
import re

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

from app.models import deadline_status


def search_records(records, q="", source="", year_from=None, year_to=None,
                   location="", deadline="all", sort="relevance"):
    results = []
    for item in records:
        if source and not any(s["source"] == source for s in item["sources"]):
            continue
        if year_from and (item.get("year") is None or item["year"] < year_from):
            continue
        if year_to and (item.get("year") is None or item["year"] > year_to):
            continue
        if location.casefold() not in item.get("location", "").casefold():
            continue
        item = dict(item, **deadline_status(item), score=0.0, matched_terms=[])
        if item["kind"] == "conference":
            if deadline == "open" and item["status"] not in {"open", "date_only", "due_today"}:
                continue
            if deadline == "unknown" and item["status"] != "unknown":
                continue
            if deadline == "expired" and item["status"] != "expired":
                continue
        results.append(item)
    if q.strip() and results:
        texts = [" ".join([r["title"], r["title"], r.get("abstract", ""), " ".join(r.get("topics", [])), r.get("note", ""), " ".join(r.get("authors", []))]) for r in results]
        tokens = set(re.findall(r"\w+", q.casefold()))
        try:
            vec = TfidfVectorizer(stop_words="english", sublinear_tf=True, strip_accents="unicode")
            matrix = vec.fit_transform(texts)
            scores = cosine_similarity(vec.transform([q]), matrix)[0]
        except ValueError:
            scores = [0.0] * len(results)
        for item, text, score in zip(results, texts, scores):
            terms = sorted(tokens & set(re.findall(r"\w+", text.casefold())))
            item.update(score=round(float(score), 4), matched_terms=terms)
        results = [r for r in results if r["score"] > 0 or r["matched_terms"]]
    if sort == "newest":
        results.sort(key=lambda r: (-(r.get("year") or 0), r["title"], r["id"]))
    elif sort == "deadline":
        results.sort(key=lambda r: (r["status"] == "expired", r.get("deadline_utc") or r.get("deadline_date") or "9999", r["id"]))
    else:
        results.sort(key=lambda r: (-r["score"], -(r.get("year") or 0), r["title"], r["id"]))
    return results


def export_csv(records):
    out = io.StringIO(newline="")
    writer = csv.writer(out)
    fields = ["id", "kind", "title", "authors", "year", "doi", "url", "sources", "location", "deadline_raw", "deadline_timezone", "status", "retrieved_at", "demo"]
    writer.writerow(fields)
    for item in records:
        cells = []
        for field in fields:
            value = item.get(field, "")
            if field == "sources":
                value = "; ".join(s["source"] + ": " + s["url"] for s in value)
            elif isinstance(value, list):
                value = "; ".join(value)
            value = str(value if value is not None else "")
            if value.lstrip().startswith(("=", "+", "-", "@")) or value.startswith(("\t", "\r", "\n")):
                value = "'" + value
            cells.append(value)
        writer.writerow(cells)
    return "\ufeff" + out.getvalue()
