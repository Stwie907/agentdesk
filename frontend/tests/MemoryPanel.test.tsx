import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, expect, test, vi } from "vitest";

import { MemoryPanel } from "../src/components/MemoryPanel";
import type { Memory } from "../src/types/memories";
import { deferredResponse, jsonResponse } from "./taskFixtures";

afterEach(() => { vi.unstubAllGlobals(); });

const memory: Memory = {
  id: 11, agent_id: 7, content: "Python answers should be concise.",
  created_at: "2026-10-08T12:00:00",
};

async function emptyPanel() {
  const fetchMock = vi.fn().mockResolvedValueOnce(jsonResponse([]));
  vi.stubGlobal("fetch", fetchMock);
  render(<MemoryPanel agentId={7} />);
  await screen.findByText("No saved memories for this Agent.");
  return fetchMock;
}

function enterMemory(content: string) {
  fireEvent.change(screen.getByLabelText("Memory content"), { target: { value: content } });
}

test("does not request memory until an Agent is selected", () => {
  const fetchMock = vi.fn();
  vi.stubGlobal("fetch", fetchMock);
  render(<MemoryPanel agentId={null} />);
  expect(screen.getByText(/Select an Agent above/)).toBeInTheDocument();
  expect(fetchMock).not.toHaveBeenCalled();
  expect(screen.queryByLabelText("Memory content")).not.toBeInTheDocument();
});

test("disables writes while loading and rejects blank drafts", async () => {
  const pending = deferredResponse();
  vi.stubGlobal("fetch", vi.fn(() => pending.promise));
  render(<MemoryPanel agentId={7} />);
  expect(screen.getByLabelText("Memory content")).toBeDisabled();
  expect(screen.getByRole("button", { name: "Save memory" })).toBeDisabled();
  await act(async () => { pending.resolve(jsonResponse([])); });
  expect(screen.getByLabelText("Memory content")).toBeEnabled();
  enterMemory(" \n ");
  expect(screen.getByRole("button", { name: "Save memory" })).toBeDisabled();
  expect(screen.getByLabelText("Memory content")).toHaveAttribute("maxlength", "2000");
});

test("renders saved content as text", async () => {
  const content = '<img src="x" onerror="alert(1)">\nPython';
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue(jsonResponse([{ ...memory, content }])));
  render(<MemoryPanel agentId={7} />);
  const list = await screen.findByRole("list", { name: "Saved memories" });
  expect(list.textContent).toContain(content);
  expect(list.querySelector("img")).toBeNull();
});

test("trims a save, locks repeated submissions, and displays the returned record", async () => {
  const fetchMock = await emptyPanel();
  const pending = deferredResponse();
  fetchMock.mockReturnValueOnce(pending.promise);
  enterMemory("  " + memory.content + " \n");
  const form = screen.getByRole("button", { name: "Save memory" }).closest("form")!;
  fireEvent.submit(form);
  fireEvent.submit(form);
  expect(fetchMock).toHaveBeenCalledTimes(2);
  expect(fetchMock).toHaveBeenLastCalledWith("/memories", {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ agent_id: 7, content: memory.content }),
  });
  expect(screen.getByLabelText("Memory content")).toBeDisabled();
  await act(async () => { pending.resolve(jsonResponse(memory)); });
  expect(screen.getByText(memory.content)).toBeInTheDocument();
  expect(screen.getByLabelText("Memory content")).toHaveValue("");
  expect(screen.getByRole("status")).toHaveTextContent("Memory 11 saved.");
});

test.each([memory.content, "User's name is Jane."])(
  "reuses a returned ID without adding a duplicate row: %s", async (content) => {
    const fetchMock = vi.fn().mockResolvedValueOnce(jsonResponse([memory]))
      .mockResolvedValueOnce(jsonResponse({ ...memory, content }));
    vi.stubGlobal("fetch", fetchMock);
    render(<MemoryPanel agentId={7} />);
    await screen.findByText(memory.content);
    enterMemory(content);
    fireEvent.click(screen.getByRole("button", { name: "Save memory" }));
    await screen.findByText("Memory 11 saved.");
    const list = screen.getByRole("list", { name: "Saved memories" });
    expect(within(list).getAllByRole("listitem")).toHaveLength(1);
    expect(within(list).getByText(content)).toBeInTheDocument();
  },
);

