import { fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, expect, test, vi } from "vitest";

import { HomePage } from "../src/pages/HomePage";
import { executionFixture, jsonResponse, testAgent } from "./taskFixtures";

afterEach(() => {
  vi.unstubAllGlobals();
});

test.each(["completed", "failed"])(
  "opens a %s execution and refreshes history after submitting a task",
  async (status) => {
    const execution = executionFixture(101, status);
    let submitted = false;
    const historyQueries: URL[] = [];
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = new URL(String(input), "http://localhost");
      const method = init?.method ?? "GET";

      if (url.pathname === "/agents" && method === "GET") {
        return jsonResponse([testAgent]);
      }
      if (url.pathname === "/memories/7") return jsonResponse([]);
      if (url.pathname === "/agents/7/chat" && method === "POST") {
        submitted = true;
        return jsonResponse({
          execution_id: execution.id, response: execution.output, status,
        });
      }
      if (url.pathname === "/executions") {
        historyQueries.push(url);
        return jsonResponse(submitted ? [execution] : []);
      }
      if (url.pathname === "/executions/101") {
        return jsonResponse(execution);
      }
      if (url.pathname === "/executions/101/snapshot") {
        return jsonResponse({ detail: "Execution snapshot not found" }, 404);
      }
      if (
        url.pathname === "/executions/101/trace" ||
        url.pathname === "/executions/101/replays"
      ) {
        return jsonResponse([]);
      }
      throw new Error(`Unexpected request: ${method} ${url}`);
    });
    vi.stubGlobal("fetch", fetchMock);
    render(<HomePage />);

    await screen.findByText("No executions found.");
    await screen.findByRole("option", { name: "Calculator Agent (ID: 7)" });
    fireEvent.change(screen.getByLabelText("Agent"), { target: { value: "7" } });
    fireEvent.change(screen.getByLabelText("Task"), {
      target: { value: "Calculate 40 + 2" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Submit task" }));

    const summary = within((await screen.findByRole("heading", {
      name: "Execution Summary",
    })).closest("section")!);
    expect(summary.getByText(status, { selector: "dd" })).toBeInTheDocument();
    expect(screen.getByLabelText("Execution ID")).toHaveValue("101");
    const history = within(screen.getByRole("heading", {
      name: "Execution History",
    }).closest("section")!);
    expect(await history.findByRole("button", {
      name: "Execution 101",
    })).toBeInTheDocument();
    expect(history.getByText(status, { selector: "span" })).toBeInTheDocument();
    expect(historyQueries).toHaveLength(2);
    expect(historyQueries[1].searchParams.get("offset")).toBe("0");
  },
);

test("keeps active history filters when the submitted execution does not match", async () => {
  const execution = executionFixture(101);
  const filteredExecution = { ...executionFixture(80, "failed"), agent_id: 2 };
  let submitted = false;
  const historyQueries: URL[] = [];
  vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = new URL(String(input), "http://localhost");
    if (url.pathname === "/agents") return jsonResponse([testAgent]);
    if (url.pathname === "/memories/7") return jsonResponse([]);
    if (url.pathname === "/agents/7/chat" && init?.method === "POST") {
      submitted = true;
      return jsonResponse({ execution_id: 101, response: "42", status: "completed" });
    }
    if (url.pathname === "/executions") {
      historyQueries.push(url);
      const hasFilters = url.searchParams.get("status") === "failed" ||
        url.searchParams.get("agent_id") === "2";
      return jsonResponse(hasFilters ? [filteredExecution] : submitted ? [execution] : []);
    }
    if (url.pathname === "/executions/101") return jsonResponse(execution);
    if (url.pathname === "/executions/101/snapshot") return jsonResponse({}, 404);
    if (url.pathname.endsWith("/trace") || url.pathname.endsWith("/replays")) {
      return jsonResponse([]);
    }
    throw new Error(`Unexpected request: ${url}`);
  }));
  render(<HomePage />);

  await screen.findByText("No executions found.");
  fireEvent.change(screen.getByLabelText("Status"), { target: { value: "failed" } });
  await screen.findByRole("button", { name: "Execution 80" });
  fireEvent.change(screen.getByLabelText("Agent ID"), { target: { value: "2" } });
  await screen.findByRole("button", { name: "Execution 80" });
  await screen.findByRole("option", { name: "Calculator Agent (ID: 7)" });
  fireEvent.change(screen.getByLabelText("Agent"), { target: { value: "7" } });
  fireEvent.change(screen.getByLabelText("Task"), { target: { value: "Calculate 40 + 2" } });
  fireEvent.click(screen.getByRole("button", { name: "Submit task" }));

  await screen.findByRole("heading", { name: "Execution Summary" });
  expect(await screen.findByRole("button", { name: "Execution 80" })).toBeInTheDocument();
  expect(screen.queryByRole("button", { name: "Execution 101" })).not.toBeInTheDocument();
  expect(screen.getByLabelText("Status")).toHaveValue("failed");
  expect(screen.getByLabelText("Agent ID")).toHaveValue(2);
  const query = historyQueries.at(-1)!;
  expect(query.searchParams.get("status")).toBe("failed");
  expect(query.searchParams.get("agent_id")).toBe("2");
  expect(query.searchParams.get("offset")).toBe("0");
});
