import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, expect, test, vi } from "vitest";

import { TaskSubmission } from "../src/components/TaskSubmission";
import { deferredResponse, jsonResponse, testAgent } from "./taskFixtures";

afterEach(() => {
  vi.unstubAllGlobals();
});

async function fillTask(message = "Calculate 40 + 2") {
  await screen.findByRole("option", { name: "Calculator Agent (ID: 7)" });
  fireEvent.change(screen.getByLabelText("Agent"), {
    target: { value: "7" },
  });
  fireEvent.change(screen.getByLabelText("Task"), {
    target: { value: message },
  });
}

test("disables the task form until Agents finish loading", async () => {
  const pending = deferredResponse();
  vi.stubGlobal("fetch", vi.fn(() => pending.promise));
  render(<TaskSubmission onSubmitted={vi.fn()} />);

  expect(screen.getByText("Loading Agents...")).toBeInTheDocument();
  expect(screen.getByLabelText("Agent")).toBeDisabled();
  expect(screen.getByLabelText("Task")).toBeDisabled();
  expect(screen.getByRole("button", { name: "Submit task" })).toBeDisabled();

  await act(async () => pending.resolve(jsonResponse([testAgent])));
  expect(screen.getByLabelText("Agent")).toBeEnabled();
});

test("shows an empty state when no Agents are available", async () => {
  vi.stubGlobal("fetch", vi.fn(async () => jsonResponse([])));
  render(<TaskSubmission onSubmitted={vi.fn()} />);

  expect(await screen.findByText(/No Agents available/)).toBeInTheDocument();
  expect(screen.getByLabelText("Agent")).toBeDisabled();
  expect(screen.getByRole("button", { name: "Submit task" })).toBeDisabled();
});

test("allows the Agent list to be reloaded after an error", async () => {
  const fetchMock = vi.fn()
    .mockResolvedValueOnce(jsonResponse({ detail: "Agents unavailable" }, 503))
    .mockResolvedValueOnce(jsonResponse([testAgent]));
  vi.stubGlobal("fetch", fetchMock);
  render(<TaskSubmission onSubmitted={vi.fn()} />);

  expect(await screen.findByRole("alert")).toHaveTextContent("Agents unavailable");
  expect(screen.getByRole("button", { name: "Submit task" })).toBeDisabled();
  fireEvent.click(screen.getByRole("button", { name: "Reload Agents" }));

  expect(await screen.findByRole("option", {
    name: "Calculator Agent (ID: 7)",
  })).toBeInTheDocument();
  expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  expect(fetchMock).toHaveBeenNthCalledWith(2, "/agents");
});

test("prevents requests with no Agent selected or blank input", async () => {
  const fetchMock = vi.fn(async () => jsonResponse([testAgent]));
  vi.stubGlobal("fetch", fetchMock);
  render(<TaskSubmission onSubmitted={vi.fn()} />);

  await screen.findByRole("option", { name: "Calculator Agent (ID: 7)" });
  const input = screen.getByLabelText("Task");
  const form = input.closest("form")!;
  fireEvent.change(input, { target: { value: "Hello" } });
  fireEvent.submit(form);
  expect(screen.getByRole("button", { name: "Submit task" })).toBeDisabled();

  await fillTask("  \n  ");
  fireEvent.submit(form);
  expect(screen.getByRole("button", { name: "Submit task" })).toBeDisabled();
  expect(fetchMock).toHaveBeenCalledTimes(1);
});

test("posts a JSON task to the selected Agent and reports its execution ID", async () => {
  const fetchMock = vi.fn()
    .mockResolvedValueOnce(jsonResponse([testAgent]))
    .mockResolvedValueOnce(jsonResponse({
      execution_id: 101,
      response: "42",
      status: "completed",
    }));
  const onSubmitted = vi.fn();
  vi.stubGlobal("fetch", fetchMock);
  render(<TaskSubmission onSubmitted={onSubmitted} />);

  await fillTask("  Calculate 40 + 2  ");
  fireEvent.click(screen.getByRole("button", { name: "Submit task" }));

  await waitFor(() => expect(onSubmitted).toHaveBeenCalledWith(101));
  expect(fetchMock).toHaveBeenLastCalledWith("/agents/7/chat", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ message: "Calculate 40 + 2" }),
  });
  expect(screen.getByRole("status")).toHaveTextContent(
    "Execution 101 returned with status: completed.",
  );
  expect(screen.getByLabelText("Task")).toHaveValue("");
});

