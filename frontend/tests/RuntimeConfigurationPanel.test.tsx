import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, expect, test, vi } from "vitest";

import { RuntimeConfigurationPanel } from "../src/components/RuntimeConfigurationPanel";
import { HomePage } from "../src/pages/HomePage";
import { runtimeConfiguration, semanticRuntimeConfiguration } from "./runtimeConfigurationFixtures";
import { deferredResponse, jsonResponse, testAgent } from "./taskFixtures";
import { mockDraftRequests, mainConversation } from "./draftPersistenceFixtures";

afterEach(() => { vi.unstubAllGlobals(); });

function show() { fireEvent.click(screen.getByRole("button", { name: "Show runtime configuration" })); }
function valueFor(label: string) { return screen.getByText(label, { selector: "dt" }).nextElementSibling; }

test("starts collapsed and does not add a configuration request to startup", () => {
  const fetchMock = vi.fn(); vi.stubGlobal("fetch", fetchMock);
  render(<RuntimeConfigurationPanel agentId={null} />);
  expect(screen.getByRole("button", { name: "Show runtime configuration" })).toHaveAttribute("aria-expanded", "false");
  expect(fetchMock).not.toHaveBeenCalled();
});

test("opens global settings and makes model availability distinct from configuration", async () => {
  const fetchMock = vi.fn().mockResolvedValue(jsonResponse(runtimeConfiguration(null)));
  vi.stubGlobal("fetch", fetchMock);
  render(<RuntimeConfigurationPanel agentId={null} />); show();
  expect(await screen.findByText("Ollama")).toBeInTheDocument();
  expect(valueFor("Selected Agent")).toHaveTextContent("No Agent selected");
  expect(valueFor("Active embedding model")).toHaveTextContent("Not used in keyword mode");
  expect(valueFor("Vector cache setting")).toHaveTextContent("Enabled");
  expect(valueFor("Vector cache activity")).toHaveTextContent("Inactive");
  expect(screen.getByText("Current settings only. Model availability has not been checked.")).toBeInTheDocument();
  expect(fetchMock.mock.calls[0][0]).toBe("/runtime/config");
});

test("shows the selected Agent's chat model separately from the configured planner", async () => {
  const value = semanticRuntimeConfiguration();
  value.selected_agent!.chat_model = "agent-local-model";
  value.configured_planner_model = "planning-local-model";
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue(jsonResponse(value)));
  render(<RuntimeConfigurationPanel agentId={7} />); show();
  expect(await screen.findByText("agent-local-model")).toBeInTheDocument();
  expect(valueFor("Configured planner model")).toHaveTextContent("planning-local-model");
  expect(valueFor("Memory retrieval mode")).toHaveTextContent("Semantic");
  expect(valueFor("Vector cache activity")).toHaveTextContent("Active for semantic retrieval");
  expect(valueFor("Database backend")).toHaveTextContent("SQLite");
});

test("identifies simulated Mock and its fixture embeddings", async () => {
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue(jsonResponse(semanticRuntimeConfiguration(7, "mock"))));
  render(<RuntimeConfigurationPanel agentId={7} />); show();
  expect(await screen.findByText("Mock (simulated)")).toBeInTheDocument();
  expect(valueFor("Active embedding model")).toHaveTextContent("mock-fixtures-v1");
});

test("prevents duplicate refreshes while loading and allows a current settings refresh", async () => {
  const pending = deferredResponse();
  const fetchMock = vi.fn().mockReturnValueOnce(pending.promise).mockResolvedValueOnce(jsonResponse(semanticRuntimeConfiguration()));
  vi.stubGlobal("fetch", fetchMock);
  render(<RuntimeConfigurationPanel agentId={7} />); show();
  const refresh = screen.getByRole("button", { name: "Refresh runtime configuration" });
  expect(refresh).toBeDisabled(); fireEvent.click(refresh); expect(fetchMock).toHaveBeenCalledOnce();
  pending.resolve(jsonResponse(runtimeConfiguration()));
  await screen.findByText("Keyword");
  fireEvent.click(refresh);
  expect(await screen.findByText("Semantic")).toBeInTheDocument();
  expect(fetchMock).toHaveBeenCalledTimes(2);
});

test("retains an explicit configuration error and can retry successfully", async () => {
  vi.stubGlobal("fetch", vi.fn().mockResolvedValueOnce(jsonResponse({ detail: "Runtime configuration is invalid." }, 503))
    .mockResolvedValueOnce(jsonResponse(runtimeConfiguration())));
  render(<RuntimeConfigurationPanel agentId={7} />); show();
  expect(await screen.findByRole("alert")).toHaveTextContent("Runtime configuration is invalid.");
  fireEvent.click(screen.getByRole("button", { name: "Refresh runtime configuration" }));
  expect(await screen.findByText("Ollama")).toBeInTheDocument();
  expect(screen.queryByRole("alert")).not.toBeInTheDocument();
});

test("network failures remain local to the panel", async () => {
  vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new TypeError("Offline")));
  render(<RuntimeConfigurationPanel agentId={7} />); show();
  expect(await screen.findByRole("alert")).toHaveTextContent("Unable to read runtime configuration.");
  expect(screen.getByRole("button", { name: "Hide runtime configuration" })).toBeEnabled();
});

