import { StrictMode } from "react";
import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, expect, test, vi } from "vitest";
import { ConversationPanel } from "../src/components/ConversationPanel";
import { conversationDraftKey, draftPreferenceKey, readConversationDraft, writeConversationDraft, writeDraftPreference } from "../src/state/conversationDraftStorage";
import { mainConversation, secondConversation, otherAgentConversation, mockDraftRequests } from "./draftPersistenceFixtures";
import { deferredResponse, jsonResponse } from "./taskFixtures";

afterEach(() => { vi.restoreAllMocks(); vi.unstubAllGlobals(); });

const checkbox = () => screen.getByRole("checkbox", { name: "Keep this Agent's drafts on this browser" });
const chat = () => screen.getByLabelText("Chat message");
const rename = () => screen.getByLabelText("Conversation title");
function type(label: string, value: string) { fireEvent.change(screen.getByLabelText(label), { target: { value } }); }
function seed(message = "Stored draft", renameTitle = mainConversation.title) {
  writeDraftPreference(7, true);
  writeConversationDraft(7, 91, { message, renameTitle, baseTitle: mainConversation.title,
    conversationCreatedAt: mainConversation.created_at });
}
async function ready(id = 91) {
  await screen.findByRole("option", { name: new RegExp(`ID: ${id}\\)`) });
}
async function choose(id = 91) {
  type("Conversation", String(id));
  await waitFor(() => expect(chat()).toBeEnabled());
}
async function setup(select = true) {
  const requests = mockDraftRequests(), onActivity = vi.fn();
  const view = render(<ConversationPanel agentId={7} onActivity={onActivity} />);
  await ready(); if (select) await choose();
  return { ...requests, onActivity, ...view };
}

test("default saving is off and a fresh panel cannot restore session-only drafts", async () => {
  const view = await setup(); expect(checkbox()).not.toBeChecked();
  type("Chat message", "Session draft"); type("Conversation title", "Session rename");
  view.unmount(); render(<ConversationPanel agentId={7} onActivity={view.onActivity} />);
  await ready(); await choose();
  expect(chat()).toHaveValue(""); expect(rename()).toHaveValue(mainConversation.title);
  expect(window.localStorage.length).toBe(0);
  expect(view.fetchMock.mock.calls.every(([, init]) => !init?.method)).toBe(true);
});

test("restores separate exact drafts after reload without selecting or submitting a conversation automatically", async () => {
  const view = await setup(); fireEvent.click(checkbox());
  const text = "  Main draft\n中文 <script>literal</script>  ";
  type("Chat message", text); type("Conversation title", " Main rename ");
  type("New conversation title", "Creation draft"); type("Conversation title search", "Title search draft");
  await choose(92); type("Chat message", "Second draft"); type("Conversation title", "Second rename");
  view.unmount(); render(<ConversationPanel agentId={7} onActivity={view.onActivity} />); await ready();
  expect(checkbox()).toBeChecked(); expect(screen.getByLabelText("Conversation")).toHaveValue("");
  expect(screen.getByLabelText("New conversation title")).toHaveValue("");
  expect(screen.getByLabelText("Conversation title search")).toHaveValue("");
  await choose(); expect(chat()).toHaveValue(text); expect(rename()).toHaveValue(" Main rename ");
  expect(document.querySelector("script")).toBeNull();
  await choose(92); expect(chat()).toHaveValue("Second draft"); expect(rename()).toHaveValue("Second rename");
  expect(view.onActivity).not.toHaveBeenCalled();
  expect(view.fetchMock.mock.calls.every(([, init]) => !init?.method)).toBe(true);
});

test("enabling saving includes drafts already typed in each visited conversation", async () => {
  await setup(); type("Chat message", "First before enabling");
  await choose(92); type("Chat message", "Second before enabling"); fireEvent.click(checkbox());
  expect(readConversationDraft(mainConversation).value?.message).toBe("First before enabling");
  expect(readConversationDraft(secondConversation).value?.message).toBe("Second before enabling");
});

