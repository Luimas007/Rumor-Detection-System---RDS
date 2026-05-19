# RDS — Rumor Detection System · Scraper Module

A Flask-powered web scraping and NLP analysis service that collects articles from multiple news sources, cleans them, and extracts key claims, themes, sentiment, and summaries — designed as a feed module for a larger Rumor Detection System.

---

## Quick Start

### 1. Create the Conda environment

```bash
conda env create -f environment.yml
conda activate rds-env
```

### 2. Install Scrapling browsers (one-time)

```bash
scrapling install
```

### 3. Configure environment variables

```bash
copy .env.example .env
# Edit .env if needed (optional — defaults work out of the box)
```

### 4. Run the server

```bash
python run.py
```

Open **http://localhost:5000** in your browser.

---

## Usage

### Web UI

The frontend has three views accessible from the top navigation bar:

| View | What it does |
|------|-------------|
| **Search** | Enter a query, pick sources and article limit, then watch results stream in |
| **Analyze Text** | Paste any text and run the full NLP pipeline on demand |
| **History** | Browse and re-open previous search jobs |

#### Search flow

1. Type a topic or claim in the search bar (e.g. `"5G towers cause cancer"`)
2. Select sources: **Google News**, **Bing News**, **Reddit** (any combination)
3. Choose a max article count (15 – 60)
4. Click **Search** — a progress bar shows live status
5. Results appear as cards showing summary, key claims, themes, and sentiment
6. Click any card to open the full detail modal with an article excerpt and a link to the original

### REST API

The same functionality is available over HTTP — useful for integrating RDS into a larger pipeline.

#### Start a search job

```http
POST /api/search
Content-Type: application/json

{
  "query": "covid vaccine side effects",
  "sources": ["google_news", "bing_news", "reddit"],
  "max_articles": 30
}
```

Response `202`:
```json
{ "job_id": "d3f1...", "status": "pending" }
```

#### Poll job status / results

```http
GET /api/job/{job_id}
```

Returns the full job object including `articles[]` once `status == "completed"`.

#### Analyze raw text

```http
POST /api/analyze
Content-Type: application/json

{ "text": "Scientists confirmed the drug reduces mortality by 40 percent." }
```

Returns `summary`, `key_claims`, `themes`, `main_theme`, `sentiment`, `sentiment_score`, `reliability_score`.

#### List recent jobs

```http
GET /api/jobs
```

#### Health check

```http
GET /api/health
```

---

## Pipeline Explanation

```
User query
    │
    ▼
┌─────────────────────────────────────┐
│         SOURCE COLLECTION           │
│  Google News RSS · Bing News RSS    │
│  Reddit JSON API                    │
│  (parallel, up to 3 sources)        │
└──────────────┬──────────────────────┘
               │  RawArticle objects
               ▼
┌─────────────────────────────────────┐
│         CONTENT FETCHING            │
│  Scrapling Fetcher (stealth HTTP)   │
│    └─ fallback: trafilatura fetch   │
│  trafilatura extracts main text     │
│  text_cleaner removes noise/HTML    │
└──────────────┬──────────────────────┘
               │  clean_content (str)
               ▼
┌─────────────────────────────────────┐
│         NLP PIPELINE                │
│                                     │
│  ContentFilter  → quality gate      │
│  Summarizer     → abstractive sum.  │
│  ClaimExtractor → key statements    │
│  TopicDetector  → themes / label    │
│  SemanticAnalyzer                   │
│    ├─ SentenceTransformer embedding │
│    └─ sentiment classification      │
└──────────────┬──────────────────────┘
               │  AnalyzedArticle objects
               ▼
┌─────────────────────────────────────┐
│         DEDUPLICATION               │
│  Cosine similarity on embeddings    │
│  threshold: 0.88 (configurable)     │
└──────────────┬──────────────────────┘
               │
               ▼
         JSON response
       (articles array)
```

### NLP models used

| Component | Model | Role |
|-----------|-------|------|
| Summarizer | `sshleifer/distilbart-cnn-12-6` | Abstractive summary (≤160 tokens) |
| Topic detector | `cross-encoder/nli-deberta-v3-small` | Zero-shot multi-label topic classification |
| Embedder | `sentence-transformers/all-MiniLM-L6-v2` | 384-dim vectors for deduplication |
| Sentiment | `distilbert-base-uncased-finetuned-sst-2-english` | Positive / Negative / Neutral |
| NER (claims) | `dslim/bert-base-NER` | Entity recognition used in claim scoring |

