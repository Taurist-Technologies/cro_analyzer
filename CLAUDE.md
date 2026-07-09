# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

CRO Analyzer is a FastAPI backend that performs **deep, PDP-focused CRO audits**: given a product detail page URL, it captures the page on desktop and mobile with Playwright, extracts machine-verified facts (schema.org data, buy-box layout, reviews, shipping info, real performance metrics), and asks Claude (Anthropic) to produce **exactly 5 prioritized quick wins** plus scorecards. It is designed to be driven from a chat widget on the Taurist website.

**Architecture:** FastAPI API + Celery workers + Redis (queue, cache, rate limiting). One Claude call per analysis with a prompt-cached system rubric and schema-enforced structured output.

## Commands

```bash
# Development (sync mode, no Redis/Celery needed)
uvicorn main:app --reload --host 0.0.0.0 --port 8000

# Production stack
docker-compose up                          # Redis + API + workers + Flower
celery -A core.celery worker --loglevel=info   # worker by hand

# Tests
python3 -m pytest tests/ -q               # unit + API tests (fast)
python3 -m pytest tests/test_pipeline_integration.py -q  # end-to-end with real Chromium, Claude mocked

# Setup
pip install -r requirements.txt
playwright install chromium
cp .env.example .env                       # set ANTHROPIC_API_KEY
```

## Request Flow (async mode — the chat path)

1. `POST /analyze/async` → validates + normalizes URL (SSRF guard, tracking-param strip), submits Celery task, returns `task_id`
2. Client either polls `GET /analyze/status/{task_id}` or opens `GET /analyze/stream/{task_id}` (SSE) for live progress text
3. Worker: cache check → capture desktop + mobile **in parallel contexts** (overlay dismissal, lazy-load scroll, above-fold + full-page shots, buy-box crop) → deterministic fact extraction (JSON-LD + DOM) → PDP detection (non-PDPs return early without an API call) → add-to-cart click test → one Claude call with structured output → exactly 5 quick wins
4. Result cached 24h by normalized URL; screenshots stored separately under the task id for 1h (`GET /analyze/screenshots/{task_id}`)
5. `POST /generate-pdf/{task_id}` renders a PDF report

## Module Map

- `analyzer/pdp/` — the analysis pipeline
  - `extractor.py` — JSON-LD Product parsing, single-pass DOM fact extraction (buy box, price, gallery, reviews, shipping, variants, trust), real perf metrics (LCP/CLS/TTFB via injected observers), PDP detection
  - `capture.py` — parallel desktop/mobile capture, fixed 5-shot list, ATC interaction test, redirect SSRF re-check
  - `prompts.py` — static PDP expert rubric (prompt-cached via `cache_control`) + user-content builder
  - `schema.py` — JSON schema for `output_config.format` (structured outputs — **no JSON repair layer exists or should be added**)
  - `analysis.py` — orchestrator + AsyncAnthropic call + exactly-5 enforcement; `analyze_url_standalone()` is the sync-endpoint path
  - `knowledge.py` — 3-tier knowledge grounding: proprietary audit patterns (Qdrant `taurist_audit_patterns`, built from the Notion audit library) → CRO knowledge brain (Qdrant `slash_cro_knowledge`) → built-in expert rubric. Queries are built from observed page facts; precedence is applied per element category; every snippet carries provenance so Claude cites the source client. **Must never fail an analysis** — returns None (tier 3) on any error/timeout/missing config
- `data/audit_library/*.json` — extracted e-comm audit pattern corpus (source of truth is Notion; re-extract + re-run `scripts/sync_audit_library.py` when new audits land)
- `scripts/sync_audit_library.py` — embeds the corpus and upserts into Qdrant (deterministic IDs; re-sync updates, never duplicates)
- `tasks/analysis.py` — thin Celery task: URL safety, cache, timeout (one retry), progress states
- `core/browser.py` — **per-worker-process** persistent event loop + persistent Chromium (recycled by use count/age). Never create a new event loop per task; always use `get_worker_loop()`
- `core/cache.py` / `core/celery.py` — Redis client, Celery config
- `api/routes.py` — endpoints; `api/security.py` — X-API-Key auth (`API_AUTH_KEY`) + Redis per-IP rate limit (`RATE_LIMIT_PER_MINUTE`)
- `utils/net.py` — `normalize_url()` (cache keys) + `validate_public_url()` (SSRF). Both must be applied to any new endpoint that fetches URLs
- `utils/testing/overlays.py` — popup/cookie-banner dismissal before screenshots
- `utils/reporting/pdf.py` — PDF report (reads the new result shape; keeps fallbacks for cached old-shape results)
- `config.py` — all settings via pydantic-settings; see `.env.example`

