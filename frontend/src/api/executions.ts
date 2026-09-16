import type {
  Execution,
  ExecutionInspection,
  ExecutionSnapshot,
  ExecutionTraceEvent,
} from "../types/executions";

const API_BASE_URL =
  import.meta.env.VITE_API_BASE_URL ?? "";

export class ApiError extends Error {
  readonly status: number;

  constructor(status: number, message: string) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

async function requestJson<T>(
  path: string,
  init?: RequestInit,
): Promise<T> {
  const response =
    init === undefined
      ? await fetch(`${API_BASE_URL}${path}`)
      : await fetch(`${API_BASE_URL}${path}`, init);

  if (!response.ok) {
    let message = `Request failed with status ${response.status}`;

    try {
      const body = (await response.json()) as {
        detail?: unknown;
      };

      if (typeof body.detail === "string") {
        message = body.detail;
      }
    } catch {
      // Keep the stable fallback message when the response is not JSON.
    }

    throw new ApiError(response.status, message);
  }

  return (await response.json()) as T;
}

export function getExecution(
  executionId: number,
): Promise<Execution> {
  return requestJson<Execution>(
    `/executions/${executionId}`,
  );
}

export function getExecutionTrace(
  executionId: number,
): Promise<ExecutionTraceEvent[]> {
  return requestJson<ExecutionTraceEvent[]>(
    `/executions/${executionId}/trace`,
  );
}

export async function getExecutionSnapshot(
  executionId: number,
): Promise<ExecutionSnapshot | null> {
  try {
    return await requestJson<ExecutionSnapshot>(
      `/executions/${executionId}/snapshot`,
    );
  } catch (error) {
    if (error instanceof ApiError && error.status === 404) {
      return null;
    }

    throw error;
  }
}

export function replayExecution(
  executionId: number,
): Promise<Execution> {
  return requestJson<Execution>(
    `/executions/${executionId}/replay`,
    {
      method: "POST",
    },
  );
}

export function cancelExecution(
  executionId: number,
): Promise<Execution> {
  return requestJson<Execution>(
    `/executions/${executionId}/cancel`,
    {
      method: "POST",
    },
  );
}

export function getExecutionReplays(
  executionId: number,
): Promise<Execution[]> {
  return requestJson<Execution[]>(
    `/executions/${executionId}/replays`,
  );
}

export async function getExecutionInspection(
  executionId: number,
): Promise<ExecutionInspection> {
  // Load the execution first. If it does not exist, stop immediately rather
  // than sending three unnecessary inspection requests.
  const execution = await getExecution(executionId);

  const [trace, snapshot, replays] = await Promise.all([
    getExecutionTrace(executionId),
    getExecutionSnapshot(executionId),
    getExecutionReplays(executionId),
  ]);

  return {
    execution,
    trace,
    snapshot,
    replays,
  };
}

export function getExecutions(
  limit = 20,
  offset = 0,
  status?: string,
  agentId?: number,
): Promise<Execution[]> {
  const queryParts: string[] = [];

  if (status !== undefined && status !== "") {
    queryParts.push(`status=${encodeURIComponent(status)}`);
  }

  if (agentId !== undefined) {
    queryParts.push(`agent_id=${agentId}`);
  }

  queryParts.push(`limit=${limit}`);
  queryParts.push(`offset=${offset}`);

  return requestJson<Execution[]>(
    `/executions?${queryParts.join("&")}`,
  );
}