test("Agent changes restore only that Agent's opted-in drafts and preference", async () => {
  const view = await setup(); fireEvent.click(checkbox()); type("Chat message", "Agent seven draft");
  view.rerender(<ConversationPanel agentId={8} onActivity={view.onActivity} />); await ready(93);
  expect(checkbox()).not.toBeChecked(); await choose(93); expect(chat()).toHaveValue("");
  fireEvent.click(checkbox()); type("Chat message", "Agent eight draft");
  view.rerender(<ConversationPanel agentId={7} onActivity={view.onActivity} />); await ready(); await choose();
  expect(checkbox()).toBeChecked(); expect(chat()).toHaveValue("Agent seven draft");
  view.rerender(<ConversationPanel agentId={8} onActivity={view.onActivity} />); await ready(93); await choose(93);
  expect(chat()).toHaveValue("Agent eight draft"); expect(view.onActivity).not.toHaveBeenCalled();
});

test("turning saving off keeps old copies, stops new saves and does not restore them after reload", async () => {
  const view = await setup(); fireEvent.click(checkbox()); type("Chat message", "Saved copy");
  fireEvent.click(checkbox()); type("Chat message", "Session-only change");
  expect(readConversationDraft(mainConversation).value?.message).toBe("Saved copy");
  view.unmount(); render(<ConversationPanel agentId={7} onActivity={view.onActivity} />); await ready(); await choose();
  expect(checkbox()).not.toBeChecked(); expect(chat()).toHaveValue("");
});

test("re-enabling saving keeps current edits ahead of older saved copies", async () => {
  await setup(); fireEvent.click(checkbox()); type("Chat message", "Old saved copy");
  fireEvent.click(checkbox()); type("Chat message", "Latest current text"); fireEvent.click(checkbox());
  expect(chat()).toHaveValue("Latest current text");
  expect(readConversationDraft(mainConversation).value?.message).toBe("Latest current text");
});

test("clearing requires confirmation, disables saving and retains current text and other Agents", async () => {
  seed("Main saved text", "Main rename");
  writeDraftPreference(8, true); writeConversationDraft(8, 93, { message: "Agent eight text", renameTitle: otherAgentConversation.title,
    baseTitle: otherAgentConversation.title, conversationCreatedAt: otherAgentConversation.created_at });
  window.localStorage.setItem("unrelated", "Keep me");
  const view = await setup();
  fireEvent.click(screen.getByRole("button", { name: "Clear saved drafts for this Agent" }));
  fireEvent.click(screen.getByRole("button", { name: "Cancel clearing saved drafts" }));
  expect(checkbox()).toBeChecked(); expect(readConversationDraft(mainConversation).value?.message).toBe("Main saved text");
  fireEvent.click(screen.getByRole("button", { name: "Clear saved drafts for this Agent" }));
  fireEvent.click(screen.getByRole("button", { name: "Confirm clear saved drafts" }));
  expect(checkbox()).not.toBeChecked(); expect(chat()).toHaveValue("Main saved text"); expect(rename()).toHaveValue("Main rename");
  expect(readConversationDraft(mainConversation).value).toBeNull();
  expect(readConversationDraft(otherAgentConversation).value?.message).toBe("Agent eight text");
  expect(window.localStorage.getItem("unrelated")).toBe("Keep me");
  expect(view.fetchMock.mock.calls.every(([, init]) => !init?.method)).toBe(true);
  view.unmount(); render(<ConversationPanel agentId={7} onActivity={view.onActivity} />); await ready(); await choose();
  expect(checkbox()).not.toBeChecked(); expect(chat()).toHaveValue("");
});

