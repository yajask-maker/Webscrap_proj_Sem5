"""Bounded acquisition from fixed providers; never fetch user-supplied URLs."""
import json
import re
import threading
import time
from urllib.parse import urljoin, urlsplit
from urllib.robotparser import RobotFileParser

from bs4 import BeautifulSoup
import feedparser
import httpx

from app.models import Record, normalize_doi, parse_deadline, safe_url

SOURCE_INFO = {
    "crossref": {"name": "Crossref", "method": "REST · JSON", "url": "https://api.crossref.org/works"},
    "arxiv": {"name": "arXiv", "method": "HTTP API · Atom", "url": "https://export.arxiv.org/api/query"},
    "mldeadlines": {"name": "ML Deadlines", "method": "Web scraping · HTML", "url": "https://mldeadlines.com/"},
}
TOPICS = {"ML": "machine learning", "CV": "computer vision", "NLP": "natural language processing",
          "DM": "data mining", "RO": "robotics", "SP": "speech signal processing", "KR": "knowledge representation",
          "HCI": "human computer interaction", "AP": "automated planning", "CG": "computer graphics"}


def plain(value):
    return BeautifulSoup(str(value or ""), "html.parser").get_text(" ", strip=True)


def crossref_records(payload):
    message = payload.get("message", {})
    if not isinstance(message, dict) or not isinstance(message.get("items"), list):
        raise ValueError("Crossref response schema changed")
    records = []
    for item in message["items"]:
        doi = normalize_doi(item.get("DOI"))
        title = plain((item.get("title") or [""])[0])
        if not doi or not title:
            continue
        parts = (item.get("published", {}).get("date-parts") or [[]])[0]
        authors = [" ".join(filter(None, [a.get("given"), a.get("family")])) or a.get("name", "") for a in item.get("author", [])]
        records.append(Record(kind="paper", external_id=doi, source="crossref", title=title,
                              url="https://doi.org/" + doi, source_url="https://doi.org/" + doi, doi=doi,
                              year=parts[0] if parts else None, authors=[a for a in authors if a],
                              abstract=plain(item.get("abstract")), venue=plain((item.get("container-title") or [""])[0]),
                              topics=item.get("subject") or []))
    if message["items"] and not records:
        raise ValueError("Crossref returned records but none could be parsed")
    return records


def arxiv_records(xml):
    feed = feedparser.parse(xml)
    if feed.bozo:
        raise ValueError("Invalid arXiv Atom response")
    if not feed.version.startswith("atom"):
        raise ValueError("Expected an arXiv Atom feed")
    records = []
    for item in feed.entries:
        identifier = item.get("id", "")
        if "/api/errors" in identifier:
            raise ValueError("arXiv rejected the search query")
        external_id = identifier.split("/abs/")[-1]
        if "/abs/" not in identifier or not item.get("title"):
            continue
        base_id = re.sub(r"v\d+$", "", external_id)
        published = item.get("published", "")
        records.append(Record(kind="paper", external_id=base_id, source="arxiv",
                              title=" ".join(item.title.split()), url="https://arxiv.org/abs/" + base_id,
                              source_url="https://arxiv.org/abs/" + external_id, arxiv_id=base_id,
                              doi=normalize_doi(item.get("arxiv_doi")), abstract=" ".join(item.get("summary", "").split()),
                              authors=[a.name for a in item.get("authors", [])],
                              year=int(published[:4]) if published[:4].isdigit() else None,
                              venue=item.get("arxiv_journal_ref", "arXiv preprint"),
                              topics=[t.term for t in item.get("tags", [])]))
    if feed.entries and not records:
        raise ValueError("arXiv returned entries but none could be parsed")
    return records


