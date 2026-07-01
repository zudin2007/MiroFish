# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

MiroFish is a swarm-intelligence prediction engine. It ingests seed material (documents, news, novels) and a natural-language prediction requirement, builds a knowledge graph of the entities involved, generates LLM-driven agent personas from that graph, runs them through a multi-round social-media simulation (Twitter/Reddit style, powered by CAMEL-AI's OASIS), and then has a ReAct-style report agent synthesize a prediction report from the simulated world (with follow-up chat/interview support). A secondary, unrelated feature (`/trading`) turns TradingView webhook alerts into Binance/OKX orders.

Stack: Flask (Python) backend + Vue 3 (Vite) frontend, with Zep Cloud as the graph/memory store and an OpenAI-SDK-compatible LLM for all generation steps.

## Common Commands

Run all commands from the repo root unless noted.

```bash
# Install everything (root npm scripts + frontend npm + backend uv env)
npm run setup:all

# Install pieces separately
npm run setup           # root + frontend npm install
npm run setup:backend   # cd backend && uv sync

# Run both servers concurrently (frontend :3000, backend :5001)
npm run dev

# Run individually
npm run backend    # cd backend && uv run python run.py
npm run frontend   # cd frontend && npm run dev

# Frontend production build
npm run build       # cd frontend && npm run build
```

Backend-only, from `backend/`:
```bash
uv sync                      # install/update Python deps (uv.lock)
uv run python run.py         # start Flask app (reads ../.env)
uv run python scripts/test_profile_format.py   # ad-hoc script, not a pytest suite
```

There is no wired-up lint/test/typecheck command for either side (pytest is listed as a dev dependency in `backend/pyproject.toml` but there is no test suite under `backend/` beyond the manual `scripts/test_profile_format.py` script, and the frontend has no configured linter or test runner). Don't invent commands that don't exist — verify manually by running the servers and exercising the flow (see Docker option below for a containerized run).

Docker (source of truth is `Dockerfile` / `docker-compose.yml`):
```bash
cp .env.example .env   # fill in required keys first
docker compose up -d   # pulls prebuilt image, maps 3000/5001
```

### Required environment variables (`.env` at repo root)

Backend loads `.env` from the project root, not `backend/.env` (`backend/app/config.py`). Required: `LLM_API_KEY`, `LLM_BASE_URL`, `LLM_MODEL_NAME` (any OpenAI-SDK-compatible endpoint — Alibaba Bailian/Qwen is the documented default) and `ZEP_API_KEY` (Zep Cloud). `Config.validate()` in `backend/app/config.py` fails fast on startup if either LLM or Zep keys are missing. Trading feature vars (`TRADING_EXCHANGE`, `BINANCE_*`/`OKX_*`, `TRADING_WEBHOOK_SECRET`) are optional and independent of the simulation pipeline.

## Architecture

### Backend layout (`backend/app/`)

- `__init__.py` — Flask app factory (`create_app`). Registers four blueprints under `/api/*`, enables CORS for all `/api/*` origins, and registers a process-cleanup hook (`SimulationRunner.register_cleanup()`) so background simulation subprocesses are killed on server shutdown.
- `api/` — one Flask blueprint per pipeline stage, thin route handlers that delegate to `services/`:
  - `graph.py` (`/api/graph`) — project CRUD, ontology generation, graph building, task polling.
  - `simulation.py` (`/api/simulation`) — by far the largest file (~2700 lines): entity browsing, simulation prepare/create, agent profile generation, start/stop, live run status, timelines/posts/comments, and agent interviews.
  - `report.py` (`/api/report`) — report generation, progress/section streaming, report chat, tool search/statistics.
  - `trading.py` (`/api/trading`) — unrelated webhook-to-exchange bridge (see below).
- `services/` — all business logic; routes should stay thin.
- `models/` — `Project` (`ProjectManager`, file-backed under `backend/uploads/projects/<id>/`) and `Task`/`TaskManager` (in-memory singleton for tracking long-running async jobs like graph builds).
- `utils/` — `llm_client.py` (OpenAI-SDK wrapper for whatever `LLM_*` config is set), `locale.py` (i18n for LLM prompts and API messages, backed by root `locales/*.json`), `logger.py`, `retry.py`, `file_parser.py` (PDF/MD/TXT ingestion), `zep_paging.py` (pagination helper over Zep's node/edge APIs).

### The five-stage pipeline

The frontend's `Step1..Step5` components and backend blueprints mirror one linear pipeline (see README "Workflow" section and `frontend/src/router/index.js`):

1. **Graph Building** (`graph.py` + `OntologyGenerator` + `GraphBuilderService` + `TextProcessor`): uploaded documents are chunked, an LLM proposes entity/relationship *ontology* types tailored for social-simulation (system prompt in `ontology_generator.py`), then `GraphBuilderService` pushes the text as episodes into a Zep Cloud "standalone graph" so Zep extracts entities/edges per that ontology.
2. **Environment Setup** (`simulation.py` + `ZepEntityReader` + `OasisProfileGenerator` + `SimulationConfigGenerator`): entities are read back from Zep and filtered to the ontology's entity types (`ZepEntityReader`), then converted into OASIS agent personas (`OasisProfileGenerator`, enriching each entity with extra Zep lookups) and into a `SimulationParameters` config (agent activity level, time/round settings, injected events, platform config) via LLM (`SimulationConfigGenerator`).
3. **Simulation** (`SimulationManager` + `SimulationRunner` + `backend/scripts/run_*.py`): `SimulationManager` prepares per-platform (Twitter/Reddit) profile CSV/JSON files and the config JSON under `backend/uploads/simulations/<sim_id>/`. `SimulationRunner` then launches the actual OASIS simulation as a **separate subprocess** (`run_twitter_simulation.py` / `run_reddit_simulation.py` / `run_parallel_simulation.py`), because OASIS's asyncio simulation loop needs to run independently of the Flask request/response cycle and survive polling. Each script logs every agent action to `actions.jsonl` and simulation state to `run_state.json` inside the sim directory; the Flask side polls these files for live status.
4. **Simulation ↔ Backend IPC** (`simulation_ipc.py`): once a simulation subprocess finishes its scripted rounds, it doesn't exit — it idles waiting for commands (interview a single agent, batch-interview, or close the environment). Communication is a simple **file-based command/response protocol**: Flask writes JSON commands into `commands/`, the subprocess polls that directory, executes, and writes JSON into `responses/`; Flask polls `responses/` for the result. This exists because there's no persistent socket/RPC layer between the Flask process and the simulation subprocess — see the module docstring in `simulation_ipc.py`.
5. **Memory sync** (`ZepGraphMemoryUpdater` / `ZepGraphMemoryManager`): agent actions from the running simulation are converted into natural-language episode text and streamed back into the same Zep graph in the background (queue + worker thread), so the graph reflects what happened during simulation and the Report Agent can query it afterward.
6. **Report Generation** (`report.py` + `report_agent.py` + `zep_tools.py`): `ReportAgent` first plans a report outline, then generates each section using a ReAct loop (multiple rounds of think → call a Zep retrieval tool → reflect) via tools in `zep_tools.py` (`InsightForge` deep hybrid search, `PanoramaSearch` broad search including stale content, `QuickSearch`). The same agent/tools back the post-report chat and "interview any agent" features. `ReportLogger` writes an `agent_log.jsonl` per report for auditability, surfaced via `/api/report/<id>/agent-log`.

### Async/long-running work pattern

Two different mechanisms are used depending on how long the work runs:
- **Short-to-medium async work** (ontology generation, graph building): tracked via `TaskManager` (in-memory singleton, `models/task.py`), polled through `/api/graph/task/<task_id>`.
- **Long-running, stateful work** (the simulation itself): run as an OS subprocess managed by `SimulationRunner`, not a Task — because it must survive independently of any single HTTP request, needs true parallelism (OASIS's asyncio loop), and needs bidirectional interaction afterward (the IPC protocol above). `SimulationManager` and `SimulationRunner` are separate: the former prepares config/profiles, the latter owns the subprocess lifecycle.

### Trading feature (`trading.py` / `trading_manager.py` / `binance_service.py` / `okx_service.py`)

Independent of the simulation pipeline. `TradingManager` (module-level singleton via `get_trading_manager()`) receives TradingView webhook alerts at `/api/trading/webhook`, validates a shared secret (`TRADING_WEBHOOK_SECRET`) with `hmac`, and dispatches to whichever exchange service `TRADING_EXCHANGE` selects (`binance` or `okx`) — both take the same payload shape (see the docstring at the top of `trading_manager.py`). Order history is kept in an in-memory bounded deque (`TRADING_MAX_HISTORY`).

### Frontend (`frontend/src/`)

Vue 3 + Vite, no Vuex/Pinia — cross-step handoff uses `store/pendingUpload.js` plus route params (`projectId`, `simulationId`, `reportId` in `router/index.js`) rather than a global store. `api/*.js` are thin axios wrappers per backend blueprint (`graph.js`, `simulation.js`, `report.js`, `trading.js`), mirroring the backend's blueprint split. `components/Step1GraphBuild.vue` … `Step5Interaction.vue` implement the five pipeline stages inside `views/MainView.vue` (route name `Process`); `views/SimulationView.vue`/`SimulationRunView.vue`, `ReportView.vue`, `InteractionView.vue`, and `TradingDashboard.vue` are the corresponding standalone routes.

### i18n

Root-level `locales/{en,zh}.json` + `locales/languages.json` are shared by both sides: the frontend loads them via `vue-i18n` (`frontend/src/i18n/index.js`, glob-imports every locale file except `languages.json`), and the backend's `utils/locale.py` loads the same files to translate API messages and to steer LLM prompts by language (`get_language_instruction()`), keyed off the `Accept-Language` request header (falls back to thread-local storage for background threads, since `set_locale`/`get_locale` needs to work outside a Flask request context — e.g. inside the simulation subprocess or background workers). Default locale is `zh`. When adding user-facing strings, add keys to both locale JSON files.

### Unrelated content in this repo

`docs/` and `static/pages/` contain a large set of personal finance/health HTML dashboards unrelated to the MiroFish application; `docs/` is deployed as-is to GitHub Pages by `.github/workflows/pages.yml` whenever files under `docs/**` change on `main`. Don't assume these are part of the MiroFish product surface.
