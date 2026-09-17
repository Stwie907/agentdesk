import {
  fireEvent,
  render,
  screen,
  within,
} from "@testing-library/react";
import {
  afterEach,
  expect,
  test,
  vi,
} from "vitest";

import { HomePage } from "../src/pages/HomePage";

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

test(
  "synchronizes a retried execution from inspector back into history",
  async () => {
    const failedExecution = {
      id: 42,
      agent_id: 1,
      input: "failed execution",
      output: null,
      status: "failed",
      retry_count: 2,
      failure_type: "tool_error",
      failure_message: "calculator failed",
      replay_of_execution_id: null,
      created_at: "2026-09-17T10:00:00",
    };

    const pendingExecution = {
      ...failedExecution,
      status: "pending",
      retry_count: 0,
      failure_type: null,
      failure_message: null,
    };

    const fetchMock = vi.fn(
      async (
        input: RequestInfo | URL,
        init?: RequestInit,
      ): Promise<Response> => {
        const url = String(input);
        const method = init?.method ?? "GET";

        if (
          method === "GET" &&
          url.includes("/executions?")
        ) {
          return jsonResponse([failedExecution]);
        }

        if (
          method === "GET" &&
          url.endsWith("/executions/42/trace")
        ) {
          return jsonResponse([]);
        }

        if (
          method === "GET" &&
          url.endsWith("/executions/42/snapshot")
        ) {
          return jsonResponse(
            {
              detail: "Execution snapshot not found",
            },
            404,
          );
        }

        if (
          method === "GET" &&
          url.endsWith("/executions/42/replays")
        ) {
          return jsonResponse([]);
        }

        if (
          method === "GET" &&
          url.endsWith("/executions/42")
        ) {
          return jsonResponse(failedExecution);
        }

        if (
          method === "POST" &&
          url.endsWith("/executions/42/retry")
        ) {
          return jsonResponse(pendingExecution);
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

    render(<HomePage />);

    const historyHeading = await screen.findByRole(
      "heading",
      {
        name: "Execution History",
      },
    );

    const historySection =
      historyHeading.closest("section");

    expect(historySection).not.toBeNull();

    const history = within(
      historySection as HTMLElement,
    );

    const executionButton =
      await history.findByRole("button", {
        name: "Execution 42",
      });

    expect(
      history.getByText("failed", {
        selector: "span",
      }),
    ).toBeInTheDocument();

    fireEvent.click(executionButton);

    expect(
      await screen.findByRole("button", {
        name: "Retry execution",
      }),
    ).toBeInTheDocument();

    fireEvent.click(
      screen.getByRole("button", {
        name: "Retry execution",
      }),
    );

    const summaryHeading =
      await screen.findByRole("heading", {
        name: "Execution Summary",
      });

    const summarySection =
      summaryHeading.closest("section");

    expect(summarySection).not.toBeNull();

    expect(
      within(
        summarySection as HTMLElement,
      ).getByText("pending", {
        selector: "dd",
      }),
    ).toBeInTheDocument();

    expect(
      await history.findByText("pending", {
        selector: "span",
      }),
    ).toBeInTheDocument();
  },
);


test(
  "synchronizes a cancelled execution from inspector back into history",
  async () => {
    const pendingExecution = {
      id: 42,
      agent_id: 1,
      input: "pending execution",
      output: null,
      status: "pending",
      retry_count: 0,
      failure_type: null,
      failure_message: null,
      replay_of_execution_id: null,
      created_at: "2026-09-17T11:00:00",
    };

    const unrelatedExecution = {
      id: 41,
      agent_id: 2,
      input: "unrelated execution",
      output: "done",
      status: "completed",
      retry_count: 0,
      failure_type: null,
      failure_message: null,
      replay_of_execution_id: null,
      created_at: "2026-09-17T10:00:00",
    };

    const cancelledExecution = {
      ...pendingExecution,
      status: "cancelled",
    };

    const fetchMock = vi.fn(
      async (
        input: RequestInfo | URL,
        init?: RequestInit,
      ): Promise<Response> => {
        const url = String(input);
        const method = init?.method ?? "GET";

        if (
          method === "GET" &&
          url.includes("/executions?")
        ) {
          return jsonResponse([
            pendingExecution,
            unrelatedExecution,
          ]);
        }

        if (
          method === "GET" &&
          url.endsWith("/executions/42/trace")
        ) {
          return jsonResponse([]);
        }

        if (
          method === "GET" &&
          url.endsWith("/executions/42/snapshot")
        ) {
          return jsonResponse(
            {
              detail: "Execution snapshot not found",
            },
            404,
          );
        }

        if (
          method === "GET" &&
          url.endsWith("/executions/42/replays")
        ) {
          return jsonResponse([]);
        }

        if (
          method === "GET" &&
          url.endsWith("/executions/42")
        ) {
          return jsonResponse(pendingExecution);
        }

        if (
          method === "POST" &&
          url.endsWith("/executions/42/cancel")
        ) {
          return jsonResponse(cancelledExecution);
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

    render(<HomePage />);

    const historyHeading = await screen.findByRole(
      "heading",
      {
        name: "Execution History",
      },
    );

    const historySection =
      historyHeading.closest("section");

    expect(historySection).not.toBeNull();

    const history = within(
      historySection as HTMLElement,
    );

    fireEvent.click(
      await history.findByRole("button", {
        name: "Execution 42",
      }),
    );

    fireEvent.click(
      await screen.findByRole("button", {
        name: "Cancel execution",
      }),
    );

    expect(
      await history.findByText("cancelled", {
        selector: "span",
      }),
    ).toBeInTheDocument();

    expect(
      history.getByText("unrelated execution", {
        selector: "span",
      }),
    ).toBeInTheDocument();

    expect(
      history.getByText("completed", {
        selector: "span",
      }),
    ).toBeInTheDocument();
  },
);

test(
  "synchronizes a refreshed completed execution back into history",
  async () => {
    const pendingExecution = {
      id: 42,
      agent_id: 1,
      input: "pending execution",
      output: null,
      status: "pending",
      retry_count: 0,
      failure_type: null,
      failure_message: null,
      replay_of_execution_id: null,
      created_at: "2026-09-17T12:00:00",
    };

    const completedExecution = {
      ...pendingExecution,
      output: "42",
      status: "completed",
    };

    let executionRequestCount = 0;

    const fetchMock = vi.fn(
      async (
        input: RequestInfo | URL,
        init?: RequestInit,
      ): Promise<Response> => {
        const url = String(input);
        const method = init?.method ?? "GET";

        if (
          method === "GET" &&
          url.includes("/executions?")
        ) {
          return jsonResponse([pendingExecution]);
        }

        if (
          method === "GET" &&
          url.endsWith("/executions/42/trace")
        ) {
          return jsonResponse([]);
        }

        if (
          method === "GET" &&
          url.endsWith("/executions/42/snapshot")
        ) {
          return jsonResponse(
            {
              detail: "Execution snapshot not found",
            },
            404,
          );
        }

        if (
          method === "GET" &&
          url.endsWith("/executions/42/replays")
        ) {
          return jsonResponse([]);
        }

        if (
          method === "GET" &&
          url.endsWith("/executions/42")
        ) {
          executionRequestCount += 1;

          return jsonResponse(
            executionRequestCount === 1
              ? pendingExecution
              : completedExecution,
          );
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

    render(<HomePage />);

    const historyHeading = await screen.findByRole(
      "heading",
      {
        name: "Execution History",
      },
    );

    const historySection =
      historyHeading.closest("section");

    expect(historySection).not.toBeNull();

    const history = within(
      historySection as HTMLElement,
    );

    fireEvent.click(
      await history.findByRole("button", {
        name: "Execution 42",
      }),
    );

    fireEvent.click(
      await screen.findByRole("button", {
        name: "Refresh execution",
      }),
    );

    expect(
      await history.findByText("completed", {
        selector: "span",
      }),
    ).toBeInTheDocument();

    const outputLabel = screen.getByText("Output", {
      selector: "dt",
    });

    expect(
      outputLabel.nextElementSibling,
    ).toHaveTextContent("42");
  },
);