test("a foreign or deleted Agent response does not display stale model values", async () => {
  vi.stubGlobal("fetch", vi.fn().mockResolvedValueOnce(jsonResponse(runtimeConfiguration(8)))
    .mockResolvedValueOnce(jsonResponse({ detail: "Agent not found" }, 404)));
  render(<RuntimeConfigurationPanel agentId={7} />); show();
  expect(await screen.findByRole("alert")).toHaveTextContent("another Agent");
  expect(screen.queryByText("Ollama")).not.toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Refresh runtime configuration" }));
  expect(await screen.findByRole("alert")).toHaveTextContent("Agent not found");
});

test.each(["success", "error"])("hiding aborts a pending read and ignores late %s on reopening", async (result) => {
  const old = deferredResponse();
  const fetchMock = vi.fn().mockReturnValueOnce(old.promise).mockResolvedValueOnce(jsonResponse(runtimeConfiguration(7)));
  vi.stubGlobal("fetch", fetchMock);
  render(<RuntimeConfigurationPanel agentId={7} />); show();
  const oldSignal = fetchMock.mock.calls[0][1].signal as AbortSignal;
  fireEvent.click(screen.getByRole("button", { name: "Hide runtime configuration" }));
  expect(oldSignal.aborted).toBe(true);
  show(); await screen.findByText("Ollama");
  await act(async () => { old.resolve(result === "success" ? jsonResponse(semanticRuntimeConfiguration(7, "mock")) : jsonResponse({ detail: "Old error" }, 503)); });
  expect(fetchMock).toHaveBeenCalledTimes(2);
  expect(screen.queryByText("Mock (simulated)")).not.toBeInTheDocument();
  expect(screen.queryByRole("alert")).not.toBeInTheDocument();
});

test.each(["success", "error"])("Agent changes keep the panel open and reject a late old-Agent %s", async (result) => {
  const old = deferredResponse(), fresh = runtimeConfiguration(8);
  fresh.selected_agent!.chat_model = "agent-eight-model";
  const fetchMock = vi.fn().mockReturnValueOnce(old.promise).mockResolvedValueOnce(jsonResponse(fresh));
  vi.stubGlobal("fetch", fetchMock);
  const { rerender } = render(<RuntimeConfigurationPanel agentId={7} />); show();
  const signal = fetchMock.mock.calls[0][1].signal as AbortSignal;
  rerender(<RuntimeConfigurationPanel agentId={8} />);
  expect(await screen.findByText("agent-eight-model")).toBeInTheDocument();
  expect(signal.aborted).toBe(true);
  expect(fetchMock.mock.calls[1][0]).toBe("/runtime/config?agent_id=8");
  await act(async () => { old.resolve(result === "success" ? jsonResponse(runtimeConfiguration(7)) : jsonResponse({ detail: "Old Agent error" }, 404)); });
  expect(valueFor("Selected Agent")).toHaveTextContent("ID: 8");
  expect(valueFor("Selected Agent chat model")).toHaveTextContent("agent-eight-model");
  expect(screen.queryByRole("alert")).not.toBeInTheDocument();
});

test("unmounting aborts an outstanding settings read", () => {
  const pending = deferredResponse(), fetchMock = vi.fn().mockReturnValue(pending.promise);
  vi.stubGlobal("fetch", fetchMock);
  const { unmount } = render(<RuntimeConfigurationPanel agentId={7} />); show();
  const signal = fetchMock.mock.calls[0][1].signal as AbortSignal;
  unmount(); expect(signal.aborted).toBe(true);
  pending.resolve(jsonResponse(runtimeConfiguration(7)));
});

test("reading settings in the full workbench preserves unsent chat and title drafts", async () => {
  const { fetchMock: draftFetch } = mockDraftRequests();
  const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const path = new URL(String(input), "http://localhost").pathname;
    if (path === "/agents") return jsonResponse([testAgent]);
    if (path === "/agents/7") return jsonResponse(testAgent);
    if (path === "/projects/1") return jsonResponse({ id: 1, owner_id: 1 });
    if (path === "/runtime/config") return jsonResponse(runtimeConfiguration(7));
    if (path.startsWith("/conversations")) return draftFetch(input, init);
    return jsonResponse([]);
  });
  vi.stubGlobal("fetch", fetchMock);
  render(<HomePage />);
  await screen.findByRole("option", { name: "Calculator Agent (ID: 7)" });
  fireEvent.change(screen.getByLabelText("Agent", { exact: true }), { target: { value: "7" } });
  const conversation = await screen.findByLabelText("Conversation", { exact: true });
  await waitFor(() => expect(within(conversation).getAllByRole("option").length).toBeGreaterThan(1));
  fireEvent.change(conversation, { target: { value: String(mainConversation.id) } });
  const message = await screen.findByLabelText("Chat message"), title = screen.getByLabelText("Conversation title", { exact: true });
  await waitFor(() => expect(message).toBeEnabled());
  fireEvent.change(message, { target: { value: "  Unsent settings-check draft  " } });
  fireEvent.change(title, { target: { value: "Unfinished title draft" } });
  show(); await screen.findByText("Ollama");
  fireEvent.click(screen.getByRole("button", { name: "Refresh runtime configuration" }));
  await waitFor(() => expect(screen.getByRole("button", { name: "Refresh runtime configuration" })).toBeEnabled());
  expect(message).toHaveValue("  Unsent settings-check draft  ");
  expect(title).toHaveValue("Unfinished title draft");
  expect(fetchMock.mock.calls.every(([, init]) => init?.method === undefined || init.method === "GET")).toBe(true);
});
