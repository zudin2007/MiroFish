# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What MiroFish Is

MiroFish is a multi-agent swarm intelligence simulation engine. Users upload seed documents (PDF/MD/TXT), describe a prediction requirement, and the system:
1. Extracts an ontology (entity types + relationships) using an LLM
2. Builds a knowledge graph in Zep Cloud (GraphRAG)
3. Generates OASIS agent profiles (personas) for each entity
4. Runs a dual-platform simulation (Twitter + Reddit) via CAMEL-OASIS
5. Generates a structured report and enables interactive chat with a ReportAgent

## Development Commands

All commands run from the project root unless noted.

### Setup
```bash
npm run setup:all          # Install everything (Node + frontend + backend via uv)
cp .env.example .env       # Then fill in LLM_API_KEY and ZEP_API_KEY
```

### Running
```bash
npm run dev                # Start both frontend (port 3000) and backend (port 5001) concurrently
npm run backend            # Backend only: cd backend && uv run python run.py
npm run frontend           # Frontend only: cd frontend && npm run dev
```

### Backend (Python)
```bash
cd backend
uv sync                    # Install/update Python deps (Python 3.11–3.12, managed by uv)
uv run python run.py       # Start Flask server
uv run pytest              # Run tests
uv run pytest tests/path/to/test_file.py::TestClass::test_method  # Single test
```

### Frontend (Vue 3)
```bash
cd frontend
npm install
npm run dev                # Vite dev server on port 3000
npm run build              # Production build
```

### Docker
```bash
cp .env.example .env       # Configure environment
docker compose up -d       # Pulls ghcr.io/666ghj/mirofish:latest
```
Docker image is published automatically on git tags via `.github/workflows/docker-image.yml`. The volume mount `./backend/uploads:/app/backend/uploads` persists simulation data.

## Architecture

### Backend (`backend/`)

Flask app using the application factory pattern (`app/__init__.py` → `create_app()`). Three blueprints:

| Blueprint | Prefix | File |
|-----------|--------|------|
| `graph_bp` | `/api/graph` | `app/api/graph.py` |
| `simulation_bp` | `/api/simulation` | `app/api/simulation.py` |
| `report_bp` | `/api/report` | `app/api/report.py` |

**Services** (`app/services/`):
- `ontology_generator.py` — LLM call to extract entity/edge types from uploaded documents
- `graph_builder.py` — Creates and populates Zep Cloud knowledge graphs
- `zep_entity_reader.py` — Reads/filters entities from Zep by ontology type
- `oasis_profile_generator.py` — Converts Zep entities into OASIS agent profiles (Reddit JSON + Twitter CSV)
- `simulation_config_generator.py` — LLM-generates full simulation config (time, agent activity, events)
- `simulation_manager.py` — Orchestrates the prepare flow; persists state to `backend/uploads/simulations/<sim_id>/`
- `simulation_runner.py` — Spawns OASIS simulation as a subprocess; monitors actions via `actions.jsonl`; supports IPC for interview/stop
- `simulation_ipc.py` — IPC client to send commands to running simulation process
- `report_agent.py` — ReACT-style report generation using LLM + Zep tools; logs to `agent_log.jsonl`
- `zep_tools.py` — Tools for ReportAgent: graph search, insight forge, panorama, interview
- `zep_graph_memory_updater.py` — Batched write-back of simulation actions into Zep memory

**Models** (`app/models/`):
- `project.py` — `Project` dataclass + `ProjectManager` (file-based persistence in `backend/uploads/projects/`)
- `task.py` — `Task` dataclass + `TaskManager` (in-memory, thread-safe, for tracking async long-running ops)

**Utils** (`app/utils/`):
- `llm_client.py` — Thin wrapper around OpenAI SDK using `Config.LLM_*` variables
- `locale.py` — i18n for backend; reads `locales/*.json`; uses `Accept-Language` header; thread-local locale for background threads
- `file_parser.py` — PDF (PyMuPDF), Markdown, and plain text extraction with charset detection
- `retry.py` — Retry decorator used on LLM calls
- `zep_paging.py` — Paginates Zep API responses

