import { StrictMode } from "react";
import { act, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, expect, test, vi } from "vitest";

import { UserMemoryPanel } from "../src/components/UserMemoryPanel";
import { deferredResponse, jsonResponse } from "./taskFixtures";

afterEach(() => vi.unstubAllGlobals());
const memory = { id: 11, user_id: 3, content: "Python shared preference.", created_at: "2026-10-09T08:00:00" };
const updated = { ...memory, content: "Rust shared preference." };
const context = { agent_id: 7, user_id: 3, username: "demo", memories: [memory] };
const preview = { agent_id: 7, user_id: 3, query: "Python", limit: 5, results: [{ memory, score: 1, matched_terms: ["python"] }] };

async function panel() {
  const fetchMock = vi.fn().mockResolvedValueOnce(jsonResponse(context));
  vi.stubGlobal("fetch", fetchMock);
  const view = render(<UserMemoryPanel agentId={7} />);
  expect(fetchMock).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole("button", { name: "Show shared memories" }));
  await screen.findByText(memory.content);
  return { fetchMock, ...view };
}
function edit() { fireEvent.click(screen.getByRole("button", { name: "Edit shared memory 11" })); }
function draft(content = updated.content) { fireEvent.change(screen.getByLabelText("Edited shared memory content"), { target: { value: content } }); }
function query(value = "Python") { fireEvent.change(screen.getByLabelText("Shared memory search query"), { target: { value } }); }

test("waits for a selection and an explicit open before fetching", async () => {
  const fetchMock = vi.fn().mockResolvedValueOnce(jsonResponse(context));
  vi.stubGlobal("fetch", fetchMock);
  const { rerender } = render(<UserMemoryPanel agentId={null} />);
  expect(screen.getByText(/Select an Agent above/)).toBeInTheDocument();
  rerender(<UserMemoryPanel agentId={7} />);
  expect(fetchMock).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole("button", { name: "Show shared memories" }));
  expect(await screen.findByText("Shared memories for demo (User 3)")).toBeInTheDocument();
  expect(fetchMock).toHaveBeenCalledWith("/user-memories/for-agent/7", { cache: "no-store" });
});

test("saves with the loaded owner, trims content, and locks duplicate submissions", async () => {
  const { fetchMock } = await panel();
  const pending = deferredResponse();
  fetchMock.mockReturnValueOnce(pending.promise);
  const content = screen.getByLabelText("Shared memory content");
  fireEvent.change(content, { target: { value: "  " + memory.content + "  " } });
  const form = content.closest("form")!;
  fireEvent.submit(form); fireEvent.submit(form);
  expect(fetchMock).toHaveBeenCalledTimes(2);
  expect(fetchMock).toHaveBeenLastCalledWith("/user-memories/for-agent/7", {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ user_id: 3, content: memory.content }),
  });
  expect(screen.getByRole("button", { name: "Reload shared memories" })).toBeDisabled();
  await act(async () => pending.resolve(jsonResponse(memory)));
  expect(await screen.findByText("Shared memory 11 saved.")).toBeInTheDocument();
  expect(content).toHaveValue("");
  expect(within(screen.getByRole("list", { name: "Saved shared memories" })).getAllByRole("listitem")).toHaveLength(1);
});

test("conditional edit preserves ID and time and cancel preserves the add draft", async () => {
  const { fetchMock } = await panel();
  fireEvent.change(screen.getByLabelText("Shared memory content"), { target: { value: "Keep add draft" } });
  edit();
  expect(screen.getByRole("button", { name: "Save shared changes" })).toBeDisabled();
  draft(); fireEvent.click(screen.getByRole("button", { name: "Cancel shared editing" }));
  expect(screen.getByLabelText("Shared memory content")).toHaveValue("Keep add draft");
  expect(fetchMock).toHaveBeenCalledTimes(1);
  const pending = deferredResponse();
  fetchMock.mockReturnValueOnce(pending.promise);
  edit(); draft("  " + updated.content + "  ");
  const form = screen.getByRole("form", { name: "Edit shared memory 11" });
  fireEvent.submit(form); fireEvent.submit(form);
  expect(fetchMock).toHaveBeenLastCalledWith("/user-memories/item/11?agent_id=7&user_id=3", {
    method: "PATCH", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ content: updated.content, expected_content: memory.content }),
  });
  expect(fetchMock).toHaveBeenCalledTimes(2);
  expect(screen.getByRole("button", { name: "Cancel shared editing" })).toBeDisabled();
  expect(screen.getByRole("button", { name: "Delete shared memory 11" })).toBeDisabled();
  await act(async () => pending.resolve(jsonResponse(updated)));
  expect(await screen.findByText("Shared memory 11 updated.")).toBeInTheDocument();
  expect(screen.getByRole("list", { name: "Saved shared memories" })).toHaveTextContent("Created 2026-10-09 08:00:00");
});

