# Eureka

**Multi-Source Research Paper and Conference Opportunity Discovery using Web Scraping and REST APIs**

Eureka is a proposed research discovery application that helps students and researchers find relevant papers and upcoming conference submission opportunities in one place.

**Status: implementation planning.** This repository currently contains the project plan, not a running application. All features and commands described as planned are future implementation work.

## Project documents

- [Implementation plan](docs/IMPLEMENTATION_PLAN.md): scope, architecture, modules, database design, API contract, six-week roadmap, tests, and demonstration criteria.
- [Source integration notes](docs/SOURCES.md): verified paper API documentation, conference source selection, access constraints, and validation checklist.

## Planned first version

- Search paper metadata from Crossref and arXiv through one interface.
- Discover conference calls for papers through permitted HTML scraping.
- Normalize records, remove confirmed duplicates, and retain source links.
- Filter papers by year and source; filter conferences by topic, location, and deadline.
- Rank results by relevance and show why each result matches.
- Bookmark results, export CSV files, and view approaching deadlines.
- Show data freshness, missing fields, and partial source failures clearly.

## Proposed stack

| Layer | Choice |
| --- | --- |
| Interface | Streamlit |
| Application REST API | FastAPI and Pydantic |
| Acquisition | HTTPX, Beautiful Soup, and feedparser |
| Storage | SQLite with SQLAlchemy |
| Relevance scoring | scikit-learn TF-IDF and cosine similarity |
| Verification | pytest, mocked HTTP responses, and GitHub Actions |

The initial release targets a single-user local demonstration. Accounts, email alerts, semantic embeddings, and public multi-user hosting are extensions.

## Implementation sequence

| Week | Deliverable |
| --- | --- |
| 1 | Confirm sources, create project skeleton, and define schemas |
| 2 | Integrate paper APIs and persist normalized records |
| 3 | Implement a permitted conference scraper and deadline handling |
| 4 | Complete search, deduplication, ranking, and REST endpoints |
| 5 | Build the interface, bookmarks, exports, and deadline dashboard |
| 6 | Validate the system and prepare the demonstration and report |

Conference source approval is an early dependency: WikiCFP is a candidate, not a verified scraping integration. See [source integration notes](docs/SOURCES.md). The project is complete only when it demonstrates both REST API retrieval and permitted live web scraping.
