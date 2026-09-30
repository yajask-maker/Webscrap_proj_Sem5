# Eureka REST API

Base URL: `http://127.0.0.1:8000/api/v1`. Interactive OpenAPI documentation: `/docs`.

The API belongs to a local single-user workspace. It does not provide public-user authentication. Cross-origin writes and unrecognized Host headers are rejected. Keep the default loopback binding and one server worker.

| Method | Route | Purpose |
| --- | --- | --- |
| GET | `/health` | Application/database readiness |
| GET | `/items` | Search and paginate stored records |
| GET | `/items/{id}` | Record details and up to 20 most recent source observations |
| POST | `/refresh` | Queue acquisition; returns HTTP 202 and job ID |
| GET | `/jobs/{id}` | Progress and final provider outcomes |
| GET | `/sources` | Provider metadata and most recent status |
| POST | `/demo` | Idempotently initialize isolated synthetic examples |
| POST | `/bookmarks` | Save a record or update its note |
| DELETE | `/bookmarks/{id}` | Remove a bookmark; returns 204 |
| GET | `/export` | Download CSV for the selected filters, capped at 5,000 rows |
| GET | `/dashboard` | Counts, upcoming deadlines, saved upcoming deadlines, source health |

## Stored-record search

Example: `/items?kind=paper&q=graph&source=arxiv&year_from=2024&page=1&page_size=12`.

| Parameter | Values/default |
| --- | --- |
| `kind` | `paper` (default), `conference`, `all` |
| `q` | Optional text, max 200 characters; empty browses stored records |
| `mode` | `live` (default) or `demo` |
| `saved` | Boolean; false by default |
| `source` | Empty or `crossref`, `arxiv`, `mldeadlines`, `demo` |
| `year_from`, `year_to` | Optional inclusive range, 1900–2100; unknown years excluded when bounded |
| `location` | Case-insensitive substring |
| `deadline` | `all`, `open`, `expired`, `unknown`; applies to conferences |
| `sort` | `relevance`, `newest`, `deadline` |
| `page` | 1-based |
| `page_size` | 1–100; default 12 |

Response fields: `items`, `total`, `page`, `page_size`, `source_status`, `mode`. Totals describe the local collection, not entire provider databases. Each item includes matched query terms, text-similarity score, source provenance, retrieval timestamp, bookmark state, and deadline status. Search only reads local data; acquisition is explicit.

`open` includes future exact deadlines, future date-only deadlines, and date-only deadlines today. It is a time-based filter, not a guarantee of submission eligibility. Exact instants are stored in UTC. Date-only comparisons use the server's UTC calendar date and remain visibly uncertain. Browser-local time is shown only for exact instants.

`/export` accepts the same substantive filters but no pagination parameters. `kind` defaults to `all` for export. It includes a UTF-8 BOM and neutralizes spreadsheet formula-like cells. `/dashboard` accepts `mode` only.

## Refresh

```json
{
  "query": "graph neural networks",
  "sources": ["crossref", "arxiv", "mldeadlines"]
}
```

The query must contain at least two characters and an alphanumeric character. Sources default to all three; an empty list is invalid. The conference source refreshes its shared index independently of topic, then the UI filters locally.

A successful request returns a job with `id`, `status`, `query`, `sources`, `results`, and `started_at`. Poll `/jobs/{id}` until `completed`, `partial`, or `failed`. Each source result includes status (`ok`, `cached`, `error`), parsed record count, attempt time, last success time, and error text. Successful cached requests do not call the provider again within 24 hours. Count means parsed records, not necessarily new unique records.

Only one job runs at a time; concurrent refresh requests return 409. A restart marks unfinished jobs failed so they can be retried. Jobs run in process, not in a durable external queue.

## Bookmarks

```json
{
  "item_id": "ID returned by /items",
  "note": "Useful background for the presentation"
}
```

Saving is idempotent and updates the note. Notes are limited to 1,000 characters. Records must already exist. Both live and demo bookmarks persist, with mode-based separation in search.

## Error behavior

Validation failures return 422. Unknown item/job/bookmark IDs return 404. Conflicting active refreshes return 409. Provider outages appear inside job/source outcomes; successful sources remain usable. Saved data is never erased just because a source is unavailable or returns no matches.
