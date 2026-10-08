# Docker Compose demo

This guide runs the existing FastAPI, React/Vite, and SQLite application with
Docker Compose. Mock mode uses deterministic planning and marked replies; the
Calculator still executes through Runtime V4. No local model or API key is
needed for Mock task execution.

## Requirements

- Docker with Linux containers and Docker Compose v2 supporting `up --wait`.
- Windows Git Bash, or a Unix shell, for the startup script.
- Internet access for the initial image and dependency build.
- Local ports `5173` and `8000` available. Stop native Vite and Uvicorn servers
  before starting these containers.

The Docker workflow installs application dependencies inside images. A host
Python virtual environment, Node.js installation, and Make are not required for
the direct startup command.

## Start the Mock demo

From the repository root:

```sh
sh deployment/start-demo.sh
```

With Make installed, `make demo` runs the same script. The script validates
Compose configuration, builds both services, waits for healthy containers, and
runs an idempotent demo initializer. Repeating it reuses matching demo records
and preserves existing Agent settings.

The initializer creates a User named `agentdesk-demo`, an `AgentDesk Demo`
Project, and a `Demo Agent` with Calculator permission. It prints their actual
IDs. Do not assume that the Agent ID is `1` in an existing volume.

Open `http://localhost:5173` and select `Demo Agent`. Submit these new tasks:

| Task | Expected result |
| --- | --- |
| `Calculate 40 + 2` or `计算40+2` | Completed, output `42`, Calculator step, and `provider=mock` in the initial trace. |
| `Hello AgentDesk` | Completed, reply starting with `[MOCK]`, and a stored snapshot. |
| Replay the Calculator execution | A new completed execution with output `42` and a link to its source. |

The startup script always loads `docker-compose.mock.yml`, which explicitly
selects Mock even when the shell or root `.env` contains `LLM_PROVIDER=ollama`.
Unsupported Mock inputs produce a fixed marked reply rather than general LLM
reasoning. The application itself still defaults to Ollama.

## Check services and run the smoke check

```sh
docker compose ps
docker compose exec -T frontend nginx -t
docker compose -f docker-compose.yml -f docker-compose.mock.yml exec -T backend python -m app.check_demo --base-url http://frontend
```

The final command returns JSON containing `"status": "passed"` and the actual
Agent, execution, and replay IDs. It checks the served React build and assets,
API health, Agent selection, Calculator execution, Mock trace marker, marked
chat reply, snapshots, and replay history. It creates demo executions during
the check. `make demo-check` runs the same command.

The following addresses have different purposes:

| Address | Purpose |
| --- | --- |
| `http://localhost:5173` | Browser workbench and API proxy. |
| `http://localhost:5173/healthz` | Nginx/frontend health. |
| `http://localhost:5173/health` | Backend health through the frontend proxy. |
| `http://localhost:8000/health` | Direct backend health. |
| `http://localhost:8000/docs` | Direct API documentation. |
| `http://backend:8000` | Internal Compose backend address. |

Nginx forwards API paths and query strings to the backend service. It starts
after backend health succeeds. Its proxy read timeout allows for local planning,
final replies, and the existing retry policy with the default LLM timeout.

## Persistence and stop

Compose fixes the container database URL to `sqlite:////data/agentdesk.db` and
mounts `/data` from the project's `agentdesk-data` named volume. Native
`backend/agentdesk.db` is a separate database and is not copied into the image.

Stop containers while retaining data:

```sh
docker compose down
```

To verify persistence after a successful smoke check:

```sh
docker compose down
sh deployment/start-demo.sh
docker compose -f docker-compose.yml -f docker-compose.mock.yml exec -T backend python -m app.check_demo --base-url http://frontend --verify-persistence
```

The persistence option checks that earlier Calculator, Mock chat, and linked
replay records and their snapshots are present before creating new test tasks.
Keep the same repository directory and Compose project name across runs so
Compose reuses the same volume.

## Switch to local Ollama

Use the base Compose file without the Mock override. Ollama must run on the host,
have `qwen2.5:7b` available for `Demo Agent`, and accept connections from Docker.
The container uses `COMPOSE_OLLAMA_BASE_URL`, whose default is
`http://host.docker.internal:11434`; native `OLLAMA_BASE_URL=localhost` is kept
separate because container localhost refers to the container itself.

From Git Bash or a Unix shell:

```sh
LLM_PROVIDER=ollama docker compose up --build --detach --wait --wait-timeout 180 backend frontend
```

This recreates the backend with normal Ollama settings and retains its data
volume. On a fresh volume, create demo records with:

```sh
docker compose exec -T backend python -m app.seed_demo
```

Agent model selections continue to control final replies; the planner model
setting does not overwrite them.

Ollama binds to host loopback by default. If Docker cannot reach it, configure a
Docker-reachable bind address using `OLLAMA_HOST` and restart Ollama. The
[official Ollama FAQ](https://docs.ollama.com/faq#how-do-i-configure-ollama-server)
describes Windows application and Linux service configuration. Mock mode works
without changing Ollama settings. Backend connection and timeout errors remain
failures and do not silently select Mock.

Return to Mock using `sh deployment/start-demo.sh`.

## Configuration

Compose reads a root `.env` for interpolated values; native Uvicorn reads values
exported into its own terminal. Copying `.env.example` to `.env` does not activate
native backend settings. The script does not require a `.env` file.

| Setting | Container behavior |
| --- | --- |
| `LLM_PROVIDER` | Base Compose defaults to `ollama`; the Mock override forces `mock`. |
| `COMPOSE_OLLAMA_BASE_URL` | Container Ollama URL; defaults to the host Docker gateway. |
| `OLLAMA_PLANNER_MODEL` | Defaults to `qwen2.5:7b`. |
| `OLLAMA_TIMEOUT_SECONDS` | Defaults to `120` seconds per model request. |
| `DATABASE_URL` | Container value is fixed to the SQLite volume; the native reference value does not override it. |

## Troubleshooting

- Docker connection errors: start Docker Desktop/the Docker daemon and confirm
  `docker compose version` works.
- Port already allocated: stop the native frontend/backend or other containers
  using `5173` or `8000`, then repeat startup.
- Unhealthy backend: inspect `docker compose logs backend`. Health requires a
  started application; Ollama is not part of the health check.
- API `502`: inspect `docker compose ps` and `docker compose logs frontend
  backend`; verify both services are healthy and run the Nginx config check.
- Missing `Demo Agent`: repeat startup or rerun the initializer. A demo User
  identity conflict is reported without changing that User.
- A changed Demo Agent no longer allows Calculator: the initializer preserves
  existing settings; restore Calculator permission explicitly before checking
  the arithmetic demo.

## CI verification

The existing `structure` job runs backend tests, frontend tests, and the
production frontend build. The `compose-demo` job builds and starts actual
containers, validates Nginx and the published health endpoints, runs the Mock
smoke check, recreates the services, and verifies persisted executions and
snapshots. It prints container logs and removes its temporary CI volume at the
end. Normal local shutdown retains the volume.

References: [Compose startup order](https://docs.docker.com/compose/how-tos/startup-order/),
[Compose networking](https://docs.docker.com/compose/how-tos/networking/), and
[Nginx proxy module](https://nginx.org/en/docs/http/ngx_http_proxy_module.html).
