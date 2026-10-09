import { act, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, expect, test, vi } from "vitest";

import { MemoryPanel } from "../src/components/MemoryPanel";
import { deferredResponse, jsonResponse } from "./taskFixtures";

afterEach(() => vi.unstubAllGlobals());

const memory = { id: 11, agent_id: 7, content: "Python original.", created_at: "2026-10-09T08:00:00" };
const updated = { ...memory, content: "Rust updated." };

async function panel() {
  const fetchMock = vi.fn().mockResolvedValueOnce(jsonResponse([memory]));
  vi.stubGlobal("fetch", fetchMock);
  const view = render(<MemoryPanel agentId={7} refreshKey={0} />);
  await screen.findByText(memory.content);
  return { fetchMock, ...view };
}

function start() { fireEvent.click(screen.getByRole("button", { name: "Edit memory 11" })); }
function draft(content = updated.content) {
  fireEvent.change(screen.getByLabelText("Edited memory content"), { target: { value: content } });
}

test("opens the original content and can cancel without making a request or losing an add draft", async () => {
  const { fetchMock } = await panel();
  fireEvent.change(screen.getByLabelText("Memory content"), { target: { value: "New memory draft" } });
  start();
  expect(screen.getByLabelText("Edited memory content")).toHaveValue(memory.content);
  expect(screen.getByRole("button", { name: "Save changes" })).toBeDisabled();
  expect(screen.getByRole("button", { name: "Delete memory 11" })).toBeDisabled();
  draft();
  fireEvent.click(screen.getByRole("button", { name: "Cancel editing" }));
  expect(screen.queryByLabelText("Edited memory content")).not.toBeInTheDocument();
  expect(screen.getByText(memory.content)).toBeInTheDocument();
  expect(screen.getByLabelText("Memory content")).toHaveValue("New memory draft");
  expect(fetchMock).toHaveBeenCalledTimes(1);
});

test("rejects blank and overlong edits without a request", async () => {
  const { fetchMock } = await panel();
  start();
  for (const value of [" \n ", "x".repeat(2001), memory.content + " "]) {
    draft(value);
    fireEvent.submit(screen.getByRole("form", { name: "Edit memory 11" }));
    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(screen.getByRole("button", { name: "Save changes" })).toBeDisabled();
  }
});

test("sends a scoped conditional PATCH, locks writes and cancels, and preserves identity", async () => {
  const { fetchMock } = await panel();
  const pending = deferredResponse();
  fetchMock.mockReturnValueOnce(pending.promise);
  start(); draft("  " + updated.content + "  ");
  const form = screen.getByRole("form", { name: "Edit memory 11" });
  fireEvent.submit(form); fireEvent.submit(form);
  expect(fetchMock).toHaveBeenCalledTimes(2);
  expect(fetchMock).toHaveBeenLastCalledWith("/memories/item/11?agent_id=7", {
    method: "PATCH", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ content: updated.content, expected_content: memory.content }),
  });
  expect(screen.getByRole("button", { name: "Cancel editing" })).toBeDisabled();
  expect(screen.getByRole("button", { name: "Reload memories" })).toBeDisabled();
  expect(screen.getByLabelText("Edited memory content")).toBeDisabled();
  await act(async () => { pending.resolve(jsonResponse(updated)); });
  expect(await screen.findByText("Memory 11 updated.")).toBeInTheDocument();
  expect(screen.queryByText(memory.content)).not.toBeInTheDocument();
  expect(screen.getByText(updated.content)).toBeInTheDocument();
  const list = screen.getByRole("list", { name: "Saved memories" });
  expect(within(list).getAllByRole("listitem")).toHaveLength(1);
  expect(list.textContent).toContain("Memory 11 · Created 2026-10-09 08:00:00");
});

