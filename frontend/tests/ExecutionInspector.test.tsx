import {
  fireEvent,
  render,
  screen,
} from "@testing-library/react";
import {
  afterEach,
  expect,
  test,
  vi,
} from "vitest";

import { ExecutionInspector } from "../src/components/ExecutionInspector";

function jsonResponse(
  body: unknown,
  status = 200,
): Response {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: async () => body,
  } as Response;
}

afterEach(() => {
  vi.unstubAllGlobals();
});

test("renders execution inspector controls", () => {
  render(<ExecutionInspector />);

  expect(
    screen.getByRole("heading", {
      name: "Runtime V4 Execution Inspector",
    }),
  ).toBeInTheDocument();

  expect(
    screen.getByLabelText("Execution ID"),
  ).toBeInTheDocument();

  expect(
    screen.getByRole("button", {
      name: "Load Execution",
    }),
  ).toBeInTheDocument();
});

test("loads and renders execution inspection data", async () => {
  const fetchMock = vi.fn(
    async (input: RequestInfo | URL) => {
      const url = String(input);

      if (url.endsWith("/executions/42/trace")) {
        return jsonResponse([
          {
            id: 10,
            execution_id: 42,
            event: "plan_started",
            step_index: null,
            tool: null,
            error: null,
            message: "plan_started",
            created_at: "2026-09-12T12:00:01",
          },
          {
            id: 11,
            execution_id: 42,
            event: "step_completed",
            step_index: 0,
            tool: "calculator",
            error: null,
            message: "step_completed: step=0 tool=calculator",
            created_at: "2026-09-12T12:00:02",
          },
        ]);
      }

      if (url.endsWith("/executions/42/snapshot")) {
        return jsonResponse({
          id: 5,
          execution_id: 42,
          snapshot_version: 1,
          input_snapshot: "calculate 40+2",
          plan_snapshot:
            '{"steps":[{"tool":"calculator","arguments":{"expression":"40+2"}}]}',
          output_snapshot: "42",
          created_at: "2026-09-12T12:00:00",
        });
      }

      if (url.endsWith("/executions/42/replays")) {
        return jsonResponse([
          {
            id: 43,
            agent_id: 1,
            input: "calculate 40+2",
            output: "42",
            status: "completed",
            retry_count: 0,
            failure_type: null,
            failure_message: null,
            replay_of_execution_id: 42,
            created_at: "2026-09-12T12:10:00",
          },
        ]);
      }

      if (url.endsWith("/executions/42")) {
        return jsonResponse({
          id: 42,
          agent_id: 1,
          input: "calculate 40+2",
          output: "42",
          status: "completed",
          retry_count: 0,
          failure_type: null,
          failure_message: null,
          replay_of_execution_id: null,
          created_at: "2026-09-12T12:00:00",
        });
      }

      return jsonResponse(
        {
          detail: "Unexpected request",
        },
        500,
      );
    },
  );

  vi.stubGlobal("fetch", fetchMock);

  render(<ExecutionInspector />);

  fireEvent.change(
    screen.getByLabelText("Execution ID"),
    {
      target: {
        value: "42",
      },
    },
  );

  fireEvent.click(
    screen.getByRole("button", {
      name: "Load Execution",
    }),
  );

  expect(
    await screen.findAllByText("calculate 40+2"),
  ).toHaveLength(2);

  expect(
    screen.getByText("completed", {
      selector: "dd",
    }),
  ).toBeInTheDocument();

  expect(
    screen.getByText("plan_started", {
      selector: "strong",
    }),
  ).toBeInTheDocument();

  expect(
    screen.getByText("Snapshot version"),
  ).toBeInTheDocument();

  expect(
    screen.getByText("Execution 43 — completed"),
  ).toBeInTheDocument();

  expect(fetchMock).toHaveBeenCalledTimes(4);
});

