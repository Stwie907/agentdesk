import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, expect, test, vi } from "vitest";

import { OllamaDiagnosticsPanel } from "../src/components/OllamaDiagnosticsPanel";
import { RuntimeConfigurationPanel } from "../src/components/RuntimeConfigurationPanel";
import { HomePage } from "../src/pages/HomePage";
import { installedModels, failedModels } from "./ollamaDiagnosticsFixtures";
import { runtimeConfiguration } from "./runtimeConfigurationFixtures";
import { deferredResponse, jsonResponse, testAgent } from "./taskFixtures";
import { mockDraftRequests, mainConversation } from "./draftPersistenceFixtures";

afterEach(() => vi.unstubAllGlobals());
function check() { fireEvent.click(screen.getByRole("button", { name: "检查本地 Ollama 模型" })); }

test("does not read model metadata until the user clicks", () => {
  const fetchMock = vi.fn(); vi.stubGlobal("fetch", fetchMock);
  render(<OllamaDiagnosticsPanel agentId={7} />);
  expect(screen.getByRole("button", { name: "检查本地 Ollama 模型" })).toBeEnabled();
  expect(fetchMock).not.toHaveBeenCalled();
});

test("shows installation per role and disables duplicate clicks during a read", async () => {
  const pending = deferredResponse(), fetchMock = vi.fn().mockReturnValue(pending.promise); vi.stubGlobal("fetch", fetchMock);
  render(<OllamaDiagnosticsPanel agentId={7} />); check(); check();
  expect(screen.getByRole("button", { name: "检查本地 Ollama 模型" })).toBeDisabled();
  expect(fetchMock).toHaveBeenCalledOnce();
  pending.resolve(jsonResponse(installedModels()));
  expect(await screen.findByText(/已连接并读取本地模型列表/)).toHaveTextContent("已连接并读取本地模型列表");
  expect(screen.getByText("向量模型").nextElementSibling).toHaveTextContent("embeddinggemma — 已安装（匹配 embeddinggemma:latest）");
});

test.each(["unreachable", "timeout", "http_error", "invalid_response"] as const)("renders %s separately from missing installation", async (status) => {
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue(jsonResponse(failedModels(status))));
  render(<OllamaDiagnosticsPanel agentId={7} />); check();
  await screen.findByRole("alert");
  expect(screen.getByText("聊天模型").nextElementSibling).toHaveTextContent("尚未确认");
  expect(screen.queryByText(/未安装/)).not.toBeInTheDocument();
});

test("can retry after an HTTP error and reports an actually missing model", async () => {
  const value = installedModels(); value.models.chat.status = "missing"; value.models.chat.installed_name = null;
  vi.stubGlobal("fetch", vi.fn().mockResolvedValueOnce(jsonResponse({ detail: "Runtime settings invalid." }, 503)).mockResolvedValueOnce(jsonResponse(value)));
  render(<OllamaDiagnosticsPanel agentId={7} />); check();
  expect(await screen.findByRole("alert")).toHaveTextContent("Runtime settings invalid.");
  check(); await screen.findByText(/已连接并读取本地模型列表/);
  expect(screen.getByText("聊天模型").nextElementSibling).toHaveTextContent("未安装");
});

test("Agent change clears the previous result and waits for another explicit click", async () => {
  const fetchMock = vi.fn().mockResolvedValueOnce(jsonResponse(installedModels())).mockResolvedValueOnce(jsonResponse(installedModels(8)));
  vi.stubGlobal("fetch", fetchMock);
  const { rerender } = render(<OllamaDiagnosticsPanel agentId={7} />); check(); await screen.findByText(/已连接并读取本地模型列表/);
  rerender(<OllamaDiagnosticsPanel agentId={8} />);
  expect(screen.queryByRole("status")).not.toBeInTheDocument(); expect(fetchMock).toHaveBeenCalledOnce();
  check(); await screen.findByText(/已连接并读取本地模型列表/);
  expect(fetchMock.mock.calls[1][0]).toBe("/runtime/ollama?agent_id=8");
});

test("late results from another Agent cannot replace the current result", async () => {
  const old = deferredResponse(), current = deferredResponse();
  const fetchMock = vi.fn().mockReturnValueOnce(old.promise).mockReturnValueOnce(current.promise); vi.stubGlobal("fetch", fetchMock);
  const { rerender } = render(<OllamaDiagnosticsPanel agentId={7} />); check();
  const signal = fetchMock.mock.calls[0][1].signal as AbortSignal;
  rerender(<OllamaDiagnosticsPanel agentId={8} />); expect(signal.aborted).toBe(true); check();
  current.resolve(jsonResponse(installedModels(8))); await screen.findByText(/已连接并读取本地模型列表/);
  await act(async () => old.resolve(jsonResponse(failedModels("timeout"))));
  expect(screen.getByText("检查的 Agent").nextElementSibling).toHaveTextContent("ID: 8");
  expect(screen.queryByRole("alert")).not.toBeInTheDocument();
});

