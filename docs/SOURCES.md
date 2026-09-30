# Source register

Reviewed and smoke-tested on 30 September 2026. Provider availability and policies may change; failures are displayed without removing existing data.

| Source | Use | Endpoint | Access and bounds |
| --- | --- | --- | --- |
| Crossref | Bibliographic paper search and DOI metadata | `https://api.crossref.org/works` | Public API; optional contact email; one serial request per second; 30 results per topic |
| arXiv | Preprints, abstracts, authors, categories | `https://export.arxiv.org/api/query` | Atom API; one request per 3.1 seconds; one connection; 30 results per topic |
| ML Deadlines | Conference opportunities and primary submission deadlines | `https://mldeadlines.com/` | HTML scraping; fixed index only; runtime robots check; 24-hour cache; maximum 500 cards |

## Crossref

The client sends a bibliographic query and optional `mailto` contact, parses DOI, title, authors, abstract, venue, subjects, and year, and tolerates absent optional metadata. Its deliberately conservative serial request cadence is below the public limit documented when reviewed. HTTP throttling is surfaced and retried within bounded limits. Some supplied abstracts have reuse restrictions; exports intentionally contain bibliographic metadata rather than abstract text.

- [REST API overview](https://www.crossref.org/documentation/retrieve-metadata/rest-api/)
- [Access and request limits](https://www.crossref.org/documentation/retrieve-metadata/rest-api/access-and-authentication/)

## arXiv

The client parses Atom, preserves source version URLs, normalizes base identifiers, and honors the legacy API's three-second interval and single-connection requirement with a 3.1-second limiter. Descriptive metadata supports discovery; full paper PDFs are not downloaded or hosted. A preprint is not automatically labeled peer reviewed.

- [API manual](https://info.arxiv.org/help/api/user-manual.html)
- [Terms of use](https://info.arxiv.org/help/api/tou.html)

## ML Deadlines

The homepage and [robots policy](https://mldeadlines.com/robots.txt) were retrieved successfully during implementation. The policy explicitly welcomes crawlers for public conference deadline data and allows the index path. The client rechecks that policy before an uncached scrape; an unreadable or disallowing policy stops acquisition.

Source scope: only `https://mldeadlines.com/robots.txt` and `https://mldeadlines.com/`. Redirects are not automatically followed. Discovery and official event links are stored for the user to open; they are not additional crawl targets. HTTP requests identify the application as `EurekaResearch/1.0`.

Extraction uses `.ConfItem` cards, source IDs, `.conf-title`, official-link anchors, `.conf-place`, `.conf-date`, `.conf-sub`, notes, and the page's ISO `data-deadline` attributes. It does not execute scripts. Missing cards cause an explicit parser error rather than a false empty success. Notes that explicitly describe assumed/estimated/tentative timing prevent an exact countdown.

Only factual discovery metadata and short source-provided notes are stored locally. Source links and attribution remain in the UI and exports. The project does not redistribute the full scraped HTML or copy the source site's interface/assets. Checked robots permission is not a claim of ownership over source content. The test HTML is authored synthetic content.

The source is an aggregator, not an official organizer. The displayed time may be inferred or changed upstream. Every conference detail instructs the user to verify the official CFP, including earlier abstract/registration requirements. Different rounds/editions remain separate source records. Unlisted tracks and events remain outside coverage.

## Candidates not enabled

WikiCFP was not enabled because automated-use policy and parser feasibility were not established. The original `aideadlin.es` was reachable but its observed index was older than the selected source. Neither is silently used as a fallback.

## Storage and source checks

- Real acquired data stays in the local database, excluded from Git.
- Test/demo records are synthetic and never presented as live results.
- API keys are unnecessary for the selected providers.
- Identical source metadata does not multiply observation rows.
- Recheck terms and source behavior before adding broader collection or redistribution.
