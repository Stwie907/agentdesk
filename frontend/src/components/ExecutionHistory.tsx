import {
  useEffect,
  useState,
} from "react";

import { getExecutions } from "../api/executions";
import type { Execution } from "../types/executions";

type ExecutionHistoryProps = {
  onSelectExecution: (executionId: number) => void;
  pageSize?: number;
};

export function ExecutionHistory({
  onSelectExecution,
  pageSize = 20,
}: ExecutionHistoryProps) {
  const [executions, setExecutions] = useState<Execution[]>([]);
  const [loading, setLoading] = useState(true);
  const [loadingMore, setLoadingMore] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [hasMore, setHasMore] = useState(false);
  const [statusFilter, setStatusFilter] = useState("");

  useEffect(() => {
    let cancelled = false;

    async function loadExecutions() {
      setLoading(true);
      setError(null);
      setExecutions([]);
      setHasMore(false);

      try {
        const result = await getExecutions(
          pageSize,
          0,
          statusFilter || undefined,
        );

        if (!cancelled) {
          setExecutions(result);
          setHasMore(result.length === pageSize);
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
  }, [pageSize, statusFilter]);

  async function handleLoadMore() {
    if (loadingMore) {
      return;
    }

    setLoadingMore(true);
    setError(null);

    try {
      const nextPage = await getExecutions(
        pageSize,
        executions.length,
        statusFilter || undefined,
      );

      setExecutions((currentExecutions) => [
        ...currentExecutions,
        ...nextPage,
      ]);

      setHasMore(nextPage.length === pageSize);
    } catch {
      setError("Unable to load execution history.");
    } finally {
      setLoadingMore(false);
    }
  }

  return (
    <section aria-labelledby="execution-history-heading">
      <h2 id="execution-history-heading">
        Execution History
      </h2>

      <div>
        <label htmlFor="execution-history-status">
          Status
        </label>

        <select
          id="execution-history-status"
          value={statusFilter}
          onChange={(event) =>
            setStatusFilter(event.target.value)
          }
        >
          <option value="">
            All statuses
          </option>
          <option value="pending">
            pending
          </option>
          <option value="running">
            running
          </option>
          <option value="completed">
            completed
          </option>
          <option value="failed">
            failed
          </option>
          <option value="cancelled">
            cancelled
          </option>
        </select>
      </div>

      {loading && (
        <p>
          Loading executions...
        </p>
      )}

      {!loading && error !== null && (
        <p role="alert">
          {error}
        </p>
      )}

      {!loading &&
        error === null &&
        executions.length === 0 && (
          <p>
            No executions found.
          </p>
        )}

      {!loading && executions.length > 0 && (
        <>
          <ul>
            {executions.map((execution) => (
              <li key={execution.id}>
                <button
                  type="button"
                  onClick={() =>
                    onSelectExecution(execution.id)
                  }
                >
                  Execution {execution.id}
                </button>

                {" – "}
                <span>
                  {execution.status}
                </span>

                {" – "}
                <span>
                  {execution.input}
                </span>
              </li>
            ))}
          </ul>

          {hasMore && (
            <button
              type="button"
              disabled={loadingMore}
              onClick={() => void handleLoadMore()}
            >
              {loadingMore
                ? "Loading..."
                : "Load more"}
            </button>
          )}
        </>
      )}
    </section>
  );
}
