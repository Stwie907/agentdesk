# AgentDesk MCP business tools

This independent server uses the official
Python SDK (`mcp==2.3.0`). It exposes `get_order(order_id)` and
`track_order(tracking_no)` over stdio and serves synthetic, read-only local
fixtures. It makes no model, carrier, or external business API calls.

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
  "tool_names": ["get_order", "track_order"],
  "checks_passed": 16
}
```

The actual output also records the negotiated protocol version, check names,
and sample order ids/statuses/source. The SDK client launches `server.py` as a
real subprocess, negotiates the protocol, lists tools, and calls both tools.
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

## Order contract

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

## Tracking contract

`track_order` requires `tracking_no` matching `^DEMO-TRACK-[0-9]{4}$`.
Order ids such as `DEMO-1001` are not tracking numbers.

| Tracking number | Linked order | Status | Events |
| --- | --- | --- | --- |
| DEMO-TRACK-1001 | DEMO-1001 | in_transit | 3 |
| DEMO-TRACK-1002 | DEMO-1002 | label_created | 1 |

Structured output contains `source`, `tracking_no`, `order_id`, `carrier`,
`status`, and `events`. Each event has `occurred_at`, `status`, `location`, and
`description`. Timestamps are valid UTC strings in strictly increasing order;
the summary status matches the final event. Carrier and locations are synthetic.
These fixed timelines are not live logistics data.

`tracking-fixtures.json` has schema version 1. Startup rejects duplicates,
invalid fields/dates, inconsistent timelines, and references to missing demo
orders. Returned event lists are deep copies. `DEMO-TRACK-9999` returns a tool
error; malformed numbers, missing arguments, and wrong types also fail.
Both business tools advertise read-only, idempotent, closed-world behavior.

Stdout is reserved for JSON-RPC protocol messages. Human-readable server logging
uses stderr. Starting `server.py` directly waits for an MCP client and does not
open a browser page.

## Checks and tests

The protocol check validates eight areas for each tool, for 16 checks total:

1. Tool discovery and input/output schemas.
2. Read-only tool metadata.
3. The first known demo fixture.
4. The second known demo fixture.
5. A missing demo record.
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

The backend registers both tools with independent Agent permissions. Their
adapters invoke `client.py` using the isolated MCP environment. Each call starts
the independent server, performs MCP discovery and `tools/call`, validates the
typed order or shipment response, and closes the session/server. The backend
does not load business fixtures directly or install the SDK into its own
dependency environment.
The shared client accepts only `get_order` and `track_order`. The original
`lookup_order` function and default order CLI contract remain compatible.

Start the Mock workbench with `sh deployment/start-demo.sh`, select `MCP Order Agent`,
and submit `Get order DEMO-1001`, `Get order DEMO-1002`, or `查询订单DEMO-1001`.
Successful outputs are JSON containing the synthetic order. `Get order DEMO-9999`
records a failed execution. Without permission, Mock selects no tool; the Executor
also rejects forced disallowed calls before launching any MCP process.

Select `MCP Logistics Agent` for `Track order DEMO-TRACK-1001` or
`查询物流DEMO-TRACK-1002`. It only receives `track_order` permission. `MCP Order Agent`
keeps its existing settings. `Track order DEMO-TRACK-9999` records a tool failure.
The generic planner metadata, direct-result policy, Trace, and replay pipeline
support the new tool without another Agent-specific execution branch.

Normal and replay step traces include `transport=mcp_stdio`, arguments, and results
or errors. Snapshot version 1 stores the structured plan and JSON output. Replay
uses the saved plan, current permissions, and current server data without a planner
or model. The registered `return_direct` policy prevents model rewrites of
single-step business-tool results. The current adapter starts one client/server pair per
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

The equivalent tracking check is:

```sh
docker compose -f docker-compose.yml -f docker-compose.mock.yml exec -T backend \
  python -m app.check_mcp_tracking --base-url http://frontend
```

`make mcp-tracking-check` checks five tracking scenarios: both known timelines,
linked replay, unknown number failure, and planning without permission. Backend
tests also force disallowed calls and revoke tracking permission before replay.
The `compose-demo` job runs both order and tracking acceptance checks.

From an activated native MCP environment, a direct client call is:

```sh
printf '%s' '{"tracking_no":"DEMO-TRACK-1001"}' | python client.py --tool track_order
```

The MCP suite now contains 36 tests, including tracking fixture/timeline validation,
order links, client envelopes, invalid requests,
incompatible discovery, mismatched order responses, transport failures, and
timeout cleanup. Client exit codes are 0 for success, 1 for call/transport failures,
and 2 for invalid input/configuration; stdout contains one JSON envelope.

## Next MCP milestones

The next business tool is `create_ticket(problem)`. It will need a separate write
contract and permission tests. The current server only provides read-only order
and shipment lookups.

Official references:

- [Python SDK](https://github.com/modelcontextprotocol/python-sdk).
- [MCP transports](https://modelcontextprotocol.io/specification/latest/basic/transports).
