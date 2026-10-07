import type { Agent, AgentChatResponse } from "../types/agents";
import { requestJson } from "./executions";

export function getAgents(): Promise<Agent[]> {
  return requestJson<Agent[]>("/agents");
}

export function submitAgentTask(
  agentId: number,
  message: string,
): Promise<AgentChatResponse> {
  return requestJson<AgentChatResponse>(`/agents/${agentId}/chat`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ message }),
  });
}
