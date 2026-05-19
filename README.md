# RDS — Web Scraper Module

Fast, concurrent web scraper that collects articles from multiple news sources, extracts clean article text, and presents the results through a Flask API and browser UI. Designed as the data-collection layer of a larger Rumor Detection System.

> **No ML models are used.** All processing is pure Python — no GPU, no model downloads, no slow inference.

---

## Quick Start

```bash
# 1. Create and activate the conda environment
conda env create -f environment.yml
conda activate rds-env

# 2. Install Scrapling browser binaries (one-time, ~500 MB)
scrapling install

# 3. Start the server
python run.py
```

Open **http://localhost:5000** in your browser.

---

## How It Works — 3-Phase Pipeline

Every search job runs through three sequential phases, each logged separately so failures are easy to spot:

```
USER QUERY
    │
    ▼
┌──────────────────────────────────────────────┐
│  PHASE 1 — SOURCE SEARCH  (parallel)         │
│                                              │
│  GoogleNews RSS · BingNews RSS ·             │
│  Reddit JSON API · HackerNews Algolia API ·  │
│  DuckDuckGo News                             │
│                                              │
│  All sources run concurrently in threads.    │
│  Results deduplicated by URL before fetch.   │
└──────────────────┬───────────────────────────┘
                   │  list[RawResult]  (url + metadata only)
                   ▼
┌──────────────────────────────────────────────┐
│  PHASE 2 — ARTICLE FETCH  (20 workers)       │
│                                              │
│  httpx (fast, realistic browser headers)     │
│    └─ Scrapling Fetcher on 403/429/503       │
│         └─ trafilatura downloader fallback   │
│                                              │
│  trafilatura extracts main article body.     │
│  Stats tracked live: full / snippet / fail.  │
└──────────────────┬───────────────────────────┘
                   │  raw HTML + extracted text
                   ▼
┌──────────────────────────────────────────────┐
│  PHASE 3 — PREPROCESS  (pure Python)         │
│                                              │
│  • Strip HTML, fix encoding, remove noise    │
│  • Language detection (langdetect)           │
│  • Quality gate: min 50 words                │
│  • Content-hash deduplication                │
│  • Sort by publication date                  │
└──────────────────┬───────────────────────────┘
                   │
                   ▼
          list[Article]  →  JSON API response
```

### Why it's fast

| What | How |
|------|-----|
| Source search | All 5 sources queried **simultaneously** |
| Article fetch | **20 concurrent threads** (configurable) |
| No ML models | Zero model-load time, zero inference latency |
| Early URL dedup | Skips fetching duplicate URLs from different sources |
| Short timeout | 12 s/request — bad pages don't stall the queue |

---

## Sources

| Key | Name | Method |
|-----|------|--------|
| `google_news` | Google News | RSS search feed |
| `bing_news` | Bing News | RSS search feed |
| `reddit` | Reddit | JSON search API |
| `hackernews` | Hacker News | Algolia search API |
| `duckduckgo` | DuckDuckGo News | `duckduckgo-search` library |

Add a new source by creating `app/scraper/sources/my_source.py` (extend `BaseSource`, implement `search()`), then register it in `app/scraper/sources/__init__.py` → `SOURCE_REGISTRY`.

---

## Project Structure