test.each(["network", "validation"])("keeps the draft after a %s save failure without retrying", async (kind) => {
  const fetchMock = await emptyPanel();
  if (kind === "network") fetchMock.mockRejectedValueOnce(new TypeError("offline"));
  else fetchMock.mockResolvedValueOnce(jsonResponse({ detail: [{ msg: "too long" }] }, 422));
  enterMemory("Keep this draft");
  fireEvent.click(screen.getByRole("button", { name: "Save memory" }));
  const alert = await screen.findByRole("alert");
  expect(alert).toHaveTextContent(kind === "network" ? "Unable to save memory" : "1 to 2000 characters");
  expect(screen.getByLabelText("Memory content")).toHaveValue("Keep this draft");
  expect(screen.getByRole("button", { name: "Save memory" })).toBeEnabled();
  expect(fetchMock).toHaveBeenCalledTimes(2);
});

test("requires confirmation and can keep a memory without sending DELETE", async () => {
  const fetchMock = vi.fn().mockResolvedValueOnce(jsonResponse([memory]));
  vi.stubGlobal("fetch", fetchMock);
  render(<MemoryPanel agentId={7} />);
  fireEvent.click(await screen.findByRole("button", { name: "Delete memory 11" }));
  expect(fetchMock).toHaveBeenCalledTimes(1);
  fireEvent.click(screen.getByRole("button", { name: "Keep memory" }));
  expect(screen.getByText(memory.content)).toBeInTheDocument();
  expect(screen.queryByRole("button", { name: "Confirm delete" })).not.toBeInTheDocument();
  expect(fetchMock).toHaveBeenCalledTimes(1);
});

test("sends the Agent scope on deletion and locks repeated confirmations", async () => {
  const pending = deferredResponse();
  const fetchMock = vi.fn().mockResolvedValueOnce(jsonResponse([memory])).mockReturnValueOnce(pending.promise);
  vi.stubGlobal("fetch", fetchMock);
  render(<MemoryPanel agentId={7} />);
  fireEvent.click(await screen.findByRole("button", { name: "Delete memory 11" }));
  const confirm = screen.getByRole("button", { name: "Confirm delete" });
  fireEvent.click(confirm);
  fireEvent.click(confirm);
  expect(fetchMock).toHaveBeenCalledTimes(2);
  expect(fetchMock).toHaveBeenLastCalledWith("/memories/item/11?agent_id=7", { method: "DELETE" });
  expect(confirm).toBeDisabled();
  await act(async () => { pending.resolve(jsonResponse({ message: "Memory deleted successfully" })); });
  expect(screen.queryByText(memory.content)).not.toBeInTheDocument();
  expect(screen.getByText("No saved memories for this Agent.")).toBeInTheDocument();
});

test("keeps the record when DELETE fails", async () => {
  const fetchMock = vi.fn().mockResolvedValueOnce(jsonResponse([memory]))
    .mockResolvedValueOnce(jsonResponse({ detail: "Memory not found for this Agent" }, 404));
  vi.stubGlobal("fetch", fetchMock);
  render(<MemoryPanel agentId={7} />);
  fireEvent.click(await screen.findByRole("button", { name: "Delete memory 11" }));
  fireEvent.click(screen.getByRole("button", { name: "Confirm delete" }));
  expect(await screen.findByRole("alert")).toHaveTextContent("Memory not found for this Agent");
  expect(screen.getByText(memory.content)).toBeInTheDocument();
  expect(fetchMock).toHaveBeenCalledTimes(2);
});

test("can reload after a load failure, with writes disabled until recovery", async () => {
  const fetchMock = vi.fn().mockRejectedValueOnce(new TypeError("offline"))
    .mockResolvedValueOnce(jsonResponse([memory]));
  vi.stubGlobal("fetch", fetchMock);
  render(<MemoryPanel agentId={7} />);
  expect(await screen.findByRole("alert")).toHaveTextContent("Unable to load memories.");
  expect(screen.getByLabelText("Memory content")).toBeDisabled();
  fireEvent.click(screen.getByRole("button", { name: "Reload memories" }));
  await screen.findByText(memory.content);
  expect(screen.getByLabelText("Memory content")).toBeEnabled();
  expect(screen.queryByRole("alert")).not.toBeInTheDocument();
});

test("ignores a late list response after switching Agents", async () => {
  const old = deferredResponse();
  const current = { ...memory, id: 22, agent_id: 8, content: "Current Agent memory" };
  vi.stubGlobal("fetch", vi.fn().mockReturnValueOnce(old.promise).mockResolvedValueOnce(jsonResponse([current])));
  const { rerender } = render(<MemoryPanel agentId={7} />);
  rerender(<MemoryPanel agentId={8} />);
  await screen.findByText(current.content);
  await act(async () => { old.resolve(jsonResponse([memory])); });
  expect(screen.queryByText(memory.content)).not.toBeInTheDocument();
  expect(screen.getByText(current.content)).toBeInTheDocument();
});

