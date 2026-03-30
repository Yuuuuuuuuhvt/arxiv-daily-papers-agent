# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
# Run the full pipeline (requires OPENROUTER_API_KEY env var)
python -m src.main

# Skip the expensive DeepResearch stage
SKIP_DEEP_RESEARCH=1 python -m src.main

# Override report date (default: today)
REPORT_DATE=2026-03-28 python -m src.main

# Run tests
pytest tests/ -v
```

## Architecture

Fully automated arXiv paper discovery pipeline for three research directions: Embodied AI, World Models, Autonomous Driving. Runs daily via GitHub Actions cron (UTC 05:30 weekdays).

**Pipeline flow** (sequential, in `src/main.py::run_pipeline()`):

```
Fetch (API+RSS) → Dedup → Relevance Filter → Deep Analysis → PDF Download
  → DeepResearch (core papers only) → Report → Email → Git Push
```

**Key design decisions:**

- **Hybrid fetch**: arXiv API (keyword search) + RSS feeds (announce type metadata) combined for both precision and recency
- **3-tier relevance**: LLM classifies papers as `core` / `peripheral` / `not_relevant`. Only core papers get DeepResearch (expensive). Both core and peripheral get Deep Analysis
- **PDF via base64**: PDFs are downloaded locally and base64-encoded before sending to OpenRouter, avoiding server-side URL fetch failures (502s). Files >15MB degrade from `native` to `pdf-text` engine
- **Concurrency**: `asyncio.Semaphore` limits parallel LLM calls (`max_concurrent_llm=10`) and PDF processing (`max_concurrent_pdf=5`)
- **Fail-safe**: Every LLM stage has fallback defaults — parse failures default to `peripheral`, analysis failures use safe defaults, DeepResearch falls back from PDF to text-only

**Data storage**: `data/` is a git submodule (separate repo). Contains `papers_index.json` (cumulative dedup index), `reports/YYYY-MM-DD.md`, and `pdfs/`. CI pushes to both repos using PAT_TOKEN.

## Coding Conventions

- `from __future__ import annotations` at top of every file; use `X | None` not `Optional[X]`
- Dataclasses for models (not Pydantic) — keep dependencies minimal
- Async for all I/O; pipeline orchestration uses `asyncio.gather` + `Semaphore`
- Logging via `logging.getLogger(__name__)` — JSON-formatted output (`ts`, `level`, `stage`, `msg`). Never use `print()`
- All tunable parameters (model IDs, thresholds, keywords, batch sizes) live in `config/config.yaml` — don't hardcode
- Prompts are plain text files in `prompts/` loaded via `config.load_prompt()` — edit prompts to change LLM behavior, not code
- Templates use Jinja2: `autoescape=False` for Markdown, `autoescape=True` for HTML email. Business logic stays in `report_generator.py::_paper_view()`, not in templates
- Use `pathlib.Path` for all file paths (Windows + Linux compatibility)

## Extension Patterns

**Adding a research direction**: Add keyword block in `config/config.yaml` under `research_directions` → update `prompts/relevance_filter.txt` → add display name in `report_generator.py` `DIRECTION_DISPLAY` dict.

**Adding a pipeline stage**: Create `src/new_stage.py` with async functions → wire into `main.py::run_pipeline()` → add `Semaphore` for LLM/network calls → add config keys if needed.

**Changing LLM behavior**: Edit prompt files in `prompts/`. Change model via `models.*.model_id` in config.yaml. Parsing changes go in `_parse_response()` / `_parse_analysis()` — always handle malformed JSON.

## Known Constraints

- `papers_index.json` is the single source of truth for dedup. If corrupted/deleted, all papers get reprocessed. A `.bak` backup is created on every save
- Git push only runs in CI (`GITHUB_ACTIONS` env var check)
- `analyze_all()` and `generate_all_deep_research()` are legacy serial wrappers, unused by the pipeline — dead code kept for standalone testing
- LLM retries: 3 attempts with exponential backoff (2s/4s/8s) for 429 and 5xx errors
- arXiv `api_delay_seconds` (default 3s) and PDF download semaphore (default 5) prevent rate limiting
