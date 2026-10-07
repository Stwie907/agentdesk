# AgentDesk Backend

FastAPI backend for AgentDesk. Runtime V4 plans and executes tasks with tool
permissions, stores execution traces and snapshots, and replays stored plans.
Ollama is the default provider. Explicit Mock mode supports offline demonstrations.

## Setup

The repository CI uses Python 3.11. From `backend/`:

```sh
python -m venv .venv
```

Activate with `source .venv/Scripts/activate` in Windows Git Bash, or
`. .venv/bin/activate` on Linux/macOS. Then install dependencies:

```sh
python -m pip install -r requirements.txt
```

An existing environment can be reused; this feature adds no dependencies.

## LLM configuration

Export settings in the terminal that starts Uvicorn. The backend reads process
environment variables. Root `.env.example` documents defaults; copying it to
`.env` alone does not load settings automatically.

| Variable | Default | Purpose |
| --- | --- | --- |
| `LLM_PROVIDER` | `ollama` | Select `ollama` or `mock`. |
| `OLLAMA_BASE_URL` | `http://localhost:11434` | Base URL without `/api/generate`. |
| `OLLAMA_PLANNER_MODEL` | `qwen2.5:7b` | Model for both Planner entry points. |
| `OLLAMA_TIMEOUT_SECONDS` | `120` | Positive finite timeout for each model request. |
| `DATABASE_URL` | `sqlite:///./agentdesk.db` | Database URL; SQLite paths are relative to the working directory. |

Final Ollama replies use the model stored on the selected Agent. The planner model
setting does not override Agent model selections. Unsupported provider names,
invalid URLs, blank planner models, and nonpositive/nonfinite timeouts raise errors
when the runtime reads settings.

### Ollama mode

Start Ollama with the planner model and the selected Agent's model available.
From `backend/`, using Git Bash or a Unix shell:

```sh
export LLM_PROVIDER=ollama
export OLLAMA_BASE_URL=http://localhost:11434
export OLLAMA_PLANNER_MODEL=qwen2.5:7b
export OLLAMA_TIMEOUT_SECONDS=120
python -m uvicorn app.main:app --reload
```

Connection, timeout, HTTP, and malformed-response errors remain failures. Ollama
errors never silently select Mock mode. The existing worker retry policy applies
to connection failures and timeouts.

### Mock mode

No local model or API key is required. From `backend/`, using Git Bash or a Unix shell:

```sh
export LLM_PROVIDER=mock
python -m uvicorn app.main:app --reload
```

In PowerShell, set `$env:LLM_PROVIDER = "mock"` before running Uvicorn.
Restart the backend after changing shell settings. Return to normal operation
by setting `LLM_PROVIDER=ollama` and restarting the backend.

Mock mode makes no LLM HTTP requests. Its rule-based planner supports one binary
arithmetic operation with signed numbers, optional decimal notation, and `+`, `-`,
`*`, or `/`. Inputs may start with `计算` or `Calculate`. It respects Calculator
permissions. Other input produces a no-tool plan and a fixed reply. Mock mode does
not perform general reasoning, datetime selection, or multi-step natural-language
planning.

| Input | Requirement | Result |
| --- | --- | --- |
| `计算40+2` | Agent allows `calculator`. | Real Calculator output: `42`. |
| `Calculate 40 + 2` | Agent allows `calculator`. | Real Calculator output: `42`. |
| `Hello AgentDesk` | Any Agent. | `[MOCK] AgentDesk demo response. No language model was called.` |
| `计算40+2` | Calculator not allowed. | Fixed `[MOCK]` reply; no tool runs. |

Calculator outputs are real tool results. The Inspector's `plan_started` trace
contains `provider=mock; planner=demo_rules`. Simulated chat replies carry the
`[MOCK]` prefix. Execution history, traces, and snapshots use the existing Runtime
V4 pipeline. Calculator replay re-executes the stored tool plan and returns `42`
without calling the planner or a model again.

## Workbench demo

The backend listens on `http://localhost:8000`. Open `http://localhost:8000/docs`
for Swagger. Use an existing Agent, or create resources in a fresh database:

1. `POST /users`: provide a unique `username` and `email`; record the returned ID.
2. `POST /projects`: provide `name` and set `owner_id` to that user ID; record the project ID.
3. `POST /agents`: provide `name`, that `project_id`, `model: "qwen2.5:7b"`, and
   `allowed_tools: ["calculator"]`.

Start the frontend in another terminal from `frontend/`:

```sh
npm ci
npm run dev
```

At `http://localhost:5173`, select the Agent and submit `计算40+2`. Confirm
`completed`, output `42`, the Mock marker in the trace, and a stored snapshot.
Submit `Hello AgentDesk` to see the explicitly marked fixed reply.

## Health and tests

`GET /health` continues to return `{"status": "ok"}`.

From `backend/`:

```sh
python -m pytest
```

Tests isolate the LLM environment and select providers explicitly. A shell setting
of `LLM_PROVIDER=mock` does not change the existing Ollama contract tests. The suite
does not require a live model.

## Containers

`docker compose up --build backend` builds the service foundation. The current
Compose file does not forward LLM variables or provide Ollama. Use the local
commands for these demos; container integration is the next deployment task.