def conference_records(html):
    soup = BeautifulSoup(html, "html.parser")
    nodes = soup.select(".ConfItem")
    if not nodes:
        raise ValueError("Conference page layout changed: no conference cards found")
    records = []
    for node in nodes[:500]:
        title_node = node.select_one(".conf-title a")
        if not title_node or not node.get("id"):
            continue
        def text(selector):
            found = node.select_one(selector)
            return found.get_text(" ", strip=True).strip(" .") if found else ""
        official = node.select_one(".conf-title-icon a")
        title = title_node.get_text(" ", strip=True)
        year = re.search(r"\b(20\d{2})\b", title)
        note = text(".note")
        raw = node.get("data-deadline", "")
        fields = parse_deadline(raw, "UTC" if raw.endswith("Z") else "")
        # Do not promote an aggregator's explicitly assumed timezone into certainty.
        if re.search(r"\b(assumed|estimated|tentative)\b|no timezone|timezone.*(?:unspecified|unknown)", note, re.I):
            fields["deadline_utc"] = None
            fields["deadline_precision"] = "date" if fields["deadline_date"] else "unknown"
            fields["deadline_timezone"] = "unverified; see source note"
        records.append(Record(kind="conference", source="mldeadlines", external_id=node["id"],
                              title=title, year=int(year[1]) if year else None,
                              url=safe_url(official.get("href")) if official else "",
                              source_url=safe_url(urljoin(SOURCE_INFO["mldeadlines"]["url"], title_node.get("href", ""))),
                              location=text(".conf-place"), event_dates=text(".conf-date"), note=note,
                              topics=[TOPICS.get(t.get("data-sub"), t.get_text(" ", strip=True)) for t in node.select(".conf-sub[data-sub]")], **fields))
    if not records:
        raise ValueError("Conference cards were present but no valid records were extracted")
    return records


class ProviderClient:
    def __init__(self, email="", client=None):
        self.email = email
        self.client = client or httpx.Client(timeout=httpx.Timeout(12.0, connect=10.0), follow_redirects=False,
                                             headers={"User-Agent": "EurekaResearch/1.0" + (" (mailto:" + email + ")" if email else "")})
        self.last = {}
        self.lock = threading.Lock()

    def close(self):
        self.client.close()

    def request(self, source, url, params=None):
        allowed = {"api.crossref.org", "export.arxiv.org", "mldeadlines.com"}
        if urlsplit(url).hostname not in allowed or urlsplit(url).scheme != "https":
            raise ValueError("Provider URL is not allowlisted")
        delay = 3.1 if source == "arxiv" else 1.0
        for attempt in range(3):
            with self.lock:
                wait = delay - (time.monotonic() - self.last.get(source, -100))
                if wait > 0:
                    time.sleep(wait)
                self.last[source] = time.monotonic()
                response = self.client.get(url, params=params)
            if response.status_code == 429 or response.status_code >= 500:
                if attempt == 2:
                    response.raise_for_status()
                retry_after = response.headers.get("Retry-After", "")
                if retry_after and (not retry_after.isdigit() or int(retry_after) > 8):
                    raise ValueError("Provider asks for a longer retry delay; please retry later")
                time.sleep(max(2 ** attempt, int(retry_after or 0)))
                continue
            response.raise_for_status()
            if len(response.content) > 4_000_000:
                raise ValueError("Provider response exceeds the size limit")
            return response
        raise ValueError("Provider could not be reached")

    def fetch(self, source, query):
        if source == "crossref":
            params = {"query.bibliographic": query, "rows": 30}
            if self.email:
                params["mailto"] = self.email
            return crossref_records(self.request(source, SOURCE_INFO[source]["url"], params).json())
        if source == "arxiv":
            terms = re.findall(r"[\w-]+", query, re.UNICODE)
            expression = " AND ".join('all:"' + term + '"' for term in terms)
            return arxiv_records(self.request(source, SOURCE_INFO[source]["url"],
                                  {"search_query": expression, "start": 0, "max_results": 30, "sortBy": "relevance"}).text)
        if source == "mldeadlines":
            robots = self.request(source, "https://mldeadlines.com/robots.txt")
            if "user-agent" not in robots.text.lower():
                raise ValueError("Could not verify the conference robots policy")
            policy = RobotFileParser()
            policy.parse(robots.text.splitlines())
            if not policy.can_fetch("EurekaResearch", SOURCE_INFO[source]["url"]):
                raise ValueError("Conference source currently disallows this crawler")
            crawl_delay = policy.crawl_delay("EurekaResearch") or policy.crawl_delay("*") or 0
            if crawl_delay > 8:
                raise ValueError("Conference source requires a longer crawl delay; adapter paused")
            if crawl_delay:
                time.sleep(crawl_delay)
            return conference_records(self.request(source, SOURCE_INFO[source]["url"]).text)
        raise ValueError("Unknown source")
