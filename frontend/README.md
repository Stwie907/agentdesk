# AgentDesk Frontend

React and TypeScript execution workbench for AgentDesk. It supports task
submission, execution history, filters, pagination, execution inspection,
structured traces, snapshots, replay, cancellation, retry, and automatic refresh.

## Requirements

- Node.js 24.15 or later, below Node.js 25.
- npm 11 or later.

## Local development

From `frontend/`:

```sh
npm ci
npm run dev
```

Open the Local URL printed by Vite, normally `http://localhost:5173`.
Start the [backend](../backend/README.md) in a separate terminal. Vite proxies
`/agents` and `/executions` to `http://127.0.0.1:8000`. If those requests report
`ECONNREFUSED` or status `502`, confirm that the backend completed startup.

## Tests and production build

```sh
npm test
npm run build
```

## Docker Compose

From the repository root:

```sh
sh deployment/start-demo.sh
```

This builds the frontend and backend, waits for health, and initializes a
`Demo Agent` in Mock mode. Open `http://localhost:5173`.

The production container serves the Vite build with Nginx. `nginx.conf` forwards
API paths to the `backend:8000` Compose service, preserving paths and query
strings. It provides a `/healthz` endpoint for the frontend container and forwards
`/health` to the backend. The static workbench and API share the same browser
origin; the browser does not need to resolve Docker service names.

See [the Docker Compose guide](../docs/docker-compose-demo.md) for normal Ollama
mode, persistence, smoke checks, shutdown, and troubleshooting.