test("shows a stable error when execution does not exist", async () => {
  const fetchMock = vi.fn(async () =>
    jsonResponse(
      {
        detail: "Execution not found",
      },
      404,
    ),
  );

  vi.stubGlobal("fetch", fetchMock);

  render(<ExecutionInspector />);

  fireEvent.change(
    screen.getByLabelText("Execution ID"),
    {
      target: {
        value: "999999",
      },
    },
  );

  fireEvent.click(
    screen.getByRole("button", {
      name: "Load Execution",
    }),
  );

  expect(
    await screen.findByRole("alert"),
  ).toHaveTextContent("Execution not found");

  expect(fetchMock).toHaveBeenCalledTimes(1);
});

test("replays the inspected execution and loads the replay result", async () => {
  const fetchMock = vi.fn(
    async (
      input: RequestInfo | URL,
      init?: RequestInit,
    ): Promise<Response> => {
      const url = String(input);
      const method = init?.method ?? "GET";

      if (method === "POST" && url.endsWith("/executions/42/replay")) {
        return jsonResponse({
          id: 44,
          agent_id: 1,
          input: "calculate 40+2",
          output: "42",
          status: "completed",
          retry_count: 0,
          failure_type: null,
          failure_message: null,
          replay_of_execution_id: 42,
          created_at: "2026-09-14T12:10:00",
        });
      }

      if (url.endsWith("/executions/42/trace")) {
        return jsonResponse([]);
      }

      if (url.endsWith("/executions/42/snapshot")) {
        return jsonResponse({
          id: 5,
          execution_id: 42,
          snapshot_version: 1,
          input_snapshot: "calculate 40+2",
          plan_snapshot:
            '{"steps":[{"tool":"calculator","arguments":{"expression":"40+2"}}]}',
          output_snapshot: "42",
          created_at: "2026-09-14T12:00:00",
        });
      }

      if (url.endsWith("/executions/42/replays")) {
        return jsonResponse([]);
      }

      if (url.endsWith("/executions/42")) {
        return jsonResponse({
          id: 42,
          agent_id: 1,
          input: "source execution",
          output: "42",
          status: "completed",
          retry_count: 0,
          failure_type: null,
          failure_message: null,
          replay_of_execution_id: null,
          created_at: "2026-09-14T12:00:00",
        });
      }

      if (url.endsWith("/executions/44/trace")) {
        return jsonResponse([]);
      }

      if (url.endsWith("/executions/44/snapshot")) {
        return jsonResponse({
          id: 6,
          execution_id: 44,
          snapshot_version: 1,
          input_snapshot: "calculate 40+2",
          plan_snapshot:
            '{"steps":[{"tool":"calculator","arguments":{"expression":"40+2"}}]}',
          output_snapshot: "42",
          created_at: "2026-09-14T12:10:00",
        });
      }

      if (url.endsWith("/executions/44/replays")) {
        return jsonResponse([]);
      }

      if (url.endsWith("/executions/44")) {
        return jsonResponse({
          id: 44,
          agent_id: 1,
          input: "replayed execution",
          output: "42",
          status: "completed",
          retry_count: 0,
          failure_type: null,
          failure_message: null,
          replay_of_execution_id: 42,
          created_at: "2026-09-14T12:10:00",
        });
      }

      return jsonResponse(
        {
          detail: `Unexpected request: ${method} ${url}`,
        },
        500,
      );
    },
  );

  vi.stubGlobal("fetch", fetchMock);

  render(<ExecutionInspector selectedExecutionId={42} />);

  expect(
    await screen.findByText("source execution"),
  ).toBeInTheDocument();

  fireEvent.click(
    screen.getByRole("button", {
      name: "Replay execution",
    }),
  );

  expect(
    await screen.findByText("replayed execution"),
  ).toBeInTheDocument();

  expect(fetchMock).toHaveBeenCalledWith(
    expect.stringContaining("/executions/42/replay"),
    expect.objectContaining({
      method: "POST",
    }),
  );
});