## Key Technical Rules

- **Model**: `settings.ANTHROPIC_MODEL` (`claude-opus-4-8`), `max_tokens` 8000, structured outputs via `output_config={"format": {"type": "json_schema", ...}}` — responses are schema-valid by construction, parse with plain `json.loads`
- **Prompt caching**: the system rubric in `prompts.py` must stay byte-stable; put anything per-request in the user message
- **Facts are ground truth**: the prompt tells Claude extracted facts are authoritative. If you extend the extractor, keep outputs conservative — `found: false` must mean "not detected", never a guess
- **Time budget**: navigation `domcontentloaded` + bounded settle; per-attempt `ANALYSIS_TIMEOUT` (150s), one retry, Celery hard limit 360s. Don't reintroduce multi-minute retries — this backs a chat UX
- **Screenshots**: max 5 images per Claude call (desktop fold/full, mobile fold/full, buy-box crop), JPEG ≤1800px via `resize_screenshot_if_needed`
- **ChromaDB / historical patterns were removed deliberately** — do not re-add without an explicit decision
- **Security**: every URL fetched must pass `validate_public_url` at submission AND the redirect re-check in capture (`_recheck_final_url`). Auth (`require_api_key`) + rate limiting stay on all `/analyze/*`, `/generate-pdf`, and `/status/detailed` endpoints; only `/` and `/health` are open. Rate-limit client IP is resolved via `TRUSTED_PROXY_DEPTH` (not the spoofable first XFF entry). **Residual risk**: DNS rebinding — validation and the browser resolve DNS independently, so a hostile resolver could return a public IP to the check and a private one to the fetch. The redirect re-check and literal-IP checks cover the common cases; pin resolution at the browser layer if this becomes a concern.

## Response Shape (SUCCESS result)

```json
{
  "status": "success | not_product_page",
  "url": "...", "analyzed_at": "...", "page_title": "...",
  "total_issues_identified": 12,
  "issues": [ { "title", "element", "viewport", "whats_wrong", "why_it_matters",
                "recommendations": [], "suggested_copy", "impact", "effort",
                "priority_score", "priority_rationale" } ],
  "scorecards": { "buy_box": {}, "product_content": {}, "social_proof": {},
                   "mobile_experience": {}, "page_speed": {} },
  "executive_summary": { "overview": "", "how_to_act": "" },
  "conversion_rate_increase_potential": { "percentage": "", "confidence": "", "rationale": "" },
  "product": { "name": "", "price": "", "availability": "", "rating_value": "", "review_count": "" },
  "performance": { "desktop": {}, "mobile": {} },
  "add_to_cart_test": { "attempted": true, "cart_responded": true, "detail": "" },
  "screenshots_url": "/analyze/screenshots/{task_id}"
}
```

`issues` always contains exactly 5 entries on success. `not_product_page` results carry a user-facing `message` for the chat to relay and are produced **before** any Claude call.

## Environment Variables

See [.env.example](.env.example). Required: `ANTHROPIC_API_KEY`; for async mode: `REDIS_URL`, `CELERY_BROKER_URL`, `CELERY_RESULT_BACKEND`. Production should set `API_AUTH_KEY` and keep `RATE_LIMIT_PER_MINUTE` > 0.

## Testing Notes

- `tests/test_pipeline_integration.py` runs the real pipeline against `tests/fixtures/pdp.html` on a local server with `_call_claude` monkeypatched — use it as the template for pipeline changes. It also asserts non-PDP pages never reach the API.
- The fixture server is loopback, so tests monkeypatch `capture._recheck_final_url`; production keeps the check.
- If you bump `playwright`, re-run `playwright install chromium` — the pinned version must match the installed browser revision.
