import { conversationPageResponse } from "./conversationFixtures";
import { fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, expect, test, vi } from "vitest";

import { HomePage } from "../src/pages/HomePage";
import { executionFixture, jsonResponse, testAgent } from "./taskFixtures";

afterEach(() => { vi.unstubAllGlobals(); });

test("conversation chat refreshes Agent memories, history, and execution inspection", async () => {
  let submitted = false;
  let memoryReads = 0;
  const execution = { ...executionFixture(101), input: "I like Python", output: "[MOCK] Fixed reply" };
  const memory = { id: 11, agent_id: 7, content: "User likes Python.", created_at: "2026-10-08T14:00:00" };
  vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = new URL(String(input), "http://localhost");
    if (url.pathname === "/agents") return jsonResponse([testAgent]);
    if (url.pathname === "/memories/7") {
      memoryReads += 1;
      return jsonResponse(submitted ? [memory] : []);
    }
    if (url.pathname === "/conversations/page") return conversationPageResponse([{ id: 91, agent_id: 7, title: "Memory demo", created_at: "2026-10-08T14:00:00" }]);
    if (url.pathname === "/conversations/91/chat" && init?.method === "POST") {
      expect(url.searchParams.get("agent_id")).toBe("7");
      submitted = true;
      return jsonResponse({ execution_id: 101, status: "completed", response: execution.output });
    }
    if (url.pathname === "/conversations/91/messages") return jsonResponse(submitted ? [
      { id: 1, conversation_id: 91, role: "user", content: execution.input, created_at: memory.created_at },
      { id: 2, conversation_id: 91, role: "assistant", content: execution.output, created_at: memory.created_at },
    ] : []);
    if (url.pathname === "/executions") return jsonResponse(submitted ? [execution] : []);
    if (url.pathname === "/executions/101") return jsonResponse(execution);
    if (url.pathname === "/executions/101/snapshot") return jsonResponse({}, 404);
    if (url.pathname.endsWith("/trace") || url.pathname.endsWith("/replays")) return jsonResponse([]);
    throw new Error(`Unexpected request: ${url}`);
  }));
  render(<HomePage />);
  await screen.findByRole("option", { name: "Calculator Agent (ID: 7)" });
  fireEvent.change(screen.getByLabelText("Agent"), { target: { value: "7" } });
  await screen.findByRole("option", { name: "Memory demo (ID: 91)" });
  fireEvent.change(screen.getByLabelText("Conversation"), { target: { value: "91" } });
  await screen.findByText("No messages in this conversation.");
  await screen.findByText("No saved memories for this Agent.");
  fireEvent.change(screen.getByLabelText("Chat message"), { target: { value: "I like Python" } });
  fireEvent.click(screen.getByRole("button", { name: "Send message" }));
  expect(await screen.findByText(memory.content)).toBeInTheDocument();
  expect(memoryReads).toBe(2);
  const summary = within((await screen.findByRole("heading", { name: "Execution Summary" })).closest("section")!);
  expect(summary.getByText("completed", { selector: "dd" })).toBeInTheDocument();
  expect(screen.getByLabelText("Execution ID")).toHaveValue("101");
  expect(await screen.findByRole("button", { name: "Execution 101" })).toBeInTheDocument();
});