test.each([true, false])("completed sends clear only the sent draft, including when saving is %s", async (enabled) => {
  const view = await setup(); fireEvent.click(checkbox()); type("Chat message", "Send this"); type("Conversation title", "Keep rename");
  await choose(92); type("Chat message", "Keep second chat"); await choose();
  if (!enabled) fireEvent.click(checkbox());
  fireEvent.click(screen.getByRole("button", { name: "Send message" }));
  await screen.findByText("Execution 101 returned with status: completed.");
  expect(chat()).toHaveValue(""); expect(rename()).toHaveValue("Keep rename");
  expect(readConversationDraft(mainConversation).value?.message).toBe("");
  expect(readConversationDraft(mainConversation).value?.renameTitle).toBe("Keep rename");
  expect(readConversationDraft(secondConversation).value?.message).toBe("Keep second chat");
  expect(view.onActivity).toHaveBeenCalledWith(7, 101);
  await waitFor(() => expect(chat()).toBeEnabled());
  view.unmount(); render(<ConversationPanel agentId={7} onActivity={view.onActivity} />); await ready();
  if (!enabled) fireEvent.click(checkbox());
  await choose(); expect(chat()).toHaveValue(""); expect(rename()).toHaveValue("Keep rename");
});

test.each(["failed", "running", "network", "validation"])("retains persisted text after %s sends without retrying", async (kind) => {
  const view = await setup(); fireEvent.click(checkbox()); type("Chat message", "Keep failed send");
  if (kind === "network") view.nextWrite(Promise.reject(new TypeError("offline")));
  else view.nextWrite(Promise.resolve(jsonResponse(kind === "validation" ? { detail: "invalid" } :
    { execution_id: 101, status: kind, response: "Reply" }, kind === "validation" ? 422 : 200)));
  fireEvent.click(screen.getByRole("button", { name: "Send message" }));
  if (kind === "network" || kind === "validation") await screen.findByRole("alert");
  else await screen.findByText(`Execution 101 returned with status: ${kind}. Inspect the execution before sending another message.`);
  expect(chat()).toHaveValue("Keep failed send");
  expect(readConversationDraft(mainConversation).value?.message).toBe("Keep failed send");
  expect(view.fetchMock.mock.calls.filter(([, init]) => init?.method === "POST")).toHaveLength(1);
});

test.each([true, false])("successful renames update saved title drafts and keep chat when saving is %s", async (enabled) => {
  const view = await setup(); fireEvent.click(checkbox()); type("Chat message", "Keep chat"); type("Conversation title", "  Saved rename  ");
  if (!enabled) fireEvent.click(checkbox());
  fireEvent.click(screen.getByRole("button", { name: "Rename conversation" }));
  await screen.findByText("Conversation 91 renamed.");
  expect(rename()).toHaveValue("Saved rename"); expect(chat()).toHaveValue("Keep chat");
  const saved = readConversationDraft(view.rows.get(91)!);
  expect(saved.value?.renameTitle).toBe("Saved rename"); expect(saved.value?.baseTitle).toBe("Saved rename");
  expect(saved.value?.message).toBe("Keep chat");
});

test("a failed rename keeps its persisted draft and original saved title", async () => {
  const view = await setup(); fireEvent.click(checkbox()); type("Conversation title", "Unsent rename");
  view.nextWrite(Promise.reject(new TypeError("offline")));
  fireEvent.click(screen.getByRole("button", { name: "Rename conversation" })); await screen.findByRole("alert");
  expect(rename()).toHaveValue("Unsent rename"); expect(readConversationDraft(mainConversation).value?.renameTitle).toBe("Unsent rename");
  expect(view.rows.get(91)?.title).toBe(mainConversation.title);
});

test.each([true, false])("successful deletion removes only its persisted draft when saving is %s", async (enabled) => {
  const view = await setup(); fireEvent.click(checkbox()); type("Chat message", "Delete main draft");
  await choose(92); type("Chat message", "Keep second draft"); await choose(); if (!enabled) fireEvent.click(checkbox());
  fireEvent.click(screen.getByRole("button", { name: "Delete conversation" }));
  fireEvent.click(screen.getByRole("button", { name: "Confirm delete" }));
  await screen.findByText("Conversation 91 deleted. Agent memories and execution history were kept.");
  expect(readConversationDraft(mainConversation).value).toBeNull();
  expect(readConversationDraft(secondConversation).value?.message).toBe("Keep second draft");
  expect(view.onActivity).not.toHaveBeenCalled();
});

