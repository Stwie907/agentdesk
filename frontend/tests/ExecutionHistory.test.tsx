import {
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import {
  afterEach,
  expect,
  test,
  vi,
} from "vitest";

import { ExecutionHistory } from "../src/components/ExecutionHistory";

function jsonResponse(body: unknown): Response {
  return {
    ok: true,
    status: 200,
    json: async () => body,
  } as Response;
}

afterEach(() => {
  vi.unstubAllGlobals();
});

test("loads and renders recent executions", async () => {
  const fetchMock = vi.fn(async () =>
    jsonResponse([
      {
        id: 131,
        agent_id: 1,
        input: "计算40+2",
        output: "42",
        status: "completed",
        retry_count: 0,
        failure_type: null,
        failure_message: null,
        replay_of_execution_id: null,
        created_at: "2026-09-13T14:34:17",
      },
      {
        id: 130,
        agent_id: 1,
        input: "计算40+2",
        output: null,
        status: "failed",
        retry_count: 0,
        failure_type: "tool_arguments_error",
        failure_message: "missing required argument",
        replay_of_execution_id: 129,
        created_at: "2026-09-13T12:07:02",
      },
    ]),
  );

  vi.stubGlobal("fetch", fetchMock);

  render(
    <ExecutionHistory
      onSelectExecution={() => undefined}
    />,
  );

  expect(
    await screen.findByRole("heading", {
      name: "Execution History",
    }),
  ).toBeInTheDocument();

  expect(
    await screen.findByRole("button", {
      name: "Execution 131",
    }),
  ).toBeInTheDocument();

  expect(
    screen.getByRole("button", {
      name: "Execution 130",
    }),
  ).toBeInTheDocument();

  expect(screen.getByText("completed", { exact: true }))
    .toBeInTheDocument();

  expect(screen.getByText("failed", { exact: true }))
    .toBeInTheDocument();

  expect(fetchMock).toHaveBeenCalledTimes(1);
});

test("selects an execution from history", async () => {
  const fetchMock = vi.fn(async () =>
    jsonResponse([
      {
        id: 131,
        agent_id: 1,
        input: "计算40+2",
        output: "42",
        status: "completed",
        retry_count: 0,
        failure_type: null,
        failure_message: null,
        replay_of_execution_id: null,
        created_at: "2026-09-13T14:34:17",
      },
    ]),
  );

  vi.stubGlobal("fetch", fetchMock);

  const onSelectExecution = vi.fn();

  render(
    <ExecutionHistory
      onSelectExecution={onSelectExecution}
    />,
  );

  fireEvent.click(
    await screen.findByRole("button", {
      name: "Execution 131",
    }),
  );

  expect(onSelectExecution).toHaveBeenCalledTimes(1);
  expect(onSelectExecution).toHaveBeenCalledWith(131);
});

test("renders an empty history state", async () => {
  vi.stubGlobal(
    "fetch",
    vi.fn(async () => jsonResponse([])),
  );

  render(
    <ExecutionHistory
      onSelectExecution={() => undefined}
    />,
  );

  await waitFor(() => {
    expect(
      screen.getByText("No executions found."),
    ).toBeInTheDocument();
  });
});