```
RDS/
├── run.py                          # Entry point
├── environment.yml                 # Conda environment
├── requirements.txt
├── config/
│   ├── config.yaml                 # Scraper tuning (concurrency, timeouts, quality gates)
│   └── sources.yaml                # Per-source enable/disable and limits
│
├── app/
│   ├── __init__.py                 # Flask app factory
│   ├── api/routes.py               # REST endpoints
│   ├── models/schemas.py           # RawResult · Article · SearchJob · ScraperStats
│   │
│   ├── scraper/                    # Data collection layer
│   │   ├── engine.py               # Job management · 3-phase orchestration
│   │   ├── fetcher.py              # HTTP layer: httpx → Scrapling → trafilatura
│   │   ├── extractor.py            # trafilatura content extraction wrapper
│   │   └── sources/
│   │       ├── base.py             # Abstract BaseSource
│   │       ├── google_news.py
│   │       ├── bing_news.py
│   │       ├── reddit.py
│   │       ├── hackernews.py
│   │       └── duckduckgo.py
│   │
│   ├── preprocessor/               # Text cleaning layer (no ML)
│   │   ├── cleaner.py              # HTML strip · encoding fix · noise removal · language detect · date normalise
│   │   └── deduplicator.py         # URL-level dedup (before fetch) · content-hash dedup (after fetch)
│   │
│   └── utils/
│       ├── logger.py               # Loguru rotating logger
│       └── text_cleaner.py         # Low-level text utilities
│
├── templates/index.html            # Single-page UI
├── static/
│   ├── css/style.css
│   └── js/app.js                   # Vanilla JS: search · progress phases · stats · modal
│
├── tests/
│   ├── test_scraper.py
│   └── test_nlp.py
└── logs/                           # Rotating log files (auto-created)
```

---

## REST API

### Start a scrape job
```http
POST /api/search
Content-Type: application/json

{
  "query":        "5G towers health risks",
  "sources":      ["google_news", "bing_news", "reddit", "hackernews", "duckduckgo"],
  "max_articles": 40
}
```
Response `202`:
```json
{ "job_id": "d3f1…", "status": "pending" }
```

### Poll status + results
```http
GET /api/job/{job_id}
```
Returns full `articles[]` array only when `status == "completed"`.

### List recent jobs
```http
GET /api/jobs
```

### List available sources
```http
GET /api/sources
```

### Health check
```http
GET /api/health
```

---

## Article Schema

Each completed article exposes:

| Field | Type | Description |
|-------|------|-------------|
| `id` | str | UUID |
| `url` | str | Source URL |
| `title` | str | Article title |
| `source` | str | Human label (e.g. `"Reddit / r/worldnews"`) |
| `source_type` | str | Machine key (e.g. `"reddit"`) |
| `published` | str | ISO-8601 UTC date |
| `author` | str | Author if available |
| `content` | str | Full cleaned article body |
| `snippet` | str | Short RSS/API description (fallback) |
| `word_count` | int | Words in `content` |
| `language` | str | ISO 639-1 code detected by langdetect |
| `fetch_mode` | str | `"full"` / `"snippet_only"` / `"failed"` |
| `scraped_at` | str | Timestamp of scrape |

---

## Configuration

**`config/config.yaml`** — all scraper knobs:

```yaml
scraper:
  concurrent_requests: 20    # Phase 2 worker threads
  request_timeout: 12        # seconds per HTTP request
  min_content_words: 50      # quality gate
  language_filter: "en"      # set to "" to accept all languages
```

**`config/sources.yaml`** — per-source settings:

```yaml
sources:
  google_news:
    enabled: true
    max_results: 20
  duckduckgo:
    enabled: true
    max_results: 15
    timelimit: "m"           # d=day w=week m=month y=year
```

---

## Running Tests

```bash
conda activate rds-env
pytest tests/ -v
```

All tests are model-free and run without network access.

---

## Debugging Tips

- Every phase logs at `INFO` level — tail `logs/rds.log` while a job runs to watch the pipeline
- The stats bar in the UI shows per-phase counts (URLs found → unique → full/snippet/failed → deduped → final)
- Increase `concurrent_requests` for faster fetching on fast networks; decrease if you're hitting rate limits
- Set `language_filter: ""` in `config.yaml` to stop dropping non-English articles
- Set `LOG_LEVEL: DEBUG` to see per-URL fetch method (httpx / scrapling / trafilatura) and extraction results

---

## Adding a New Source

1. Create `app/scraper/sources/my_source.py` — extend `BaseSource`, implement `search(query) -> Iterator[RawResult]`
2. Add `"my_source": MySource` to `SOURCE_REGISTRY` in `app/scraper/sources/__init__.py`
3. Add a config block to `config/sources.yaml`

No other files need to change.