test("ignores a late save after switching Agents and preserves the new draft", async () => {
  const pending = deferredResponse();
  const fetchMock = vi.fn().mockResolvedValueOnce(jsonResponse([])).mockReturnValueOnce(pending.promise)
    .mockResolvedValueOnce(jsonResponse([]));
  vi.stubGlobal("fetch", fetchMock);
  const { rerender } = render(<MemoryPanel agentId={7} />);
  await screen.findByText("No saved memories for this Agent.");
  enterMemory(memory.content);
  fireEvent.click(screen.getByRole("button", { name: "Save memory" }));
  rerender(<MemoryPanel agentId={8} />);
  await screen.findByText("No saved memories for this Agent.");
  enterMemory("Agent 8 draft");
  await act(async () => { pending.resolve(jsonResponse(memory)); });
  expect(screen.getByLabelText("Memory content")).toHaveValue("Agent 8 draft");
  expect(screen.queryByText(memory.content)).not.toBeInTheDocument();
  expect(screen.queryByText("Memory 11 saved.")).not.toBeInTheDocument();
});

test("ignores a late deletion after switching Agents", async () => {
  const pending = deferredResponse();
  const current = { ...memory, agent_id: 8, content: "Agent 8 memory" };
  vi.stubGlobal("fetch", vi.fn().mockResolvedValueOnce(jsonResponse([memory]))
    .mockReturnValueOnce(pending.promise).mockResolvedValueOnce(jsonResponse([current])));
  const { rerender } = render(<MemoryPanel agentId={7} />);
  fireEvent.click(await screen.findByRole("button", { name: "Delete memory 11" }));
  fireEvent.click(screen.getByRole("button", { name: "Confirm delete" }));
  rerender(<MemoryPanel agentId={8} />);
  await screen.findByText(current.content);
  await act(async () => { pending.resolve(jsonResponse({ message: "Memory deleted successfully" })); });
  expect(screen.getByText(current.content)).toBeInTheDocument();
  expect(screen.queryByText("Memory 11 deleted.")).not.toBeInTheDocument();
});

test("rejects a list containing another Agent's memory", async () => {
  vi.stubGlobal("fetch", vi.fn().mockResolvedValueOnce(jsonResponse([{ ...memory, agent_id: 8 }])));
  render(<MemoryPanel agentId={7} />);
  expect(await screen.findByRole("alert")).toHaveTextContent("invalid memory data for this Agent");
  expect(screen.queryByText(memory.content)).not.toBeInTheDocument();
  expect(screen.getByLabelText("Memory content")).toBeDisabled();
});

test("rejects a save response from another Agent without losing the draft", async () => {
  const fetchMock = await emptyPanel();
  fetchMock.mockResolvedValueOnce(jsonResponse({ ...memory, agent_id: 8 }));
  enterMemory("Agent 7 draft");
  fireEvent.click(screen.getByRole("button", { name: "Save memory" }));
  await screen.findByRole("alert");
  expect(screen.getByLabelText("Memory content")).toHaveValue("Agent 7 draft");
  expect(screen.queryByText(memory.content)).not.toBeInTheDocument();
  await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(2));
});

test("defers a chat-triggered refresh until a manual save has finished", async () => {
  const pending = deferredResponse();
  const extracted = { ...memory, id: 12, content: "User likes Python." };
  const fetchMock = vi.fn().mockResolvedValueOnce(jsonResponse([])).mockReturnValueOnce(pending.promise)
    .mockResolvedValueOnce(jsonResponse([memory, extracted]));
  vi.stubGlobal("fetch", fetchMock);
  const { rerender } = render(<MemoryPanel agentId={7} refreshKey={0} />);
  await screen.findByText("No saved memories for this Agent.");
  enterMemory(memory.content);
  fireEvent.click(screen.getByRole("button", { name: "Save memory" }));
  rerender(<MemoryPanel agentId={7} refreshKey={1} />);
  expect(fetchMock).toHaveBeenCalledTimes(2);
  await act(async () => { pending.resolve(jsonResponse(memory)); });
  await screen.findByText(extracted.content);
  expect(screen.getByText(memory.content)).toBeInTheDocument();
  expect(fetchMock).toHaveBeenCalledTimes(3);
});