All models are **lazy-loaded** on first request and cached for the lifetime of the process. Swap any model by editing `config/config.yaml` — no code changes needed.

---

## Project Structure

```
RDS/
├── run.py                      # Entry point
├── environment.yml             # Conda environment definition
├── requirements.txt            # Pip requirements (subset of above)
├── .env.example                # Environment variable template
│
├── config/
│   ├── config.yaml             # Flask, scraper, NLP, and logging settings
│   └── sources.yaml            # Per-source URLs, limits, and toggles
│
├── app/
│   ├── __init__.py             # Flask app factory + CORS
│   ├── api/routes.py           # All REST endpoints
│   ├── models/schemas.py       # RawArticle · AnalyzedArticle · SearchJob
│   │
│   ├── scraper/
│   │   ├── engine.py           # Job queue (threading), job store, dedup
│   │   ├── pipeline.py         # Per-article fetch → extract → clean
│   │   └── sources/
│   │       ├── base.py         # Abstract BaseSource
│   │       ├── google_news.py  # Google News RSS
│   │       ├── bing_news.py    # Bing News RSS
│   │       └── reddit.py       # Reddit search JSON API
│   │
│   ├── nlp/
│   │   ├── processor.py        # Singleton NLP orchestrator
│   │   ├── summarizer.py       # DistilBART summarisation
│   │   ├── claim_extractor.py  # NER + heuristic claim scoring
│   │   ├── topic_detector.py   # Zero-shot + keyword fallback
│   │   ├── semantic_analyzer.py# Embeddings + sentiment
│   │   └── content_filter.py   # Language detection + quality score
│   │
│   └── utils/
│       ├── logger.py           # Loguru rotating logger
│       └── text_cleaner.py     # HTML stripping, noise removal, sentence split
│
├── templates/index.html        # Single-page frontend
├── static/
│   ├── css/style.css           # Dark-theme styles
│   └── js/app.js               # Vanilla JS (search, polling, modal, history)
│
├── tests/
│   ├── test_scraper.py         # Scraper + schema unit tests (no network)
│   └── test_nlp.py             # NLP heuristic tests (no model downloads)
│
└── logs/                       # Rotating log files (auto-created)
```

---

## Configuration

All tunables live in `config/config.yaml`. Key sections:

```yaml
scraper:
  max_articles_per_source: 15     # articles fetched per source
  request_timeout: 25             # seconds per HTTP request
  dedup_similarity_threshold: 0.88 # cosine sim cutoff for dedup

nlp:
  summarizer_model: sshleifer/distilbart-cnn-12-6
  max_input_chars: 4000           # chars fed to any model
  max_claims: 6                   # key claims extracted per article
  topics:                         # editable topic list for zero-shot
    - politics
    - technology
    - health
    - ...
```

Toggle sources on/off or change their result limits in `config/sources.yaml`.

---

## Running Tests

```bash
conda activate rds-env
pytest tests/ -v
```

Tests cover text-cleaning utilities, schema serialisation, scraper pipeline helpers, and NLP heuristic paths — all without requiring network access or model downloads.

---

## Extending the System

### Add a new scraper source

1. Create `app/scraper/sources/my_source.py` extending `BaseSource`
2. Implement `search(query) -> Iterator[RawArticle]`
3. Register it in `app/scraper/engine.py` → `_SOURCE_CLASSES`
4. Add its config block to `config/sources.yaml`

### Swap an NLP model

Edit the relevant `*_model` key in `config/config.yaml`. The processor reads config at runtime — no restart needed between searches.

### Add a new API endpoint

Add a route function in `app/api/routes.py` on the existing `api_bp` blueprint.

---

## Integration with RDS Pipeline

`AnalyzedArticle` objects expose these fields for downstream RDS modules:

| Field | Type | Description |
|-------|------|-------------|
| `key_claims` | `list[str]` | Extracted factual statements |
| `themes` | `list[str]` | Detected topic labels |
| `main_theme` | `str` | Highest-confidence topic |
| `sentiment` | `str` | `positive` / `negative` / `neutral` |
| `sentiment_score` | `float` | Model confidence |
| `reliability_score` | `float` | Heuristic quality score 0–1 |
| `embedding` | `list[float]` | 384-dim semantic vector |

Use `/api/search` + poll `/api/job/{id}` to get the full articles array as JSON, or import `app.scraper.engine.create_job` directly if embedding RDS as a Python library.