test.each(["network", "validation", "duplicate", "stale", "missing"])("preserves the edit draft after %s failure", async (kind) => {
  const { fetchMock } = await panel();
  const cases: Record<string, [number, string]> = {
    validation: [422, "bad input"], duplicate: [409, "An identical memory already exists"],
    stale: [409, "Memory changed since it was loaded"], missing: [404, "Memory not found for this Agent"],
  };
  if (kind === "network") fetchMock.mockRejectedValueOnce(new TypeError("offline"));
  else fetchMock.mockResolvedValueOnce(jsonResponse({ detail: cases[kind][1] }, cases[kind][0]));
  start(); draft();
  fireEvent.click(screen.getByRole("button", { name: "Save changes" }));
  await screen.findByRole("alert");
  expect(screen.getByLabelText("Edited memory content")).toHaveValue(updated.content);
  expect(screen.getByText(memory.content)).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Save changes" })).toBeEnabled();
  expect(fetchMock).toHaveBeenCalledTimes(2);
});

test.each([
  { ...updated, id: 12 }, { ...updated, agent_id: 8 },
  { ...updated, created_at: "2026-10-10T00:00:00" }, { ...updated, content: "Unexpected" },
])("rejects mismatched edit response data: %j", async (result) => {
  const { fetchMock } = await panel();
  fetchMock.mockResolvedValueOnce(jsonResponse(result));
  start(); draft(); fireEvent.click(screen.getByRole("button", { name: "Save changes" }));
  expect(await screen.findByRole("alert")).toHaveTextContent("invalid memory");
  expect(screen.getByLabelText("Edited memory content")).toHaveValue(updated.content);
  expect(screen.getByText(memory.content)).toBeInTheDocument();
  expect(screen.queryByText("Memory 11 updated.")).not.toBeInTheDocument();
});

test.each([false, true])("ignores a late edit after an Agent switch, failure=%s", async (failed) => {
  const { fetchMock, rerender } = await panel();
  const pending = deferredResponse();
  const current = { ...memory, id: 22, agent_id: 8, content: "Other Agent memory" };
  fetchMock.mockReturnValueOnce(pending.promise).mockResolvedValueOnce(jsonResponse([current]));
  start(); draft(); fireEvent.click(screen.getByRole("button", { name: "Save changes" }));
  rerender(<MemoryPanel agentId={8} />);
  await screen.findByText(current.content);
  fireEvent.change(screen.getByLabelText("Memory content"), { target: { value: "Other Agent draft" } });
  await act(async () => {
    if (failed) pending.resolve(jsonResponse({ detail: "Late conflict" }, 409));
    else pending.resolve(jsonResponse(updated));
  });
  expect(screen.getByText(current.content)).toBeInTheDocument();
  expect(screen.getByLabelText("Memory content")).toHaveValue("Other Agent draft");
  expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  expect(screen.queryByText("Memory 11 updated.")).not.toBeInTheDocument();
});

test("clears preview when saving an edit and ignores an older search response", async () => {
  const { fetchMock } = await panel();
  const pending = deferredResponse();
  fetchMock.mockReturnValueOnce(pending.promise).mockResolvedValueOnce(jsonResponse(updated));
  fireEvent.change(screen.getByLabelText("Memory search query"), { target: { value: "Python" } });
  fireEvent.click(screen.getByRole("button", { name: "Search memories" }));
  start(); draft(); fireEvent.click(screen.getByRole("button", { name: "Save changes" }));
  await screen.findByText(updated.content);
  await act(async () => pending.resolve(jsonResponse({ agent_id: 7, query: "Python", limit: 5,
    results: [{ memory, score: 1, matched_terms: ["python"] }] })));
  expect(screen.queryByRole("list", { name: "Memory search results" })).not.toBeInTheDocument();
});

test.each(["save", "cancel"])("defers a chat refresh while drafting and resumes after %s", async (action) => {
  const { fetchMock, rerender } = await panel();
  start(); draft();
  rerender(<MemoryPanel agentId={7} refreshKey={1} />);
  expect(fetchMock).toHaveBeenCalledTimes(1);
  expect(screen.getByLabelText("Edited memory content")).toHaveValue(updated.content);
  if (action === "save") fetchMock.mockResolvedValueOnce(jsonResponse(updated));
  fetchMock.mockResolvedValueOnce(jsonResponse([{ ...updated, content: "Latest refreshed memory" }]));
  fireEvent.click(screen.getByRole("button", { name: action === "save" ? "Save changes" : "Cancel editing" }));
  await screen.findByText("Latest refreshed memory");
  expect(fetchMock).toHaveBeenCalledTimes(action === "save" ? 3 : 2);
});