test("cancels a pending execution from the inspector", async () => {
  const fetchMock = vi.fn(
    async (
      input: RequestInfo | URL,
      init?: RequestInit,
    ): Promise<Response> => {
      const url = String(input);
      const method = init?.method ?? "GET";

      if (
        method === "POST" &&
        url.endsWith("/executions/42/cancel")
      ) {
        return jsonResponse({
          id: 42,
          agent_id: 1,
          input: "pending execution",
          output: null,
          status: "cancelled",
          retry_count: 0,
          failure_type: null,
          failure_message: null,
          replay_of_execution_id: null,
          created_at: "2026-09-16T12:00:00",
        });
      }

      if (url.endsWith("/executions/42/trace")) {
        return jsonResponse([]);
      }

      if (url.endsWith("/executions/42/snapshot")) {
        return jsonResponse(
          {
            detail: "Execution snapshot not found",
          },
          404,
        );
      }

      if (url.endsWith("/executions/42/replays")) {
        return jsonResponse([]);
      }

      if (url.endsWith("/executions/42")) {
        return jsonResponse({
          id: 42,
          agent_id: 1,
          input: "pending execution",
          output: null,
          status: "pending",
          retry_count: 0,
          failure_type: null,
          failure_message: null,
          replay_of_execution_id: null,
          created_at: "2026-09-16T12:00:00",
        });
      }

      return jsonResponse(
        {
          detail: `Unexpected request: ${method} ${url}`,
        },
        500,
      );
    },
  );

  vi.stubGlobal("fetch", fetchMock);

  render(
    <ExecutionInspector selectedExecutionId={42} />,
  );

  expect(
    await screen.findByText("pending execution"),
  ).toBeInTheDocument();

  expect(
    screen.getByText("pending", {
      selector: "dd",
    }),
  ).toBeInTheDocument();

  fireEvent.click(
    screen.getByRole("button", {
      name: "Cancel execution",
    }),
  );

  expect(
    await screen.findByText("cancelled", {
      selector: "dd",
    }),
  ).toBeInTheDocument();

  expect(fetchMock).toHaveBeenCalledWith(
    expect.stringContaining("/executions/42/cancel"),
    expect.objectContaining({
      method: "POST",
    }),
  );

  expect(
    screen.queryByRole("button", {
      name: "Cancel execution",
    }),
  ).not.toBeInTheDocument();
});

test("retries a failed execution from the inspector", async () => {
  const fetchMock = vi.fn(
    async (
      input: RequestInfo | URL,
      init?: RequestInit,
    ): Promise<Response> => {
      const url = String(input);
      const method = init?.method ?? "GET";

      if (
        method === "POST" &&
        url.endsWith("/executions/42/retry")
      ) {
        return jsonResponse({
          id: 42,
          agent_id: 1,
          input: "failed execution",
          output: null,
          status: "pending",
          retry_count: 0,
          failure_type: null,
          failure_message: null,
          replay_of_execution_id: null,
          created_at: "2026-09-16T12:00:00",
        });
      }

      if (url.endsWith("/executions/42/trace")) {
        return jsonResponse([]);
      }

      if (url.endsWith("/executions/42/snapshot")) {
        return jsonResponse(
          {
            detail: "Execution snapshot not found",
          },
          404,
        );
      }

      if (url.endsWith("/executions/42/replays")) {
        return jsonResponse([]);
      }

      if (url.endsWith("/executions/42")) {
        return jsonResponse({
          id: 42,
          agent_id: 1,
          input: "failed execution",
          output: null,
          status: "failed",
          retry_count: 2,
          failure_type: "tool_error",
          failure_message: "calculator failed",
          replay_of_execution_id: null,
          created_at: "2026-09-16T12:00:00",
        });
      }

      return jsonResponse(
        {
          detail: `Unexpected request: ${method} ${url}`,
        },
        500,
      );
    },
  );

  vi.stubGlobal("fetch", fetchMock);

  render(
    <ExecutionInspector selectedExecutionId={42} />,
  );

  expect(
    await screen.findByText("failed execution"),
  ).toBeInTheDocument();

  expect(
    screen.getByText("failed", {
      selector: "dd",
    }),
  ).toBeInTheDocument();

  fireEvent.click(
    screen.getByRole("button", {
      name: "Retry execution",
    }),
  );

  expect(
    await screen.findByText("pending", {
      selector: "dd",
    }),
  ).toBeInTheDocument();

  expect(
    screen.queryByText("tool_error", {
      selector: "dd",
    }),
  ).not.toBeInTheDocument();

  expect(
    screen.queryByText("calculator failed", {
      selector: "dd",
    }),
  ).not.toBeInTheDocument();

  expect(fetchMock).toHaveBeenCalledWith(
    expect.stringContaining("/executions/42/retry"),
    expect.objectContaining({
      method: "POST",
    }),
  );

  expect(
    screen.queryByRole("button", {
      name: "Retry execution",
    }),
  ).not.toBeInTheDocument();
});


