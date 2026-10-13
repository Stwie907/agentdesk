import type { Agent } from "../src/types/agents";
import type { Execution } from "../src/types/executions";

export const testAgent: Agent = {
  id: 7,
  name: "Calculator Agent",
  description: "Runs calculator tasks",
  model: "qwen2.5:7b",
  project_id: 1,
  allowed_tools: ["calculator"],
  created_at: "2026-10-07T12:00:00",
};

export function jsonResponse(body: unknown, status = 200): Response {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: async () => body,
  } as Response;
}

export function deferredResponse() {
  let resolve!: (response: Response) => void;
  const promise = new Promise<Response>((fulfill) => {
    resolve = fulfill;
  });

  return { promise, resolve };
}

export function executionFixture(id: number, status = "completed"): Execution {
  return {
    id,
    agent_id: testAgent.id,
    input: "Calculate 40 + 2",
    output: status === "failed" ? "Tool failed" : "42",
    status,
    retry_count: 0,
    failure_type: status === "failed" ? "tool_error" : null,
    failure_message: status === "failed" ? "Tool failed" : null,
    replay_of_execution_id: null,
    created_at: "2026-10-07T12:00:00",
  };
}