test("failed deletion keeps the persisted copy", async () => {
  const view = await setup(); fireEvent.click(checkbox()); type("Chat message", "Keep delete failure");
  view.nextWrite(Promise.reject(new TypeError("offline")));
  fireEvent.click(screen.getByRole("button", { name: "Delete conversation" }));
  fireEvent.click(screen.getByRole("button", { name: "Confirm delete" })); await screen.findByRole("alert");
  expect(chat()).toHaveValue("Keep delete failure"); expect(readConversationDraft(mainConversation).value?.message).toBe("Keep delete failure");
});

test("a scoped missing selection on reload removes its persisted draft", async () => {
  const view = await setup(); fireEvent.click(checkbox()); type("Chat message", "Removed elsewhere"); view.rows.delete(91);
  fireEvent.click(screen.getByRole("button", { name: "Reload conversations" }));
  await screen.findByText("The selected conversation was removed. Choose another conversation.");
  expect(screen.getByLabelText("Conversation")).toHaveValue(""); expect(readConversationDraft(mainConversation).value).toBeNull();
});

test("a reused conversation ID cannot restore an old creation's draft", async () => {
  seed(); const view = mockDraftRequests(); view.rows.set(91, { ...mainConversation, created_at: "2026-10-12T00:00:00" });
  render(<ConversationPanel agentId={7} onActivity={vi.fn()} />); await ready(); await choose();
  expect(chat()).toHaveValue(""); expect(await screen.findByRole("alert")).toHaveTextContent("could not be restored");
  expect(view.fetchMock.mock.calls.every(([, init]) => !init?.method)).toBe(true);
});

test.each([false, true])("a refreshed saved title preserves a dirty rename only when it was edited: %s", async (edited) => {
  seed("Keep chat", edited ? "My pending rename" : mainConversation.title);
  const view = mockDraftRequests(); view.rows.set(91, { ...mainConversation, title: "Fresh server title" });
  render(<ConversationPanel agentId={7} onActivity={vi.fn()} />); await ready(); await choose();
  expect(rename()).toHaveValue(edited ? "My pending rename" : "Fresh server title"); expect(chat()).toHaveValue("Keep chat");
});

test("a corrupt browser draft is ignored without blocking ordinary editing", async () => {
  writeDraftPreference(7, true); window.localStorage.setItem(conversationDraftKey(7, 91), "{"); await setup();
  expect(chat()).toHaveValue(""); expect(await screen.findByRole("alert")).toHaveTextContent("could not be restored");
  type("Chat message", "New valid draft"); expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  expect(readConversationDraft(mainConversation).value?.message).toBe("New valid draft");
});

test("a quota error retains current text and previous disk data, then an explicit edit recovers", async () => {
  seed("Previous saved text"); await setup();
  const failed = vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => { throw new DOMException("full", "QuotaExceededError"); });
  type("Chat message", "Latest page text"); expect(chat()).toHaveValue("Latest page text");
  expect(await screen.findByRole("alert")).toHaveTextContent("reload may restore an older copy");
  expect(readConversationDraft(mainConversation).value?.message).toBe("Previous saved text");
  failed.mockRestore(); type("Chat message", "Saved after recovery");
  expect(readConversationDraft(mainConversation).value?.message).toBe("Saved after recovery");
  expect(screen.queryByRole("alert")).not.toBeInTheDocument();
});

test("a failed enable stays off and retains the current page draft", async () => {
  await setup(); type("Chat message", "Keep current page");
  vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => { throw new DOMException("blocked", "SecurityError"); });
  fireEvent.click(checkbox()); expect(checkbox()).not.toBeChecked(); expect(chat()).toHaveValue("Keep current page");
  expect(await screen.findByRole("alert")).toHaveTextContent("remain in this page");
});

test("blocked browser storage leaves scoped chat usable with saving off", async () => {
  vi.spyOn(window, "localStorage", "get").mockImplementation(() => { throw new DOMException("blocked", "SecurityError"); });
  await setup(); expect(checkbox()).not.toBeChecked(); type("Chat message", "Session remains usable");
  expect(chat()).toHaveValue("Session remains usable"); expect(await screen.findByRole("alert")).toHaveTextContent("remain in this page");
});

