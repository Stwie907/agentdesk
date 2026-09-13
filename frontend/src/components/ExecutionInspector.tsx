import { FormEvent, useState } from "react";

import { ApiError, getExecutionInspection } from "../api/executions";
import type { ExecutionInspection } from "../types/executions";

export function ExecutionInspector() {
  const [executionId, setExecutionId] = useState("");
  const [inspection, setInspection] = useState<ExecutionInspection | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();

    const parsedExecutionId = Number(executionId);

    if (
      !Number.isInteger(parsedExecutionId) ||
      parsedExecutionId <= 0
    ) {
      setInspection(null);
      setError("Enter a valid positive execution ID.");
      return;
    }

    setLoading(true);
    setError(null);
    setInspection(null);

    try {
      const result = await getExecutionInspection(parsedExecutionId);
      setInspection(result);
    } catch (requestError) {
      if (requestError instanceof ApiError) {
        setError(requestError.message);
      } else {
        setError("Unable to load execution.");
      }
    } finally {
      setLoading(false);
    }
  }

  return (
    <section aria-labelledby="execution-inspector-heading">
      <h2 id="execution-inspector-heading">
        Runtime V4 Execution Inspector
      </h2>

      <form onSubmit={handleSubmit}>
        <label htmlFor="execution-id">
          Execution ID
        </label>

        <input
          id="execution-id"
          name="execution-id"
          inputMode="numeric"
          value={executionId}
          onChange={(event) => setExecutionId(event.target.value)}
        />

        <button type="submit" disabled={loading}>
          {loading ? "Loading..." : "Load Execution"}
        </button>
      </form>

      {error !== null && (
        <p role="alert">
          {error}
        </p>
      )}

      {inspection !== null && (
        <>
          <section aria-labelledby="execution-summary-heading">
            <h3 id="execution-summary-heading">
              Execution Summary
            </h3>

            <dl>
              <dt>ID</dt>
              <dd>{inspection.execution.id}</dd>

              <dt>Agent ID</dt>
              <dd>{inspection.execution.agent_id}</dd>

              <dt>Status</dt>
              <dd>{inspection.execution.status}</dd>

              <dt>Input</dt>
              <dd>{inspection.execution.input}</dd>

              <dt>Output</dt>
              <dd>
                {inspection.execution.output ?? "No output"}
              </dd>

              <dt>Retry count</dt>
              <dd>{inspection.execution.retry_count}</dd>

              <dt>Replay of execution</dt>
              <dd>
                {inspection.execution.replay_of_execution_id ?? "No"}
              </dd>

              <dt>Failure type</dt>
              <dd>
                {inspection.execution.failure_type ?? "None"}
              </dd>

              <dt>Failure message</dt>
              <dd>
                {inspection.execution.failure_message ?? "None"}
              </dd>

              <dt>Created at</dt>
              <dd>{inspection.execution.created_at}</dd>
            </dl>
          </section>

          <section aria-labelledby="execution-trace-heading">
            <h3 id="execution-trace-heading">
              Runtime V4 Trace
            </h3>

            {inspection.trace.length === 0 ? (
              <p>No Runtime V4 trace events.</p>
            ) : (
              <ol>
                {inspection.trace.map((event) => (
                  <li key={event.id}>
                    <strong>{event.event}</strong>

                    {event.step_index !== null && (
                      <span>
                        {" "}
                        — step {event.step_index}
                      </span>
                    )}

                    {event.tool !== null && (
                      <span>
                        {" "}
                        — tool {event.tool}
                      </span>
                    )}

                    {event.error !== null && (
                      <span>
                        {" "}
                        — error {event.error}
                      </span>
                    )}

                    <div>{event.message}</div>
                  </li>
                ))}
              </ol>
            )}
          </section>

          <section aria-labelledby="execution-snapshot-heading">
            <h3 id="execution-snapshot-heading">
              Snapshot
            </h3>

            {inspection.snapshot === null ? (
              <p>No snapshot available.</p>
            ) : (
              <>
                <dl>
                  <dt>Snapshot version</dt>
                  <dd>{inspection.snapshot.snapshot_version}</dd>

                  <dt>Input snapshot</dt>
                  <dd>{inspection.snapshot.input_snapshot}</dd>

                  <dt>Output snapshot</dt>
                  <dd>
                    {inspection.snapshot.output_snapshot ?? "No output"}
                  </dd>
                </dl>

                <h4>Plan snapshot</h4>

                <pre>
                  {inspection.snapshot.plan_snapshot ?? "No plan snapshot"}
                </pre>
              </>
            )}
          </section>

          <section aria-labelledby="execution-replays-heading">
            <h3 id="execution-replays-heading">
              Replay History
            </h3>

            {inspection.replays.length === 0 ? (
              <p>No replay executions.</p>
            ) : (
              <ul>
                {inspection.replays.map((replay) => (
                  <li key={replay.id}>
                    Execution {replay.id} — {replay.status}
                  </li>
                ))}
              </ul>
            )}
          </section>
        </>
      )}
    </section>
  );
}
