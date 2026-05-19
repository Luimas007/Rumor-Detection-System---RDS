# This file is intentionally empty.
# The fetch + extract + preprocess pipeline now lives entirely in:
#   app/scraper/engine.py   (orchestration, phases 1-3)
#   app/scraper/fetcher.py  (HTTP layer)
#   app/scraper/extractor.py (content extraction)
#   app/preprocessor/       (cleaning + deduplication)
