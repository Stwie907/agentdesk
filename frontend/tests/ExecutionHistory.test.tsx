import {
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
import {
  afterEach,
  expect,
  test,
  vi,
} from "vitest";

import { ExecutionHistory } from "../src/components/ExecutionHistory";

function jsonResponse(body: unknown, status = 200): Response {
  return {
    ok: status >= 200 && status < 300,
    status,
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

  expect(
    within(
      screen.getByRole("button", { name: "Execution 131" }).closest("li")!,
    ).getByText("completed", { exact: true }),
  ).toBeInTheDocument();

  expect(
    within(
      screen.getByRole("button", { name: "Execution 130" }).closest("li")!,
    ).getByText("failed", { exact: true }),
  ).toBeInTheDocument();

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

test("loads execution history in pages and appends the next page", async () => {
  const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
    const url = String(input);

    if (url.endsWith("/executions?limit=2&offset=0")) {
      return jsonResponse([
        {
          id: 131,
          agent_id: 1,
          input: "first page execution",
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
          input: "second execution",
          output: null,
          status: "failed",
          retry_count: 0,
          failure_type: "tool_arguments_error",
          failure_message: "missing required argument",
          replay_of_execution_id: null,
          created_at: "2026-09-13T12:07:02",
        },
      ]);
    }

    if (url.endsWith("/executions?limit=2&offset=2")) {
      return jsonResponse([
        {
          id: 129,
          agent_id: 1,
          input: "older execution",
          output: "10",
          status: "completed",
          retry_count: 0,
          failure_type: null,
          failure_message: null,
          replay_of_execution_id: null,
          created_at: "2026-09-12T10:00:00",
        },
      ]);
    }

    return jsonResponse(
      {
        detail: `Unexpected request: ${url}`,
      },
      500,
    );
  });

  vi.stubGlobal("fetch", fetchMock);

  render(
    <ExecutionHistory
      onSelectExecution={() => undefined}
      pageSize={2}
    />,
  );

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

  expect(
    screen.queryByRole("button", {
      name: "Execution 129",
    }),
  ).not.toBeInTheDocument();

  fireEvent.click(
    screen.getByRole("button", {
      name: "Load more",
    }),
  );

  expect(
    await screen.findByRole("button", {
      name: "Execution 129",
    }),
  ).toBeInTheDocument();

  expect(fetchMock).toHaveBeenNthCalledWith(
    1,
    expect.stringContaining("/executions?limit=2&offset=0"),
  );

  expect(fetchMock).toHaveBeenNthCalledWith(
    2,
    expect.stringContaining("/executions?limit=2&offset=2"),
  );

  expect(fetchMock).toHaveBeenCalledTimes(2);

  expect(
    screen.queryByRole("button", {
      name: "Load more",
    }),
  ).not.toBeInTheDocument();
});


test("filters execution history by status and restarts pagination", async () => {
  const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
    const url = String(input);

    if (url.endsWith("/executions?limit=2&offset=0")) {
      return jsonResponse([
        {
          id: 131,
          agent_id: 1,
          input: "completed execution",
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
          input: "failed execution",
          output: null,
          status: "failed",
          retry_count: 0,
          failure_type: "tool_arguments_error",
          failure_message: "missing required argument",
          replay_of_execution_id: null,
          created_at: "2026-09-13T12:07:02",
        },
      ]);
    }

    if (
      url.endsWith(
        "/executions?status=completed&limit=2&offset=0",
      )
    ) {
      return jsonResponse([
        {
          id: 131,
          agent_id: 1,
          input: "completed execution",
          output: "42",
          status: "completed",
          retry_count: 0,
          failure_type: null,
          failure_message: null,
          replay_of_execution_id: null,
          created_at: "2026-09-13T14:34:17",
        },
      ]);
    }

    return jsonResponse(
      {
        detail: `Unexpected request: ${url}`,
      },
      500,
    );
  });

  vi.stubGlobal("fetch", fetchMock);

  render(
    <ExecutionHistory
      onSelectExecution={() => undefined}
      pageSize={2}
    />,
  );

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

  fireEvent.change(
    screen.getByLabelText("Status"),
    {
      target: {
        value: "completed",
      },
    },
  );

  await waitFor(() => {
    expect(
      screen.queryByRole("button", {
        name: "Execution 130",
      }),
    ).not.toBeInTheDocument();
  });

  expect(
    screen.getByRole("button", {
      name: "Execution 131",
    }),
  ).toBeInTheDocument();

  expect(fetchMock).toHaveBeenNthCalledWith(
    2,
    expect.stringContaining(
      "/executions?status=completed&limit=2&offset=0",
    ),
  );
});
