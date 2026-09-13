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