test("refreshes the inspected execution data", async () => {
  let executionReadCount = 0;

  const fetchMock = vi.fn(
    async (
      input: RequestInfo | URL,
      init?: RequestInit,
    ): Promise<Response> => {
      const url = String(input);
      const method = init?.method ?? "GET";

      if (
        method === "GET" &&
        url.endsWith("/executions/42")
      ) {
        executionReadCount += 1;

        if (executionReadCount === 1) {
          return jsonResponse({
            id: 42,
            agent_id: 1,
            input: "refresh execution",
            output: null,
            status: "pending",
            retry_count: 0,
            failure_type: null,
            failure_message: null,
            replay_of_execution_id: null,
            created_at: "2026-09-16T12:00:00",
          });
        }

        return jsonResponse({
          id: 42,
          agent_id: 1,
          input: "refresh execution",
          output: "refreshed output",
          status: "completed",
          retry_count: 0,
          failure_type: null,
          failure_message: null,
          replay_of_execution_id: null,
          created_at: "2026-09-16T12:00:00",
        });
      }

      if (url.endsWith("/executions/42/trace")) {
        if (executionReadCount === 1) {
          return jsonResponse([]);
        }

        return jsonResponse([
          {
            id: 20,
            execution_id: 42,
            event: "step_completed",
            step_index: 0,
            tool: "calculator",
            error: null,
            message: "refreshed trace",
            created_at: "2026-09-16T12:01:00",
          },
        ]);
      }

      if (url.endsWith("/executions/42/snapshot")) {
        return jsonResponse(
          {
            detail: "Execution snapshot not found",
          },
          404,
        );
      }

      if (url.endsWith("/executions/42/replays")) {
        if (executionReadCount === 1) {
          return jsonResponse([]);
        }

        return jsonResponse([
          {
            id: 43,
            agent_id: 1,
            input: "refresh execution",
            output: "replay output",
            status: "completed",
            retry_count: 0,
            failure_type: null,
            failure_message: null,
            replay_of_execution_id: 42,
            created_at: "2026-09-16T12:01:00",
          },
        ]);
      }

      return jsonResponse(
        {
          detail: `Unexpected request: ${method} ${url}`,
        },
        500,
      );
    },
  );

  vi.stubGlobal("fetch", fetchMock);

  render(
    <ExecutionInspector selectedExecutionId={42} />,
  );

  expect(
    await screen.findByText("refresh execution"),
  ).toBeInTheDocument();

  expect(
    screen.getByText("pending", {
      selector: "dd",
    }),
  ).toBeInTheDocument();

  fireEvent.click(
    screen.getByRole("button", {
      name: "Refresh execution",
    }),
  );

  expect(
    await screen.findByText("refreshed output"),
  ).toBeInTheDocument();

  expect(
    screen.getByText("completed", {
      selector: "dd",
    }),
  ).toBeInTheDocument();

  expect(
    screen.getByText("step_completed", {
      selector: "strong",
    }),
  ).toBeInTheDocument();

  expect(
    screen.getByText(
      (content) =>
        content.includes("Execution 43") &&
        content.includes("completed"),
    ),
  ).toBeInTheDocument();

  expect(
    screen.getByLabelText("Execution ID"),
  ).toHaveValue("42");

  expect(fetchMock).toHaveBeenCalledTimes(8);
});
