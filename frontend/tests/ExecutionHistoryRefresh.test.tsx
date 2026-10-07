import { act, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, expect, test, vi } from "vitest";

import { ExecutionHistory } from "../src/components/ExecutionHistory";
import { deferredResponse, executionFixture, jsonResponse } from "./taskFixtures";

afterEach(() => {
  vi.unstubAllGlobals();
});

test("reloads the first page on refresh and continues pagination with current filters", async () => {
  const queries: URL[] = [];
  const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
    const url = new URL(String(input), "http://localhost");
    queries.push(url);
    return jsonResponse(url.searchParams.get("offset") === "0"
      ? [executionFixture(101, "failed"), executionFixture(100, "failed")]
      : [executionFixture(99, "failed")]);
  });
  vi.stubGlobal("fetch", fetchMock);
  const onSelectExecution = vi.fn();
  const { rerender } = render(
    <ExecutionHistory onSelectExecution={onSelectExecution} pageSize={2} />,
  );

  await screen.findByRole("button", { name: "Execution 101" });
  fireEvent.change(screen.getByLabelText("Status"), { target: { value: "failed" } });
  await screen.findByRole("button", { name: "Execution 101" });
  fireEvent.change(screen.getByLabelText("Agent ID"), { target: { value: "7" } });
  await screen.findByRole("button", { name: "Execution 101" });
  fireEvent.click(screen.getByRole("button", { name: "Load more" }));
  await screen.findByRole("button", { name: "Execution 99" });

  rerender(<ExecutionHistory
    onSelectExecution={onSelectExecution} pageSize={2} refreshKey={1}
  />);
  await screen.findByRole("button", { name: "Execution 101" });
  expect(screen.queryByRole("button", { name: "Execution 99" })).not.toBeInTheDocument();
  expect(screen.getByLabelText("Status")).toHaveValue("failed");
  expect(screen.getByLabelText("Agent ID")).toHaveValue(7);
  expect(queries.at(-1)!.searchParams.get("offset")).toBe("0");
  fireEvent.click(screen.getByRole("button", { name: "Load more" }));
  await screen.findByRole("button", { name: "Execution 99" });
  const nextPage = queries.at(-1)!;
  expect(nextPage.searchParams.get("offset")).toBe("2");
  expect(nextPage.searchParams.get("status")).toBe("failed");
  expect(nextPage.searchParams.get("agent_id")).toBe("7");
});

test("ignores a stale load-more response after a history refresh", async () => {
  const pending = deferredResponse();
  let firstPageRequests = 0;
  vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL) => {
    const url = new URL(String(input), "http://localhost");
    if (url.searchParams.get("offset") === "2") return pending.promise;
    firstPageRequests += 1;
    return jsonResponse(firstPageRequests === 1
      ? [executionFixture(100), executionFixture(99)]
      : [executionFixture(101), executionFixture(100)]);
  }));
  const onSelectExecution = vi.fn();
  const { rerender } = render(
    <ExecutionHistory onSelectExecution={onSelectExecution} pageSize={2} />,
  );
  await screen.findByRole("button", { name: "Execution 100" });
  fireEvent.click(screen.getByRole("button", { name: "Load more" }));
  expect(screen.getByRole("button", { name: "Loading..." })).toBeDisabled();

  rerender(<ExecutionHistory
    onSelectExecution={onSelectExecution} pageSize={2} refreshKey={1}
  />);
  await screen.findByRole("button", { name: "Execution 101" });
  await act(async () => pending.resolve(jsonResponse([executionFixture(98)])));
  expect(screen.queryByRole("button", { name: "Execution 98" })).not.toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Load more" })).toBeEnabled();
  expect(screen.getByRole("button", { name: "Execution 101" })).toBeInTheDocument();
});