test("blocks repeated form submission while the chat request is pending", async () => {
  const pending = deferredResponse();
  const fetchMock = vi.fn()
    .mockResolvedValueOnce(jsonResponse([testAgent]))
    .mockReturnValue(pending.promise);
  const onSubmitted = vi.fn();
  vi.stubGlobal("fetch", fetchMock);
  render(<TaskSubmission onSubmitted={onSubmitted} />);

  await fillTask();
  const form = screen.getByLabelText("Task").closest("form")!;
  fireEvent.submit(form);
  fireEvent.submit(form);
  fireEvent.submit(form);

  expect(screen.getByRole("button", { name: "Submitting..." })).toBeDisabled();
  expect(screen.getByLabelText("Agent")).toBeDisabled();
  expect(screen.getByLabelText("Task")).toBeDisabled();
  expect(screen.getByRole("status")).toHaveTextContent("Waiting for the Agent to finish...");
  expect(fetchMock).toHaveBeenCalledTimes(2);

  await act(async () => pending.resolve(jsonResponse({
    execution_id: 101, response: "42", status: "completed",
  })));
  expect(onSubmitted).toHaveBeenCalledTimes(1);
});

test("preserves failed input and allows an edited task to be submitted", async () => {
  const fetchMock = vi.fn()
    .mockResolvedValueOnce(jsonResponse([testAgent]))
    .mockResolvedValueOnce(jsonResponse({ detail: "Agent not found" }, 404))
    .mockResolvedValueOnce(jsonResponse({
      execution_id: 102, response: "10", status: "completed",
    }));
  const onSubmitted = vi.fn();
  vi.stubGlobal("fetch", fetchMock);
  render(<TaskSubmission onSubmitted={onSubmitted} />);

  await fillTask();
  fireEvent.click(screen.getByRole("button", { name: "Submit task" }));
  expect(await screen.findByRole("alert")).toHaveTextContent("Agent not found");
  expect(screen.getByLabelText("Task")).toHaveValue("Calculate 40 + 2");
  expect(screen.getByLabelText("Agent")).toHaveValue("7");
  expect(onSubmitted).not.toHaveBeenCalled();

  fireEvent.change(screen.getByLabelText("Task"), {
    target: { value: "Calculate 5 + 5" },
  });
  fireEvent.click(screen.getByRole("button", { name: "Submit task" }));
  await waitFor(() => expect(onSubmitted).toHaveBeenCalledWith(102));
  expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  expect(fetchMock).toHaveBeenLastCalledWith("/agents/7/chat", expect.objectContaining({
    body: JSON.stringify({ message: "Calculate 5 + 5" }),
  }));
});

test("shows a connection error without clearing input or retrying automatically", async () => {
  const fetchMock = vi.fn()
    .mockResolvedValueOnce(jsonResponse([testAgent]))
    .mockRejectedValueOnce(new TypeError("Failed to fetch"));
  vi.stubGlobal("fetch", fetchMock);
  render(<TaskSubmission onSubmitted={vi.fn()} />);

  await fillTask();
  fireEvent.click(screen.getByRole("button", { name: "Submit task" }));
  expect(await screen.findByRole("alert")).toHaveTextContent("Unable to submit task.");
  expect(screen.getByLabelText("Task")).toHaveValue("Calculate 40 + 2");
  expect(screen.getByRole("button", { name: "Submit task" })).toBeEnabled();
  expect(fetchMock).toHaveBeenCalledTimes(2);
});

test("shows a stable error when an HTTP failure has no JSON body", async () => {
  const fetchMock = vi.fn()
    .mockResolvedValueOnce(jsonResponse([testAgent]))
    .mockResolvedValueOnce(new Response("Bad Gateway", { status: 502 }));
  vi.stubGlobal("fetch", fetchMock);
  render(<TaskSubmission onSubmitted={vi.fn()} />);

  await fillTask();
  fireEvent.click(screen.getByRole("button", { name: "Submit task" }));
  expect(await screen.findByRole("alert")).toHaveTextContent("Request failed with status 502");
  expect(screen.getByLabelText("Task")).toHaveValue("Calculate 40 + 2");
});
