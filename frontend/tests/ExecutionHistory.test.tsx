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


test("filters execution history by agent and restarts pagination", async () => {
  const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
    const url = new URL(String(input), "http://localhost");

    if (
      url.pathname.endsWith("/executions") &&
      url.searchParams.get("agent_id") === "1"
    ) {
      return jsonResponse([
        {
          id: 131,
          agent_id: 1,
          input: "agent one execution",
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

    if (
      url.pathname.endsWith("/executions") &&
      url.searchParams.get("agent_id") === null
    ) {
      return jsonResponse([
        {
          id: 131,
          agent_id: 1,
          input: "agent one execution",
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
          agent_id: 2,
          input: "agent two execution",
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

    return jsonResponse(
      {
        detail: `Unexpected request: ${url.toString()}`,
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
    screen.getByLabelText("Agent ID"),
    {
      target: {
        value: "1",
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

  expect(fetchMock).toHaveBeenCalledTimes(2);

  const secondRequestUrl = String(fetchMock.mock.calls[1][0]);

  expect(secondRequestUrl).toContain("agent_id=1");
  expect(secondRequestUrl).toContain("limit=2");
  expect(secondRequestUrl).toContain("offset=0");
});


test("combines status and agent filters with pagination", async () => {
  const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
    const url = new URL(String(input), "http://localhost");

    const status = url.searchParams.get("status");
    const agentId = url.searchParams.get("agent_id");
    const offset = url.searchParams.get("offset");

    if (
      status === null &&
      agentId === null &&
      offset === "0"
    ) {
      return jsonResponse([
        {
          id: 131,
          agent_id: 1,
          input: "agent one completed execution",
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
          agent_id: 2,
          input: "agent two failed execution",
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
      status === "completed" &&
      agentId === null &&
      offset === "0"
    ) {
      return jsonResponse([
        {
          id: 131,
          agent_id: 1,
          input: "agent one completed execution",
          output: "42",
          status: "completed",
          retry_count: 0,
          failure_type: null,
          failure_message: null,
          replay_of_execution_id: null,
          created_at: "2026-09-13T14:34:17",
        },
        {
          id: 129,
          agent_id: 2,
          input: "agent two completed execution",
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

    if (
      status === "completed" &&
      agentId === "1" &&
      offset === "0"
    ) {
      return jsonResponse([
        {
          id: 131,
          agent_id: 1,
          input: "agent one newest execution",
          output: "42",
          status: "completed",
          retry_count: 0,
          failure_type: null,
          failure_message: null,
          replay_of_execution_id: null,
          created_at: "2026-09-13T14:34:17",
        },
        {
          id: 128,
          agent_id: 1,
          input: "agent one older execution",
          output: "20",
          status: "completed",
          retry_count: 0,
          failure_type: null,
          failure_message: null,
          replay_of_execution_id: null,
          created_at: "2026-09-12T09:00:00",
        },
      ]);
    }

    if (
      status === "completed" &&
      agentId === "1" &&
      offset === "2"
    ) {
      return jsonResponse([
        {
          id: 127,
          agent_id: 1,
          input: "agent one oldest execution",
          output: "15",
          status: "completed",
          retry_count: 0,
          failure_type: null,
          failure_message: null,
          replay_of_execution_id: null,
          created_at: "2026-09-11T09:00:00",
        },
      ]);
    }

    return jsonResponse(
      {
        detail: `Unexpected request: ${url.toString()}`,
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

  fireEvent.change(
    screen.getByLabelText("Status"),
    {
      target: {
        value: "completed",
      },
    },
  );

  expect(
    await screen.findByRole("button", {
      name: "Execution 129",
    }),
  ).toBeInTheDocument();

  fireEvent.change(
    screen.getByLabelText("Agent ID"),
    {
      target: {
        value: "1",
      },
    },
  );

  expect(
    await screen.findByRole("button", {
      name: "Execution 128",
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
      name: "Execution 127",
    }),
  ).toBeInTheDocument();

  const combinedFirstPageUrl = new URL(
    String(fetchMock.mock.calls[2][0]),
    "http://localhost",
  );

  expect(
    combinedFirstPageUrl.searchParams.get("status"),
  ).toBe("completed");

  expect(
    combinedFirstPageUrl.searchParams.get("agent_id"),
  ).toBe("1");

  expect(
    combinedFirstPageUrl.searchParams.get("limit"),
  ).toBe("2");

  expect(
    combinedFirstPageUrl.searchParams.get("offset"),
  ).toBe("0");

  const combinedSecondPageUrl = new URL(
    String(fetchMock.mock.calls[3][0]),
    "http://localhost",
  );

  expect(
    combinedSecondPageUrl.searchParams.get("status"),
  ).toBe("completed");

  expect(
    combinedSecondPageUrl.searchParams.get("agent_id"),
  ).toBe("1");

  expect(
    combinedSecondPageUrl.searchParams.get("limit"),
  ).toBe("2");

  expect(
    combinedSecondPageUrl.searchParams.get("offset"),
  ).toBe("2");

  expect(fetchMock).toHaveBeenCalledTimes(4);
});


test(
  "preserves the active status filter when an execution update no longer matches",
  async () => {
    const execution42 = {
      id: 42,
      agent_id: 1,
      input: "first completed execution",
      output: "42",
      status: "completed",
      retry_count: 0,
      failure_type: null,
      failure_message: null,
      replay_of_execution_id: null,
      created_at: "2026-09-17T12:00:00",
    };

    const execution41 = {
      id: 41,
      agent_id: 1,
      input: "second completed execution",
      output: "41",
      status: "completed",
      retry_count: 0,
      failure_type: null,
      failure_message: null,
      replay_of_execution_id: null,
      created_at: "2026-09-17T11:00:00",
    };

    const updatedExecution42 = {
      ...execution42,
      output: null,
      status: "pending",
    };

    const fetchMock = vi.fn(
      async (
        input: RequestInfo | URL,
      ): Promise<Response> => {
        const url = new URL(
          String(input),
          "http://localhost",
        );

        if (
          url.pathname.endsWith("/executions") &&
          url.searchParams.get("status") ===
            "completed"
        ) {
          return jsonResponse([
            execution42,
            execution41,
          ]);
        }

        if (url.pathname.endsWith("/executions")) {
          return jsonResponse([]);
        }

        return jsonResponse(
          {
            detail: `Unexpected request: ${url.toString()}`,
          },
          500,
        );
      },
    );

    vi.stubGlobal("fetch", fetchMock);

    const onSelectExecution = vi.fn();

    const { rerender } = render(
      <ExecutionHistory
        onSelectExecution={onSelectExecution}
        pageSize={2}
      />,
    );

    expect(
      await screen.findByText("No executions found."),
    ).toBeInTheDocument();

    fireEvent.change(
      screen.getByLabelText("Status"),
      {
        target: {
          value: "completed",
        },
      },
    );

    expect(
      await screen.findByRole("button", {
        name: "Execution 42",
      }),
    ).toBeInTheDocument();

    expect(
      screen.getByRole("button", {
        name: "Execution 41",
      }),
    ).toBeInTheDocument();

    const requestCountBeforeUpdate =
      fetchMock.mock.calls.length;

    rerender(
      <ExecutionHistory
        onSelectExecution={onSelectExecution}
        pageSize={2}
        updatedExecution={updatedExecution42}
      />,
    );

    expect(
      screen.getByLabelText("Status"),
    ).toHaveValue("completed");

    expect(
      screen.queryByRole("button", {
        name: "Execution 42",
      }),
    ).not.toBeInTheDocument();

    expect(
      screen.getByRole("button", {
        name: "Execution 41",
      }),
    ).toBeInTheDocument();

    expect(fetchMock).toHaveBeenCalledTimes(
      requestCountBeforeUpdate,
    );
  },
);


test(
  "preserves the active agent filter when an execution update no longer matches",
  async () => {
    const execution42 = {
      id: 42,
      agent_id: 1,
      input: "agent one execution",
      output: "42",
      status: "completed",
      retry_count: 0,
      failure_type: null,
      failure_message: null,
      replay_of_execution_id: null,
      created_at: "2026-09-17T12:00:00",
    };

    const execution41 = {
      id: 41,
      agent_id: 1,
      input: "another agent one execution",
      output: "41",
      status: "completed",
      retry_count: 0,
      failure_type: null,
      failure_message: null,
      replay_of_execution_id: null,
      created_at: "2026-09-17T11:00:00",
    };

    const updatedExecution42 = {
      ...execution42,
      agent_id: 2,
    };

    const fetchMock = vi.fn(
      async (
        input: RequestInfo | URL,
      ): Promise<Response> => {
        const url = new URL(
          String(input),
          "http://localhost",
        );

        if (
          url.pathname.endsWith("/executions") &&
          url.searchParams.get("agent_id") === "1"
        ) {
          return jsonResponse([
            execution42,
            execution41,
          ]);
        }

        if (url.pathname.endsWith("/executions")) {
          return jsonResponse([]);
        }

        return jsonResponse(
          {
            detail: `Unexpected request: ${url.toString()}`,
          },
          500,
        );
      },
    );

    vi.stubGlobal("fetch", fetchMock);

    const onSelectExecution = vi.fn();

    const { rerender } = render(
      <ExecutionHistory
        onSelectExecution={onSelectExecution}
        pageSize={2}
      />,
    );

    expect(
      await screen.findByText("No executions found."),
    ).toBeInTheDocument();

    fireEvent.change(
      screen.getByLabelText("Agent ID"),
      {
        target: {
          value: "1",
        },
      },
    );

    expect(
      await screen.findByRole("button", {
        name: "Execution 42",
      }),
    ).toBeInTheDocument();

    expect(
      screen.getByRole("button", {
        name: "Execution 41",
      }),
    ).toBeInTheDocument();

    const requestCountBeforeUpdate =
      fetchMock.mock.calls.length;

    rerender(
      <ExecutionHistory
        onSelectExecution={onSelectExecution}
        pageSize={2}
        updatedExecution={updatedExecution42}
      />,
    );

    expect(
      screen.getByLabelText("Agent ID"),
    ).toHaveValue(1);

    expect(
      screen.queryByRole("button", {
        name: "Execution 42",
      }),
    ).not.toBeInTheDocument();

    expect(
      screen.getByRole("button", {
        name: "Execution 41",
      }),
    ).toBeInTheDocument();

    expect(fetchMock).toHaveBeenCalledTimes(
      requestCountBeforeUpdate,
    );
  },
);


test(
  "preserves loaded history pages when synchronizing an execution update",
  async () => {
    const execution42 = {
      id: 42,
      agent_id: 1,
      input: "first page execution",
      output: "42",
      status: "completed",
      retry_count: 0,
      failure_type: null,
      failure_message: null,
      replay_of_execution_id: null,
      created_at: "2026-09-17T12:00:00",
    };

    const execution41 = {
      id: 41,
      agent_id: 1,
      input: "second first page execution",
      output: "41",
      status: "completed",
      retry_count: 0,
      failure_type: null,
      failure_message: null,
      replay_of_execution_id: null,
      created_at: "2026-09-17T11:00:00",
    };

    const execution40 = {
      id: 40,
      agent_id: 2,
      input: "second page execution",
      output: "40",
      status: "completed",
      retry_count: 0,
      failure_type: null,
      failure_message: null,
      replay_of_execution_id: null,
      created_at: "2026-09-17T10:00:00",
    };

    const updatedExecution42 = {
      ...execution42,
      input: "updated first page execution",
      output: "updated output",
    };

    const fetchMock = vi.fn(
      async (
        input: RequestInfo | URL,
      ): Promise<Response> => {
        const url = new URL(
          String(input),
          "http://localhost",
        );

        if (!url.pathname.endsWith("/executions")) {
          return jsonResponse(
            {
              detail: `Unexpected request: ${url.toString()}`,
            },
            500,
          );
        }

        const offset =
          url.searchParams.get("offset") ?? "0";

        if (offset === "0") {
          return jsonResponse([
            execution42,
            execution41,
          ]);
        }

        if (offset === "2") {
          return jsonResponse([
            execution40,
          ]);
        }

        return jsonResponse([]);
      },
    );

    vi.stubGlobal("fetch", fetchMock);

    const onSelectExecution = vi.fn();

    const { rerender } = render(
      <ExecutionHistory
        onSelectExecution={onSelectExecution}
        pageSize={2}
      />,
    );

    expect(
      await screen.findByRole("button", {
        name: "Execution 42",
      }),
    ).toBeInTheDocument();

    fireEvent.click(
      screen.getByRole("button", {
        name: "Load more",
      }),
    );

    expect(
      await screen.findByRole("button", {
        name: "Execution 40",
      }),
    ).toBeInTheDocument();

    const requestCountBeforeUpdate =
      fetchMock.mock.calls.length;

    rerender(
      <ExecutionHistory
        onSelectExecution={onSelectExecution}
        pageSize={2}
        updatedExecution={updatedExecution42}
      />,
    );

    expect(
      screen.getByRole("button", {
        name: "Execution 42",
      }),
    ).toBeInTheDocument();

    expect(
      screen.getByRole("button", {
        name: "Execution 41",
      }),
    ).toBeInTheDocument();

    expect(
      screen.getByRole("button", {
        name: "Execution 40",
      }),
    ).toBeInTheDocument();

    expect(
      screen.getByText(
        "updated first page execution",
        {
          selector: "span",
        },
      ),
    ).toBeInTheDocument();

    expect(
      screen.queryByText(
        "first page execution",
        {
          selector: "span",
        },
      ),
    ).not.toBeInTheDocument();

    expect(fetchMock).toHaveBeenCalledTimes(
      requestCountBeforeUpdate,
    );
  },
);
