"""Synthetic data, intentionally separated from live records."""
from datetime import datetime, timedelta, timezone

from app.models import Record, parse_deadline


def seed_demo(db):
    if db.items(demo=True):
        return
    papers = [
        ("Graph neural networks for scientific discovery", "A synthetic example exploring graph machine learning, molecular representations and research discovery.", ["graph neural networks", "machine learning"], ["A. Example", "B. Researcher"]),
        ("A practical guide to retrieval-augmented generation", "A synthetic overview of retrieval, language models, vector search and evaluation for knowledge-intensive applications.", ["natural language processing", "machine learning"], ["C. Example"]),
        ("Learning visual representations with small datasets", "An illustrative study of computer vision, image classification and transfer learning with limited labeled examples.", ["computer vision", "machine learning"], ["D. Example", "E. Researcher"]),
        ("Explainable machine learning for healthcare", "A synthetic discussion of interpretable models, clinical decision support and responsible artificial intelligence.", ["machine learning", "healthcare"], ["F. Example"]),
        ("Robust planning for autonomous robots", "An illustrative research record on robotics, reinforcement learning, motion planning and uncertainty.", ["robotics", "machine learning"], ["G. Example"]),
        ("Mapping research trends with text mining", "A synthetic example using data mining and natural language processing to organize academic literature.", ["data mining", "natural language processing"], ["H. Example"]),
    ]
    for i, (title, abstract, topics, authors) in enumerate(papers):
        db.upsert(Record(kind="paper", source="demo", external_id=f"paper-{i}", title=title,
                         abstract=abstract, topics=topics, authors=authors, year=2026-i%3,
                         venue="Synthetic demonstration record", demo=True))
    for i, (title, topic, location, offset) in enumerate([
        ("Example Symposium on Machine Learning", "machine learning", "Mumbai, India", 12),
        ("Example Workshop on Language Technologies", "natural language processing", "Online", 25),
        ("Example Computer Vision Forum", "computer vision", "Singapore", 40),
        ("Example Robotics Research Meeting", "robotics", "Berlin, Germany", -5),
        ("Example Data Mining Colloquium", "data mining", "To be announced", None),
    ]):
        raw = (datetime.now(timezone.utc)+timedelta(days=offset)).strftime("%Y-%m-%d 23:59:59") if offset is not None else "TBA"
        db.upsert(Record(kind="conference", source="demo", external_id=f"conference-{i}",
                         title=title, topics=[topic], location=location, year=datetime.now().year,
                         event_dates="Illustrative event; not a real opportunity", demo=True,
                         note="Synthetic demonstration only. Dates are generated when the demo is first loaded.",
                         **parse_deadline(raw, "UTC")))
