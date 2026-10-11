import { vi } from "vitest";
import type { MessageRoleFilter } from "../src/api/messageSearch";
import { agentSearchData, agentSearchResponse, siblingMarkdown, siblingMessage, siblingTitle } from "./agentMessageSearchFixtures";
import { conversationMessagePageResponse, conversationPageResponse } from "./conversationFixtures";
import { exportConversation, exportMessages } from "./conversationExportFixtures";
import { contextData, contextResponse } from "./messageContextFixtures";
import { contextExportResponse } from "./messageContextExportFixtures";
import { detailResponse } from "./messageSearchFixtures";
import { jsonResponse } from "./taskFixtures";

export const siblingConversation = { ...exportConversation, id: 92, title: siblingTitle };
export const navigationItem = agentSearchData("中文", null, 50).items.find((row) => row.id === 26)!;

export function mockNavigationRequests(includeSibling = false) {
  const respond = async (input: RequestInfo | URL): Promise<Response> => {
    const url = new URL(String(input), "http://localhost");
    const query = url.searchParams.get("query") ?? "";
    if (url.pathname === "/agents/7/messages/search") return agentSearchResponse(agentSearchData(query,
      url.searchParams.get("role") as MessageRoleFilter, Number(url.searchParams.get("limit")), Number(url.searchParams.get("offset"))));
    if (url.pathname === "/conversations/page") {
      const agentId = Number(url.searchParams.get("agent_id"));
      const filtered = agentId === 7 ? (includeSibling ? [exportConversation, siblingConversation] : [exportConversation])
        .filter((row) => row.title.includes(query)) : [];
      return conversationPageResponse(filtered, { agent_id: agentId, query,
        limit: Number(url.searchParams.get("limit")), offset: Number(url.searchParams.get("offset")) });
    }
    if (url.pathname === "/conversations/91") return jsonResponse(exportConversation);
    if (url.pathname === "/conversations/92") return jsonResponse(siblingConversation);
    if (url.pathname === "/conversations/91/messages/page") {
      const older = url.searchParams.get("before_id") !== null;
      return conversationMessagePageResponse(older ? exportMessages.slice(0, 5) : exportMessages.slice(-20), {
        before_id: older ? 6 : null, has_more: !older, next_before_id: older ? null : 6 });
    }
    if (url.pathname === "/conversations/92/messages/page") return conversationMessagePageResponse([siblingMessage]);
    const match = /^\/conversations\/(91|92)\/messages\/(\d+)(\/context(?:\/export)?)?$/.exec(url.pathname);
    if (match) {
      const conversationId = Number(match[1]), messageId = Number(match[2]);
      const messages = conversationId === 91 ? exportMessages : [siblingMessage];
      if (!match[3]) return detailResponse(messages.find((row) => row.id === messageId)!);
      const before = Number(url.searchParams.get("before") ?? 3), after = Number(url.searchParams.get("after") ?? 3);
      const context = { ...contextData(messageId, before, after, messages), conversation_id: conversationId };
      if (match[3] === "/context") return contextResponse(context);
      const format = url.searchParams.get("format") === "markdown" ? "markdown" : "json";
      return contextExportResponse(format, context, format === "markdown" && conversationId === 92 ? siblingMarkdown : undefined);
    }
    throw new Error(`Unexpected navigation request ${url}`);
  };
  const fetchMock = vi.fn((input: RequestInfo | URL, _init?: RequestInit) => respond(input));
  vi.stubGlobal("fetch", fetchMock);
  return { fetchMock, respond };
}
