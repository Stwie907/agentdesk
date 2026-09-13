import { useEffect, useState } from "react";

import { getExecutions } from "../api/executions";
import type { Execution } from "../types/executions";

type ExecutionHistoryProps = {
  onSelectExecution: (executionId: number) => void;
};

export function ExecutionHistory({
  onSelectExecution,
}: ExecutionHistoryProps) {
  const [executions, setExecutions] = useState<Execution[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;

    async function loadExecutions() {
      try {
        const result = await getExecutions();

        if (!cancelled) {
          setExecutions(result);
        }
      } catch {
        if (!cancelled) {
          setError("Unable to load execution history.");
        }
      } finally {
        if (!cancelled) {
          setLoading(false);
        }
      }
    }

    void loadExecutions();

    return () => {
      cancelled = true;
    };
  }, []);

  return (
    <section aria-labelledby="execution-history-heading">
      <h2 id="execution-history-heading">Execution History</h2>

      {loading && <p>Loading executions...</p>}

      {!loading && error !== null && (
        <p role="alert">{error}</p>
      )}

      {!loading && error === null && executions.length === 0 && (
        <p>No executions found.</p>
      )}

      {!loading && error === null && executions.length > 0 && (
        <ul>
          {executions.map((execution) => (
            <li key={execution.id}>
              <button
                type="button"
                onClick={() => onSelectExecution(execution.id)}
              >
                Execution {execution.id}
              </button>

              {" — "}
              <span>{execution.status}</span>

              {" — "}
              <span>{execution.input}</span>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