test("unmount cancels a pending metadata read", () => {
  const pending = deferredResponse(), fetchMock = vi.fn().mockReturnValue(pending.promise); vi.stubGlobal("fetch", fetchMock);
  const { unmount } = render(<OllamaDiagnosticsPanel agentId={7} />); check();
  const signal = fetchMock.mock.calls[0][1].signal as AbortSignal; unmount(); expect(signal.aborted).toBe(true);
});

test("hiding the runtime panel cancels metadata and reopening only reads configuration", async () => {
  const pending = deferredResponse();
  const fetchMock = vi.fn((url: string, _init?: RequestInit) => url.startsWith("/runtime/config") ? Promise.resolve(jsonResponse(runtimeConfiguration())) : pending.promise);
  vi.stubGlobal("fetch", fetchMock); render(<RuntimeConfigurationPanel agentId={7} />);
  fireEvent.click(screen.getByRole("button", { name: "Show runtime configuration" }));
  await screen.findByRole("button", { name: "检查本地 Ollama 模型" }); expect(fetchMock).toHaveBeenCalledOnce(); check();
  const signal = fetchMock.mock.calls[1][1]!.signal as AbortSignal;
  fireEvent.click(screen.getByRole("button", { name: "Hide runtime configuration" })); expect(signal.aborted).toBe(true);
  fireEvent.click(screen.getByRole("button", { name: "Show runtime configuration" }));
  await screen.findByRole("button", { name: "检查本地 Ollama 模型" });
  expect(fetchMock).toHaveBeenCalledTimes(3);
});

test("metadata reads retain conversation selection and both unsaved drafts", async () => {
  const { fetchMock: drafts } = mockDraftRequests();
  const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const path = new URL(String(input), "http://localhost").pathname;
    if (path === "/agents") return jsonResponse([testAgent]);
    if (path === "/agents/7") return jsonResponse(testAgent);
    if (path === "/projects/1") return jsonResponse({ id: 1, owner_id: 1 });
    if (path === "/runtime/config") return jsonResponse(runtimeConfiguration());
    if (path === "/runtime/ollama") return jsonResponse(installedModels());
    if (path.startsWith("/conversations")) return drafts(input, init);
    return jsonResponse([]);
  });
  vi.stubGlobal("fetch", fetchMock); render(<HomePage />);
  await screen.findByRole("option", { name: "Calculator Agent (ID: 7)" });
  fireEvent.change(screen.getByLabelText("Agent", { exact: true }), { target: { value: "7" } });
  const conversation = await screen.findByLabelText("Conversation", { exact: true });
  await waitFor(() => expect(within(conversation).getAllByRole("option").length).toBeGreaterThan(1));
  fireEvent.change(conversation, { target: { value: String(mainConversation.id) } });
  const message = await screen.findByLabelText("Chat message"), title = screen.getByLabelText("Conversation title", { exact: true });
  await waitFor(() => expect(message).toBeEnabled());
  fireEvent.change(message, { target: { value: "Unsent model-check draft" } });
  fireEvent.change(title, { target: { value: "Unfinished model-check title" } });
  fireEvent.click(screen.getByRole("button", { name: "Show runtime configuration" }));
  await screen.findByRole("button", { name: "检查本地 Ollama 模型" }); check();
  await screen.findByText(/已连接并读取本地模型列表/);
  expect(conversation).toHaveValue(String(mainConversation.id));
  expect(message).toHaveValue("Unsent model-check draft"); expect(title).toHaveValue("Unfinished model-check title");
  expect(fetchMock.mock.calls.every(([, init]) => init?.method === undefined || init.method === "GET")).toBe(true);
});

test("configuration refresh cancels an old model check and requires a fresh explicit check", async () => {
  const pending = deferredResponse();
  const fetchMock = vi.fn((url: string, _init?: RequestInit) => url.startsWith("/runtime/config") ? Promise.resolve(jsonResponse(runtimeConfiguration())) : pending.promise);
  vi.stubGlobal("fetch", fetchMock); render(<RuntimeConfigurationPanel agentId={7} />);
  fireEvent.click(screen.getByRole("button", { name: "Show runtime configuration" }));
  await screen.findByRole("button", { name: "检查本地 Ollama 模型" }); check();
  const signal = fetchMock.mock.calls[1][1]!.signal as AbortSignal;
  fireEvent.click(screen.getByRole("button", { name: "Refresh runtime configuration" }));
  await waitFor(() => expect(signal.aborted).toBe(true));
  await screen.findByRole("button", { name: "检查本地 Ollama 模型" });
  await act(async () => pending.resolve(jsonResponse(installedModels())));
  expect(screen.queryByText(/已连接并读取本地模型列表/)).not.toBeInTheDocument();
  expect(fetchMock).toHaveBeenCalledTimes(3);
});
