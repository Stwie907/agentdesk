# AgentDesk MCP order server

This independent server uses the official
Python SDK (`mcp==2.3.0`). It exposes `get_order(order_id)` over stdio and serves
synthetic, read-only local order fixtures. It makes no model or business API calls.

## Docker check

From the repository root, using Windows Git Bash or a Unix shell:

```sh
sh deployment/check-mcp.sh
```

Expected output includes:

```json
{
  "status": "passed",
  "transport": "stdio",
  "tool_names": ["get_order"],
  "checks_passed": 8
}
```

The actual output also records the negotiated protocol version, check names,
and sample order ids/statuses/source. The SDK client launches `server.py` as a
real subprocess, negotiates the protocol, lists tools, and calls `get_order`.
It closes the server process after checking. The temporary Docker container is
removed after the command finishes.

The `mcp-check` service belongs to an optional `mcp` profile. Normal application
startup excludes it. Explicitly running the service activates its profile:

```sh
docker compose run --build --rm --no-deps -T mcp-check
```

Backend, frontend, Ollama, and a Windows virtual environment are not required
for this command. No MCP port is published and no application database is mounted.
The service uses its own dependency environment, preserving backend package pins.

## Tool contract

`get_order` requires a string matching `^DEMO-[0-9]{4}$`.

| Id | Demo status | Demo total |
| --- | --- | --- |
| DEMO-1001 | shipped | CNY 129.00 |
| DEMO-1002 | processing | CNY 59.00 |

Successful calls return structured data with `source`, `order_id`, `status`,
`currency`, `total`, and `items`. The output schema comes from a Pydantic model;
`source` is always `demo_fixture`. These examples represent synthetic data,
not actual customer orders, payment amounts, or live logistics information.

The tool advertises read-only, non-destructive, idempotent, closed-world hints.
Its implementation only reads fixture data; hints describe behavior rather than
implementing access control.

- `DEMO-9999`: valid id format but no matching demo record; returns a tool error.
- Missing `order_id`, an integer, or a malformed id: returns a tool error.
- Failed tool calls have `is_error=true` and no successful structured order.

Fixture schema version 1 requires unique demo order ids and valid typed fields.
Startup rejects malformed or duplicated fixtures. Returned order/item data is
copied so calls cannot modify cached fixture contents.

Stdout is reserved for JSON-RPC protocol messages. Human-readable server logging
uses stderr. Starting `server.py` directly waits for an MCP client and does not
open a browser page.

## Checks and tests

The protocol check validates eight areas:

1. Tool discovery and input/output schemas.
2. Read-only tool metadata.
3. The shipped demo order.
4. The processing demo order.
5. A missing demo order.
6. A malformed id.
7. A missing argument.
8. An argument with the wrong type.

Run unit and protocol tests in the same Docker environment:

```sh
docker compose run --build --rm --no-deps -T mcp-check \
  python -m unittest discover -s tests -v
```

Equivalent Makefile commands are `make mcp-check` and `make mcp-test`. CI runs
both in a separate `mcp-tools` job. Tests cover fixture validation and isolation,
MCP error responses, session reuse, actual stdio subprocesses, and checker failure
and timeout behavior.

Checker exit codes are `0` for success, `1` for connection/protocol/check failure,
and `2` for invalid command-line configuration. `--timeout` defaults to 30 seconds
for the complete check. Failure output includes `status: failed` and a diagnostic.

## Optional native setup

Use a separate MCP environment with Python 3.11 or newer. From the repository
root in Windows Git Bash:

```sh
cd mcp-server
python -m venv .venv
source .venv/Scripts/activate
python -m pip install -r requirements.txt
python check.py
python -m unittest discover -s tests -v
```

Unix environments use `source .venv/bin/activate`. The Docker workflow above
handles the environment automatically and is the simplest way to reproduce CI.

The native backend automatically detects `mcp-server/.venv`. For another location,
export `MCP_PYTHON` as its absolute Python executable path before starting Uvicorn.
Docker installs its own isolated SDK environment. `MCP_TIMEOUT_SECONDS` defaults
to 30 positive finite seconds. See [backend setup](../backend/README.md).

## Agent Runtime integration

The backend registers `get_order` as a normal permission-controlled tool. Its
adapter invokes `client.py` using the isolated MCP environment. Each call starts
the independent server, performs MCP discovery and `tools/call`, validates the
typed order response, and closes the session/server. The backend does not load
order fixtures directly or install the SDK into its own dependency environment.

Start the Mock workbench with `sh deployment/start-demo.sh`, select `MCP Order Agent`,
and submit `Get order DEMO-1001`, `Get order DEMO-1002`, or `查询订单DEMO-1001`.
Successful outputs are JSON containing the synthetic order. `Get order DEMO-9999`
records a failed execution. Without permission, Mock selects no tool; the Executor
also rejects forced disallowed calls before launching any MCP process.

Normal and replay step traces include `transport=mcp_stdio`, arguments, and results
or errors. Snapshot version 1 stores the structured plan and JSON output. Replay
uses the saved plan, current permissions, and current server data without a planner
or model. The registered `return_direct` policy prevents model rewrites of
single-step order results. The current adapter starts one client/server pair per
call; pooling and configurable remote servers remain future work.

```sh
docker compose -f docker-compose.yml -f docker-compose.mock.yml exec -T backend \
  python -m app.check_mcp_runtime --base-url http://frontend
```

Equivalent: `make mcp-runtime-check`. This checks five scenarios: both known
orders, linked replay, unknown order failure, and planning without permission.
Backend API tests also force a disallowed plan and revoke permission before
replay. CI runs the integrated check in `compose-demo` and the standalone MCP
checks/tests in `mcp-tools`.

The MCP suite now contains 22 tests, including client envelopes, invalid requests,
incompatible discovery, mismatched order responses, transport failures, and
timeout cleanup. Client exit codes are 0 for success, 1 for call/transport failures,
and 2 for invalid input/configuration; stdout contains one JSON envelope.

## Next MCP milestones

The original business-tool plan also includes `track_order(tracking_no)` and
`create_ticket(problem)`. They will be implemented as separate verifiable tools.
The current server has only the read-only `get_order` tool.

Official references:

- [Python SDK](https://github.com/modelcontextprotocol/python-sdk).
- [MCP transports](https://modelcontextprotocol.io/specification/latest/basic/transports).
