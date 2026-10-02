# Eureka: single-session implementation

The original six-week roadmap was replaced at the user's request. This document records the implemented first version and the remaining extensions; there is no weekly schedule.

## Delivery checklist

- [x] Verify repository state and source feasibility.
- [x] Implement live Crossref and arXiv paper retrieval.
- [x] Implement ML Deadlines HTML extraction with runtime robots checks.
- [x] Normalize records and merge confirmed DOI/arXiv duplicates.
- [x] Persist records, identity aliases, source observations, bookmarks, notes, jobs, and cache metadata in SQLite.
- [x] Implement TF-IDF relevance ranking, filters, stable ordering, and pagination.
- [x] Distinguish exact, date-only, unknown, and expired deadlines.
- [x] Implement background refresh, per-source failures, throttling, and caching.
- [x] Build the browser interface, saved collection, details, dashboard, and CSV export.
- [x] Add isolated and labeled offline demo data.
- [x] Add API documentation, installation instructions, and offline CI tests.
- [x] Verify live ingestion from all three providers.

See [VERIFICATION.md](VERIFICATION.md) for precisely what was tested and any environment limitations.

## Implementation decisions

| Original proposal | Implemented choice | Why |
| --- | --- | --- |
| Streamlit plus separate API | Static HTML/CSS/JavaScript served by FastAPI | One start command, one server, and no frontend build |
| SQLAlchemy with many entity tables | Standard-library SQLite with JSON records and relational identity/collection tables | Less setup while preserving referential integrity and queryable identity |
| WikiCFP or unspecified official pages | ML Deadlines | Live HTML was reachable and the source explicitly permits crawling |
| Many scheduled milestones | One vertical build with offline and live verification | Matches the single-session delivery request |

## Implemented pipeline

1. A user enters a topic or filters the collected database.
2. A refresh request is validated and assigned a persisted job ID.
3. A single worker checks each provider's 24-hour cache.
4. The worker retrieves JSON from Crossref, Atom from arXiv, and HTML from ML Deadlines.
5. Parsers produce common records; optional missing values remain empty or null.
6. Identifier aliases consolidate confirmed duplicates and keep source observations.
7. SQLite stores records and bookmarks; changed observations remain visible in details.
8. Search applies local filters and TF-IDF cosine scoring over titles, abstracts, topics, authors, and notes.
9. The interface shows cards, source health, details, and deadlines; selected filtered collections can be exported.

## Data model

| Table | Purpose |
| --- | --- |
| `items` | Canonical records; `kind` distinguishes papers/conferences and `demo` isolates synthetic examples |
| `aliases` | Unique provider IDs, DOI IDs, and arXiv IDs mapped to canonical records |
| `observations` | Metadata snapshots keyed by content hash; unchanged refreshes do not duplicate history |
| `bookmarks` | One bookmark per canonical record, with a note and saved timestamp |
| `source_runs` | Per-provider/per-query cache and latest acquisition outcome; conferences use a shared index key |
| `jobs` | Refresh lifecycle, progress, and error summaries |

Confirmed identifier bridges also preserve bookmarks and observations. Similar titles do not merge automatically. Conference IDs retain the source's separate editions/rounds. The scraper captures the primary listed deadline and explanatory notes; it does not claim to model every track or abstract deadline separately.

## Operational limits

- One local user, one server process, and one refresh job at a time.
- Paper requests retrieve at most 30 results per provider per topic; no whole-corpus harvesting.
- The scraper fetches robots.txt and a single index page, parses at most 500 cards, and never crawls official links.
- Successful identical topic/provider queries and the conference index are cached for 24 hours. There is no force-refresh bypass.
- Three attempts at most for HTTP 429/5xx, transient network errors and timeouts; bounded retry sleeps, a 30-second read timeout, a 60-second body-read budget checked between chunks, and a 4 MB decoded response limit enforced while streaming.
- Network failures retain stored data. Details expose timestamps; the dashboard displays each provider's latest run and last success.
- Schema version is 1; formal upgrade migrations should be added before incompatible schema changes.

## Extensions

- [ ] Validate conference deadlines against additional official sources and model multiple track/abstract deadlines.
- [ ] Add provider pagination, retained-query result membership, and a collection management policy for much larger databases.
- [ ] Add scheduled refresh and opt-in notifications.
- [ ] Add optional semantic matching and a manually labeled relevance evaluation.
- [ ] Add accounts, authorization, and PostgreSQL before public multi-user hosting.
- [ ] Add BibTeX/calendar export and a presentation/report as separate deliverables when requested.