test("failed clearing reports incomplete removal and keeps page drafts", async () => {
  seed(); await setup();
  vi.spyOn(Storage.prototype, "removeItem").mockImplementation(() => { throw new DOMException("blocked", "SecurityError"); });
  fireEvent.click(screen.getByRole("button", { name: "Clear saved drafts for this Agent" }));
  fireEvent.click(screen.getByRole("button", { name: "Confirm clear saved drafts" }));
  expect(checkbox()).not.toBeChecked(); expect(chat()).toHaveValue("Stored draft");
  expect(screen.getByText(/could not be fully cleared/)).toBeInTheDocument();
  expect(readConversationDraft(mainConversation).value?.message).toBe("Stored draft");
});

test("Strict Mode reads saved drafts without passive writes or duplicate saves", async () => {
  seed("Strict draft"); mockDraftRequests();
  const write = vi.spyOn(Storage.prototype, "setItem"), remove = vi.spyOn(Storage.prototype, "removeItem");
  render(<StrictMode><ConversationPanel agentId={7} onActivity={vi.fn()} /></StrictMode>); await ready(); await choose();
  expect(chat()).toHaveValue("Strict draft"); expect(write).not.toHaveBeenCalled(); expect(remove).not.toHaveBeenCalled();
  type("Chat message", "Strict edit"); expect(write).toHaveBeenCalledTimes(1);
});

test("another tab turning saving off prevents further saves without replacing open drafts", async () => {
  seed("Original copy"); await setup();
  window.localStorage.setItem(draftPreferenceKey(7), "false");
  act(() => window.dispatchEvent(new StorageEvent("storage", { key: draftPreferenceKey(7), storageArea: window.localStorage, newValue: "false" })));
  expect(checkbox()).not.toBeChecked(); expect(chat()).toHaveValue("Original copy");
  type("Chat message", "Keep only in this page"); expect(readConversationDraft(mainConversation).value?.message).toBe("Original copy");
});

test("session-storage and other-Agent events cannot change the current Agent's setting", async () => {
  seed(); await setup(); window.localStorage.setItem(draftPreferenceKey(7), "false");
  act(() => window.dispatchEvent(new StorageEvent("storage", { key: draftPreferenceKey(7), storageArea: window.sessionStorage })));
  act(() => window.dispatchEvent(new StorageEvent("storage", { key: draftPreferenceKey(8), storageArea: window.localStorage })));
  expect(checkbox()).toBeChecked(); expect(chat()).toHaveValue("Stored draft");
});

test.each(["chat", "rename", "delete"])("late %s completion after an Agent change cannot mutate another panel's drafts", async (kind) => {
  seed("Agent seven source", "Agent seven rename"); const view = await setup(); const pending = deferredResponse();
  view.nextWrite(pending.promise);
  if (kind === "chat") fireEvent.click(screen.getByRole("button", { name: "Send message" }));
  else if (kind === "rename") fireEvent.click(screen.getByRole("button", { name: "Rename conversation" }));
  else {
    fireEvent.click(screen.getByRole("button", { name: "Delete conversation" }));
    fireEvent.click(screen.getByRole("button", { name: "Confirm delete" }));
  }
  expect(checkbox()).toBeDisabled();
  view.rerender(<ConversationPanel agentId={8} onActivity={view.onActivity} />); await ready(93); await choose(93);
  fireEvent.click(checkbox()); type("Chat message", "New Agent draft");
  await act(async () => pending.resolve(jsonResponse(kind === "chat" ? { execution_id: 101, status: "completed", response: "Reply" } :
    kind === "rename" ? { ...mainConversation, title: "Agent seven rename" } : { message: "deleted" })));
  expect(chat()).toHaveValue("New Agent draft"); expect(readConversationDraft(otherAgentConversation).value?.message).toBe("New Agent draft");
  expect(readConversationDraft(mainConversation).value?.message).toBe("Agent seven source"); expect(view.onActivity).not.toHaveBeenCalled();
});
