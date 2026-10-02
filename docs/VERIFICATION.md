# Verification record

## Implementation and usage audit — 2 October 2026

Reviewed all 33 original tracked files, including application code, assets, dependency files, tests, CI, fixtures, and documentation. Added targeted regression tests and a real Chromium journey.

Observed locally on a fresh Python 3.12.14 environment:

- Installation from `requirements-dev.txt` succeeded; `pip check` found no broken requirements.
- **50 Python tests passed**, including 20 new regression cases.
- The jsdom interface journey passed against the actual FastAPI API.
- JavaScript syntax and Git whitespace checks passed.
- Live adapter query `natural language processing`: Crossref returned **30** papers and ML Deadlines returned **307** listings. **arXiv timed out after three attempts**; no claim of successful live arXiv retrieval is made for this audit.
- Regression coverage verifies partial failures preserve records, transient failures recover, retries are throttled and bounded, failed refreshes remain retryable, streamed responses stop at the size limit, and compressed content is decoded correctly.
- Other fixes cover omitted-note preservation, notes in CSV exports, source health history, concurrent identifier merging, null optional metadata, refresh lock cleanup, stable database paths, invalid origin handling, pagination recovery, and mode-switch races.

Windows/Linux Python 3.11/3.12 CI and the Chromium journey are being verified on the audit branch. The local environment's browser download returned an invalid archive, so it could not run Chromium locally. CI results will be recorded here once complete.

The historical results below describe the original build separately.

Implementation verification on 30 September 2026. Results below describe observed checks, not guarantees about future provider availability.

## Automated Python tests

**30 passed** using Python 3.12.14 and the dependencies recorded in `requirements-lock.txt`.

Covered: API validation, partial provider failure, cache reuse, JSON/Atom/HTML parsing, missing metadata, parser drift, DOI/arXiv identity, late identifier bridges, preservation of both bookmark notes during merging, idempotent ingestion, demo/live isolation, persistence across database reopen, filtering/ranking, uncertain dates, AoE conversion, invalid dates, expired deadlines, changed deadlines, CSV formula escaping, source allowlists, robots denial, throttling retries, unknown records, and local-origin protection.

The installed Starlette test client emitted one upstream deprecation warning about its httpx transport. No test failed. Runtime acquisition uses HTTPX directly. CI runs the offline Python suite and optional DOM interaction suite on pushes and pull requests.

## Live end-to-end acquisition

A real refresh was submitted to the actual FastAPI application through TestClient using its production provider client. Query: `graph neural networks`.

| Provider | Parsed records | Outcome |
| --- | --- | --- |
| Crossref | 30 papers | Success |
| arXiv | 30 papers | Success |
| ML Deadlines | 307 conference listings | Success |

The database held 60 unique paper records and 307 conference records after this refresh. The dashboard counted 22 future/date-only/due-today submission deadlines at that time. Acquisition ran from 05:46:10 to 05:46:31 UTC, approximately 21 seconds. This is one smoke run, not a performance benchmark. It does not establish metadata accuracy or worldwide coverage.

Live HTML and databases from verification are not committed. The tracked parser fixtures and demo are synthetic. The live adapters can be exercised locally through **Search sources**.

## Interface interaction checks

The interface JavaScript passed `node --check`. A jsdom harness connected the actual interface to FastAPI TestClient through a local process bridge and verified:

- Demo initialization and six paper cards.
- Bookmark creation and saved collection.
- Note saving and retrieval when reopening details.
- Conference browsing and future-deadline filtering.
- Dashboard rendering.
- Topic search and clearing the query.
- Switching from demo to live without mixing data.
- Refresh submission, job polling, and final result rendering with mocked providers.
- No JavaScript exceptions during these journeys.

Run these checks with `npm ci` and `npm run test:ui` after installing Python test dependencies. Node.js is used only for development verification; it is not required to run Eureka.

## Visual verification limitation

A full Chromium smoke run was attempted, but this execution environment blocked Chromium's process socket creation (`Operation not permitted`). Therefore desktop/mobile screenshots, actual browser download behavior, keyboard focus behavior, and rendered responsive layout were **not visually verified here**. jsdom checks interaction logic, not browser layout.

Manual local check before presenting:

1. Start the application and open it in Chrome or Edge at 127.0.0.1:8000.
2. Check the paper and conference screens at desktop and narrow/mobile widths.
3. Save a record and note, restart the server, and reopen the saved collection.
4. Export CSV and open it in a spreadsheet application; confirm Unicode and filter selection.
5. Inspect a conference's raw deadline, local-time display, notes, and original link.
6. Confirm source progress, stale labels, empty states, and the synthetic-data banner.

## Known scope limits

- Conference dates are aggregator-reported. They have not all been independently checked against organizers.
- Only the primary listed deadline and notes are extracted; earlier abstract deadlines and track-specific rules require official verification.
- Search ranks the bounded local collection, with a maximum of 30 paper results per provider per refresh. It is not a complete literature review.
- Fuzzy title merging is intentionally absent. Only explicit identifiers establish duplicate equivalence.
- No measured Precision@10, field-accuracy study, accessibility audit, or cross-platform browser certification is claimed.
- Public accounts, email alerts, scheduled refreshing, deployment, and a separate report/presentation remain extensions.