test.each([" \n ", "x".repeat(2001), memory.content + " "])("invalid or unchanged draft makes no edit request", async value => {
  const { fetchMock } = await panel();
  edit(); draft(value);
  fireEvent.submit(screen.getByRole("form", { name: "Edit shared memory 11" }));
  expect(screen.getByRole("button", { name: "Save shared changes" })).toBeDisabled();
  expect(fetchMock).toHaveBeenCalledTimes(1);
});

test.each(["network", "validation", "duplicate", "stale", "owner changed"])("retains a draft after %s failure", async kind => {
  const { fetchMock } = await panel();
  if (kind === "network") fetchMock.mockRejectedValueOnce(new TypeError("offline"));
  else fetchMock.mockResolvedValueOnce(jsonResponse({ detail: kind }, kind === "validation" ? 422 : kind === "owner changed" ? 404 : 409));
  edit(); draft(); fireEvent.click(screen.getByRole("button", { name: "Save shared changes" }));
  await screen.findByRole("alert");
  expect(screen.getByLabelText("Edited shared memory content")).toHaveValue(updated.content);
  expect(screen.getByText(memory.content)).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Save shared changes" })).toBeEnabled();
});

test.each([{ ...updated, id: 12 }, { ...updated, user_id: 4 }, { ...updated, created_at: "changed" }, { ...updated, content: "Wrong" }])(
  "rejects mismatched edit response %j", async result => {
    const { fetchMock } = await panel();
    fetchMock.mockResolvedValueOnce(jsonResponse(result));
    edit(); draft(); fireEvent.click(screen.getByRole("button", { name: "Save shared changes" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("invalid shared memory data");
    expect(screen.getByText(memory.content)).toBeInTheDocument();
    expect(screen.getByLabelText("Edited shared memory content")).toHaveValue(updated.content);
  });

test("confirms a delete affecting all same-user Agents and keeps the row on failure", async () => {
  const { fetchMock } = await panel();
  fireEvent.click(screen.getByRole("button", { name: "Delete shared memory 11" }));
  expect(screen.getByText(/for all Agents belonging to this user/)).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Keep shared memory" }));
  expect(fetchMock).toHaveBeenCalledTimes(1);
  fetchMock.mockResolvedValueOnce(jsonResponse({ detail: "Owner changed" }, 404));
  fireEvent.click(screen.getByRole("button", { name: "Delete shared memory 11" }));
  fireEvent.click(screen.getByRole("button", { name: "Confirm shared delete" }));
  expect(await screen.findByRole("alert")).toHaveTextContent("Owner changed");
  expect(screen.getByText(memory.content)).toBeInTheDocument();
  fetchMock.mockResolvedValueOnce(jsonResponse({ message: "Shared memory deleted successfully" }));
  fireEvent.click(screen.getByRole("button", { name: "Confirm shared delete" }));
  expect(fetchMock).toHaveBeenLastCalledWith("/user-memories/item/11?agent_id=7&user_id=3", { method: "DELETE" });
  expect(await screen.findByText("No shared memories for this user.")).toBeInTheDocument();
});

test("switching to another same-owner Agent reloads shared records and resets drafts", async () => {
  const { fetchMock, rerender } = await panel();
  fireEvent.change(screen.getByLabelText("Shared memory content"), { target: { value: "Unsaved draft" } });
  fetchMock.mockResolvedValueOnce(jsonResponse({ ...context, agent_id: 8 }));
  rerender(<UserMemoryPanel agentId={8} />);
  await screen.findByText(memory.content);
  expect(screen.getByLabelText("Shared memory content")).toHaveValue("");
  expect(fetchMock).toHaveBeenLastCalledWith("/user-memories/for-agent/8", { cache: "no-store" });
});

test.each([false, true])("ignores late writes after switching to another owner, failed=%s", async failed => {
  const { fetchMock, rerender } = await panel();
  const pending = deferredResponse();
  const foreign = { ...memory, id: 22, user_id: 4, content: "Other user's shared preference" };
  fetchMock.mockReturnValueOnce(pending.promise).mockResolvedValueOnce(jsonResponse({ agent_id: 8, user_id: 4, username: "other", memories: [foreign] }));
  edit(); draft(); fireEvent.click(screen.getByRole("button", { name: "Save shared changes" }));
  rerender(<UserMemoryPanel agentId={8} />);
  await screen.findByText(foreign.content);
  fireEvent.change(screen.getByLabelText("Shared memory content"), { target: { value: "Other draft" } });
  await act(async () => pending.resolve(jsonResponse(failed ? { detail: "Late conflict" } : updated, failed ? 409 : 200)));
  expect(screen.getByText(foreign.content)).toBeInTheDocument();
  expect(screen.getByLabelText("Shared memory content")).toHaveValue("Other draft");
  expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  expect(screen.queryByText("Shared memory 11 updated.")).not.toBeInTheDocument();
});

test("search uses trimmed query, locks repeats, and clears stale results on edit", async () => {
  const { fetchMock } = await panel();
  const pending = deferredResponse();
  fetchMock.mockReturnValueOnce(pending.promise).mockResolvedValueOnce(jsonResponse(updated));
  query("  Python  ");
  const form = screen.getByLabelText("Shared memory search query").closest("form")!;
  fireEvent.submit(form); fireEvent.submit(form);
  expect(fetchMock).toHaveBeenCalledTimes(2);
  expect(fetchMock).toHaveBeenLastCalledWith("/user-memories/for-agent/7/search?query=Python&limit=5", { cache: "no-store" });
  edit(); draft(); fireEvent.click(screen.getByRole("button", { name: "Save shared changes" }));
  await screen.findByText(updated.content);
  await act(async () => pending.resolve(jsonResponse(preview)));
  expect(screen.queryByRole("list", { name: "Shared memory search results" })).not.toBeInTheDocument();
});

test("shows keyword scores and ignores an older result after a query change", async () => {
  const { fetchMock } = await panel();
  fetchMock.mockResolvedValueOnce(jsonResponse(preview));
  query(); fireEvent.click(screen.getByRole("button", { name: "Search shared memories" }));
  expect(await screen.findByRole("list", { name: "Shared memory search results" })).toHaveTextContent("Keyword matches: 1");
  const pending = deferredResponse();
  fetchMock.mockReturnValueOnce(pending.promise);
  fireEvent.click(screen.getByRole("button", { name: "Search shared memories" }));
  query("Rust");
  await act(async () => pending.resolve(jsonResponse(preview)));
  expect(screen.queryByRole("list", { name: "Shared memory search results" })).not.toBeInTheDocument();
});

test.each([
  { ...preview, user_id: 4 }, { ...preview, query: "Wrong" }, { ...preview, agent_id: 8 },
  { ...preview, results: [{ memory: { ...memory, user_id: 4 }, score: 1, matched_terms: ["python"] }] },
  { ...preview, results: [{ memory, score: 2, matched_terms: ["python"] }] },
  { ...preview, results: [preview.results[0], preview.results[0]] },
])("rejects invalid or cross-user search response %j", async result => {
  const { fetchMock } = await panel();
  fetchMock.mockResolvedValueOnce(jsonResponse(result));
  query(); fireEvent.click(screen.getByRole("button", { name: "Search shared memories" }));
  expect(await screen.findByRole("alert")).toHaveTextContent("invalid shared memory data");
  expect(screen.queryByRole("list", { name: "Shared memory search results" })).not.toBeInTheDocument();
});

test("can retry a failed load and works under StrictMode", async () => {
  const fetchMock = vi.fn().mockResolvedValue(jsonResponse({ detail: "Unavailable" }, 500));
  vi.stubGlobal("fetch", fetchMock);
  render(<StrictMode><UserMemoryPanel agentId={7} /></StrictMode>);
  fireEvent.click(screen.getByRole("button", { name: "Show shared memories" }));
  await screen.findByRole("alert");
  fetchMock.mockResolvedValueOnce(jsonResponse(context));
  fireEvent.click(screen.getByRole("button", { name: "Reload shared memories" }));
  await screen.findByText(memory.content);
  fetchMock.mockResolvedValueOnce(jsonResponse(updated));
  edit(); draft(); fireEvent.click(screen.getByRole("button", { name: "Save shared changes" }));
  expect(await screen.findByText("Shared memory 11 updated.")).toBeInTheDocument();
});
