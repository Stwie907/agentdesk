# AgentDesk Backend

Minimal FastAPI service foundation for AgentDesk. It contains no LLM, RAG,
MCP, Agent, API key, or external-service integration.

## Requirements

- Python 3.11

## Local development

```sh
python3.11 -m venv .venv
. .venv/bin/activate
python -m pip install -r requirements.txt
python -m uvicorn app.main:app --reload
```

The service listens on `http://localhost:8000`.

## Health check

```http
GET /health
```

```json
{"status": "ok"}
```

## Tests

```sh
python -m pytest
```

## Docker Compose

From the repository root:

```sh
docker compose up --build backend
```