**Async pattern**: Long-running operations (graph build, simulation prepare, report generate) start a `threading.Thread`, create a `Task` in `TaskManager`, and the frontend polls for status. Always capture `get_locale()` before spawning a thread and call `set_locale()` inside it.

**Persistence layout** (all under `backend/uploads/`):
```
projects/<project_id>/           # Project files, extracted text, project.json
simulations/<simulation_id>/     # state.json, simulation_config.json,
                                 # reddit_profiles.json, twitter_profiles.csv,
                                 # actions.jsonl, run_state.json,
                                 # twitter_simulation.db, reddit_simulation.db
reports/<report_id>/             # meta.json, report.md, agent_log.jsonl,
                                 # section_01.md, section_02.md, ...
```

**OASIS simulation scripts** live in `backend/scripts/` and are invoked as subprocesses by `SimulationRunner`. They are not copied into the simulation directory — they are referenced directly from `scripts/`.

### Frontend (`frontend/`)

Vue 3 + Vite + vue-router 4 + vue-i18n 11 + D3.js + Axios.

**Routing** (step-by-step wizard flow):
- `/` → `Home.vue` (history + new project)
- `/process/:projectId` → `MainView.vue` (Steps 1–3: graph build, env setup, simulation prepare)
- `/simulation/:simulationId` → `SimulationView.vue` (Step 3 detail)
- `/simulation/:simulationId/start` → `SimulationRunView.vue` (Step 3 run monitor)
- `/report/:reportId` → `ReportView.vue` (Step 4 report)
- `/interaction/:reportId` → `InteractionView.vue` (Step 5 chat)

**Step components** (inside `MainView.vue`):
- `Step1GraphBuild.vue` — File upload + ontology generation + graph build
- `Step2EnvSetup.vue` — Entity review + simulation prepare
- `Step3Simulation.vue` — Simulation config review + run control
- `Step4Report.vue` — Report generation + display
- `Step5Interaction.vue` — Chat with ReportAgent / interview agents

**API layer** (`src/api/`): Three modules (`graph.js`, `simulation.js`, `report.js`) each import from `src/api/index.js` which configures an Axios instance. The base URL defaults to `http://localhost:5001`; override with `VITE_API_BASE_URL` env var. The Vite dev server proxies `/api` to `localhost:5001`.

**i18n**: Language strings live in `locales/en.json` and `locales/zh.json` (shared between frontend and backend). The `Accept-Language` request header carries the locale from frontend to backend on every request.

**State**: Minimal — `src/store/pendingUpload.js` holds ephemeral upload state. Most state flows through URL params (`projectId`, `simulationId`, `reportId`) and API polling.

**GraphPanel**: D3-based force-directed graph for visualizing Zep knowledge graph nodes/edges.

## Key Conventions

### Configuration
All environment variables are loaded from the project root `.env` file. `Config` class in `backend/app/config.py` is the single source of truth. Any LLM API compatible with the OpenAI SDK format works (configure `LLM_BASE_URL` and `LLM_MODEL_NAME`). The optional `LLM_BOOST_*` variables enable a faster secondary model.

### i18n for all user-facing strings
Backend user-facing strings must use `t('key', **kwargs)` from `app/utils/locale.py` — never hardcode Chinese or English text in API responses. Add keys to both `locales/zh.json` and `locales/en.json`.

### Simulation state machine
`SimulationStatus`: `created → preparing → ready → running → paused/stopped/completed/failed`

The `_check_simulation_prepared()` helper in `simulation.py` is the canonical way to verify all required files exist; use it rather than checking status strings directly.

### Data types
- Projects: `proj_<uuid_hex[:12]>`
- Simulations: `sim_<uuid_hex[:12]>`
- Reports: `report_<uuid_hex[:12]>`
- Tasks: `task_<uuid_hex[:12]>`
- Zep graph IDs are returned by the Zep API and stored as-is.

### LLM calls
All LLM calls go through `app/utils/llm_client.py`. JSON responses from LLMs should be parsed defensively — strip markdown fences before parsing. The retry decorator in `app/utils/retry.py` is used on profile generation and config generation.

### File uploads
Accepted formats: PDF, MD, TXT, Markdown. Max 50 MB per request. Files are saved to `backend/uploads/projects/<project_id>/`. Extracted text is saved separately as `extracted_text.txt` in the same directory.
