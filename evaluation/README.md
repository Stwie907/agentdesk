# Runtime V4 evaluation

This suite evaluates AgentDesk's existing runtime through public HTTP APIs.
It uses a versioned fixed Mock dataset, the real Calculator, stored traces,
snapshots, and replay. It adds no Python packages and requires no model API key.

## Run with Docker

From the repository root, using Windows Git Bash or a Unix shell:

```sh
sh deployment/start-demo.sh
sh deployment/evaluate-demo.sh
```

The first command starts the explicit Mock backend, frontend, and Demo Agent.
The second command builds a temporary evaluation container using the backend
Dockerfile and requests the API through `http://frontend`. It needs the existing
demo services to be running; it does not change a running backend's provider.
Its source directory is mounted read-only, and reports are written to a separate
bind mount on your computer. The temporary container is removed after the run.
The optional evaluation service is disabled during normal application startup.

Equivalent commands are `make demo` followed by `make evaluate`.
Python on Windows and virtual-environment activation are not needed for this
Docker workflow.

For the shipped dataset, successful output contains:

```json
{
  "status": "passed",
  "total_cases": 8,
  "passed_cases": 8,
  "failed_cases": 0,
  "skipped_cases": 0,
  "completed_cases": 8,
  "correct_outputs": 8,
  "pass_rate": 1.0,
  "execution_success_rate": 1.0,
  "output_accuracy": 1.0
}
```

The actual console summary also includes measured latency values. Reports are:

- `evaluation/reports/report.json`: machine-readable metadata, checks, and results.
- `evaluation/reports/report.md`: a metrics table and per-case diagnostics.

Each run overwrites these two files and creates eight execution records on a
successful run. Existing agents and executions are retained. Generated reports
are ignored by Git; copy them elsewhere if you want to preserve a particular run.

## Fixed cases

| Case | Input or operation | Expected output | Expected tool |
| --- | --- | --- | --- |
| addition | Calculate 40 + 2 | 42 | calculator |
| subtraction | Calculate 18 - 7 | 11 | calculator |
| multiplication | calculate -3 * 7 | -21 | calculator |
| division | 计算20/4 | 5.0 | calculator |
| decimal | Calculate 1.5 + 2.25 | 3.75 | calculator |
| greeting | Hello AgentDesk | Fixed `[MOCK]` reply | none |
| unsupported_expression | Calculate (2 + 3) * 4 | Fixed `[MOCK]` reply | none |
| replay_addition | Replay the addition execution | 42 | calculator |

Mock planning supports a single binary operation. The complex expression case
checks its documented fixed-reply behavior. It does not claim support for a
multi-operation planner. The exact reply is stored in `dataset.json`.

Every case checks a completed execution, exact output, persisted execution
record, trace order, tool selection, and snapshot version/input/output/plan.
Chat cases additionally require the `provider=mock` trace marker. Replay uses a
passing source from the current run, checks its parent link, and checks replay
history. A failed source makes its replay case skipped rather than replaying an
unrelated old execution.

The API currently has no provider-discovery endpoint. Provider verification
therefore uses the first chat task's trace. If you point the evaluator at an
Ollama backend, that first task can call the local model before the mismatch is
detected; remaining cases are then skipped. Use the explicit Mock startup command
above for a model-free run.

## Metrics

All three rates use the total number of dataset cases as their denominator;
failed or skipped cases are not silently removed.

| Metric | Definition |
| --- | --- |
| Overall pass rate | Cases passing every applicable check / all cases. |
| Execution success rate | Cases whose primary POST response reports `completed` / all cases. |
| Exact output accuracy | Cases whose returned output equals the expected string / all cases. |
| Failed cases | Attempted cases failing checks or encountering request/response errors. |
| Skipped cases | Cases not submitted because setup, provider verification, or their source failed. |
| Mean / median POST latency | Summary of attempted chat/replay POST request durations in milliseconds. |
| p95 POST latency | Nearest-rank value at `ceil(0.95 * samples)` in sorted durations. |

Latency includes failed POST attempts and excludes the follow-up inspection GET
requests. Skipped cases contribute no latency sample. No samples produce JSON
`null` latency values. CI gates on correctness, not a machine-dependent latency
threshold. Eight cases form a small regression corpus, not a general performance
benchmark or language-model quality score.

Reports record UTC timestamps, the selected agent, expected provider, dataset
SHA-256, execution ids, and individual failed checks. CI provides its Git revision
through `EVALUATION_REVISION`; local runs show `unknown` unless you supply it:

```sh
EVALUATION_REVISION=$(git rev-parse HEAD) sh deployment/evaluate-demo.sh
```

## Native Python and evaluator tests

With Python 3.11 or newer, the evaluator also runs directly from the repository
root. Backend dependencies are not required by the evaluator itself:

```sh
python -m evaluation.run --base-url http://127.0.0.1:5173
python -m unittest discover -s evaluation/tests -v
```

The application still needs a running, seeded Mock backend. Native backend
environment variables must be exported in the terminal launching Uvicorn; the
root `.env` file is not automatically loaded by Uvicorn.

Optional arguments include `--dataset`, `--output-dir`, `--timeout`, `--agent-id`,
`--agent-name`, and `--revision`. Agent name defaults to `Demo Agent`; duplicate
matching names require selecting an explicit id. Timeout defaults to 30 seconds
per HTTP request. Local requests bypass host HTTP proxy settings.

Datasets use schema version 1 and provider `mock`. Case ids must be unique, and
replay references must point to earlier chat cases. Each case declares an exact
expected output and tool; calculator cases also declare the stored expression.

## CI and troubleshooting

The `structure` job runs evaluator tests. The `compose-demo` job evaluates the
running Mock services and uploads the reports as `runtime-evaluation-report`
with seven-day retention, including reports from a failed evaluation run.
Find them on that GitHub Actions run's **Artifacts** section.

Exit codes:

- `0`: all cases passed.
- `1`: setup or case evaluation failed; inspect the generated reports.
- `2`: invalid arguments, dataset configuration, or report write failure.

If setup fails, check `docker compose ps --all` and
`docker compose logs --tail=80 backend frontend`, then run the Mock startup script.
If a case fails, inspect `error`, `failures`, and its execution id in the JSON
report or the workbench. A completed task with a wrong output still fails.

Router/RAG accuracy, hallucination scoring, token accounting, and a report
dashboard remain later evaluation phases. Planned Router accuracy (>80%) and
RAG answer accuracy (>85%) need their own implemented pipelines and datasets.
