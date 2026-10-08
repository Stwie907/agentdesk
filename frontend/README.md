# AgentDesk Frontend

React and TypeScript execution workbench for AgentDesk. It supports task
submission, execution history, filters, pagination, execution inspection,
structured traces, snapshots, replay, cancellation, retry, and automatic refresh.
The Agent Memory panel lists, adds, and deletes persistent memories for the Agent
selected in the task form.

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
`/agents`, `/executions`, and `/memories` to `http://127.0.0.1:8000`. If those requests report
`ECONNREFUSED` or status `502`, confirm that the backend completed startup.

## Agent Memory

Select an Agent in the task form. Its memories load below that form. Enter, for
example, `I prefer concise Python answers.` and select **Save memory**. Content
must be non-blank and at most 2000 characters after trimming. Saving the same
content reuses the existing memory; a canonical `User's name is ...` entry follows
the backend's existing name replacement policy.

**Reload memories** loads the latest records, including changes made through
other API clients. **Delete memory** requires inline confirmation and sends the
selected Agent ID. A failed write retains the draft or record and is not retried
automatically. Switching Agents clears drafts and ignores responses from the
previous selection.

Memories use the existing backend SQLite database. In Mock mode, Runtime logs
can confirm relevant memory retrieval, but the reply remains the fixed `[MOCK]`
message. Use the existing local Ollama provider for model-generated replies.

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
