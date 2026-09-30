from datetime import date, datetime, timedelta, timezone
import hashlib
import re
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel, Field


def now_iso():
    return datetime.now(timezone.utc).isoformat()


def safe_url(value):
    value = str(value or "").strip()
    try:
        p = urlsplit(value)
        return value if p.scheme in {"http", "https"} and p.hostname and not p.username else ""
    except ValueError:
        return ""


def normalize_doi(value):
    value = re.sub(r"^(?:https?://(?:dx\.)?doi\.org/|doi:\s*)", "", str(value or "").strip(), flags=re.I)
    return value.lower() if re.match(r"^10\.\d{4,9}/\S+$", value, re.I) else ""


def stable_id(value):
    return hashlib.sha256(value.encode()).hexdigest()[:24]


class Record(BaseModel):
    kind: str
    external_id: str
    source: str
    title: str
    url: str = ""
    source_url: str = ""
    authors: list[str] = Field(default_factory=list)
    abstract: str = ""
    year: int | None = None
    doi: str = ""
    arxiv_id: str = ""
    venue: str = ""
    topics: list[str] = Field(default_factory=list)
    location: str = ""
    event_dates: str = ""
    deadline_raw: str = ""
    deadline_timezone: str = ""
    deadline_utc: str | None = None
    deadline_date: str | None = None
    deadline_precision: str = "unknown"
    note: str = ""
    demo: bool = False
    retrieved_at: str = Field(default_factory=now_iso)


def parse_deadline(raw, tz=""):
    result = {"deadline_raw": raw, "deadline_timezone": tz, "deadline_utc": None,
              "deadline_date": None, "deadline_precision": "unknown"}
    if not raw or not re.match(r"^\d{4}-\d{2}-\d{2}(?:$|[ T])", raw):
        return result
    try:
        value = datetime.fromisoformat(raw.strip())
        result["deadline_date"] = value.date().isoformat()
        result["deadline_precision"] = "date"
        if len(raw.strip()) <= 10:
            return result
        zone = value.tzinfo
        if not zone:
            if tz in {"AoE", "Anywhere on Earth"}:
                zone = timezone(timedelta(hours=-12))
            elif match := re.fullmatch(r"UTC([+-])(\d{1,2})(?::(\d{2}))?", tz):
                hours, minutes = int(match[2]), int(match[3] or 0)
                if hours > 14 or minutes > 59:
                    return result
                zone = timezone((1 if match[1] == "+" else -1) * timedelta(hours=hours, minutes=minutes))
            elif tz:
                zone = ZoneInfo(tz)
        if zone:
            result["deadline_utc"] = value.replace(tzinfo=zone).astimezone(timezone.utc).isoformat()
            result["deadline_precision"] = "instant"
    except (ValueError, ZoneInfoNotFoundError):
        pass
    return result


def deadline_status(record, now=None):
    now = now or datetime.now(timezone.utc)
    if record.get("deadline_utc"):
        delta = datetime.fromisoformat(record["deadline_utc"]) - now
        return {"status": "expired" if delta.total_seconds() < 0 else "open",
                "days_left": max(0, delta.days) if delta.total_seconds() >= 0 else delta.days}
    if record.get("deadline_date"):
        days = (date.fromisoformat(record["deadline_date"]) - now.date()).days
        return {"status": "expired" if days < 0 else "due_today" if days == 0 else "date_only", "days_left": days}
    return {"status": "unknown", "days_left": None}
