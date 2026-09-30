# Source integration notes

Documentation reviewed on 30 September 2026. Reading documentation verifies an integration design, not live endpoint availability. Run and record smoke checks during implementation. Recheck provider policies before enabling collection.

## Paper sources

| Source | Proposed use | Interface | Validation status |
| --- | --- | --- | --- |
| Crossref | Published-work metadata, DOI lookup, keyword discovery | JSON REST API at `https://api.crossref.org/works` | Official documentation reviewed; live adapter not implemented |
| arXiv | Preprints, abstracts, authors, categories, identifiers | Atom/XML HTTP API at `https://export.arxiv.org/api/query` | Official documentation reviewed; live adapter not implemented |

### Crossref

The public REST API does not require signup. Use a configured contact email through the documented polite-pool mechanism. Read rate and concurrency response headers, honor throttling, and keep limits configurable rather than assuming an old fixed quota. Metadata completeness varies; abstracts may be absent and some have reuse restrictions. Retrieve discovery metadata and source links rather than treating the API as unrestricted full-text access.

References:

- [REST API overview](https://www.crossref.org/documentation/retrieve-metadata/rest-api/)
- [Access, authentication, and request limits](https://www.crossref.org/documentation/retrieve-metadata/rest-api/access-and-authentication/)
- [REST API filters](https://www.crossref.org/documentation/retrieve-metadata/rest-api/rest-api-filters/)

### arXiv

The API supports query parameters and pagination and returns Atom XML, not JSON. Parse identifiers, authors, titles, dates, categories, abstract text, and links using an Atom parser. The terms specify no more than one legacy API request every three seconds, with one connection at a time across the deployment. Cache repeated queries. Preserve preprint identity and version information; do not label every preprint as peer reviewed. Link users to arXiv rather than hosting paper PDFs.

References:

- [API user manual](https://info.arxiv.org/help/api/user-manual.html)
- [API terms of use](https://info.arxiv.org/help/api/tou.html)

## Conference sources

| Candidate | Intended use | Current decision |
| --- | --- | --- |
| [WikiCFP](https://www.wikicfp.com/) | Discover conference listings and submission dates | Candidate only; direct homepage/terms retrieval did not succeed during planning, so automated-use permission and parser feasibility remain unverified |
| Selected official conference CFP pages | Extract and verify event-specific topics, tracks, and deadlines | Exact URLs to be selected and reviewed in week 1 |

Do not commit to a candidate merely because its listings appear in search results. Inspect the exact pages, site terms, robots directives, and available feeds/APIs. Prefer a supported feed or API when available, while retaining at least one permitted HTML source for the project's scraping objective. Do not bypass login, CAPTCHA, or access restrictions.

Maintain the following source register for each enabled HTML adapter:

| Field | Required value |
| --- | --- |
| Identity | Source name, owner/organizer, base URL, adapter name |
| Scope | Exact allowed domains, paths, redirects, and pagination bounds |
| Access review | Terms URL, robots URL, reviewed date, relevant evidence, decision |
| Request policy | Identification header, minimum delay, concurrency, cache duration |
| Extraction | Required/optional fields, selectors, detail-page links, date formats |
| Storage | Permitted metadata, attribution, retention, and redistribution constraints |
| Verification | Fixture location, sample URLs, last successful smoke check, known gaps |

A missing or unclear permission decision means the adapter stays disabled until resolved. A robots allowance alone does not establish reuse rights.

## Smoke-check checklist

- [ ] Fetch one small paper result batch from each API using documented parameters.
- [ ] Confirm actual content type, useful fields, pagination, errors, and limits.
- [ ] Approve at least one conference HTML source and its exact URL patterns.
- [ ] Extract one listing and detail page; compare fields manually with the original.
- [ ] Verify uncertain, missing, changed, and track-specific deadlines.
- [ ] Confirm source attribution and storage rules before retaining fixtures or records.
- [ ] Record outcomes and dates; retain failures as unresolved work rather than claiming support.

Optional future providers should receive the same review. API keys, access tiers, pricing, and quotas may change; no additional provider is assumed available in this MVP.
