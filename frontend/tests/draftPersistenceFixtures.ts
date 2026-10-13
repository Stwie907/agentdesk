import { vi } from "vitest";
import type { Conversation } from "../src/types/conversations";
import { conversationMessagePageResponse, conversationPageResponse } from "./conversationFixtures";
import { exportConversation } from "./conversationExportFixtures";
import { jsonResponse } from "./taskFixtures";

export const mainConversation = { ...exportConversation };
export const secondConversation = { ...exportConversation, id: 92, title: "Second saved conversation" };
export const otherAgentConversation = { ...exportConversation, id: 93, agent_id: 8, title: "Agent eight conversation" };

export function mockDraftRequests() {
  const rows = new Map<number, Conversation>([mainConversation, secondConversation, otherAgentConversation]
    .map((row) => [row.id, { ...row }]));
  let next: Promise<Response> | null = null;
  const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit): Promise<Response> => {
    const url = new URL(String(input), "http://localhost"), agentId = Number(url.searchParams.get("agent_id"));
    if (url.pathname === "/conversations/page") {
      const query = url.searchParams.get("query") ?? "", offset = Number(url.searchParams.get("offset"));
      const limit = Number(url.searchParams.get("limit"));
      const matches = [...rows.values()].filter((row) => row.agent_id === agentId && row.title.includes(query));
      return conversationPageResponse(matches.slice(offset, offset + limit), { agent_id: agentId, query, limit, offset, total: matches.length });
    }
    const match = /^\/conversations\/(\d+)(?:\/(chat|messages\/page))?$/.exec(url.pathname);
    if (!match) throw new Error(`Unexpected draft request ${url}`);
    const row = rows.get(Number(match[1]));
    if (!row || row.agent_id !== agentId) return jsonResponse({ detail: "Conversation not found" }, 404);
    if (init?.method && next) { const response = next; next = null; return response; }
    if (init?.method === "PATCH") {
      const saved = { ...row, title: (JSON.parse(String(init.body)) as { title: string }).title };
      rows.set(row.id, saved); return jsonResponse(saved);
    }
    if (init?.method === "DELETE") { rows.delete(row.id); return jsonResponse({ message: "deleted" }); }
    if (match[2] === "chat") return jsonResponse({ execution_id: 101, status: "completed", response: "Saved reply" });
    if (match[2] === "messages/page") return conversationMessagePageResponse([], { conversation_id: row.id, agent_id: agentId });
    return jsonResponse(row);
  });
  vi.stubGlobal("fetch", fetchMock);
  return { rows, fetchMock, nextWrite: (response: Promise<Response>) => { next = response; } };
}
