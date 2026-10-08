import { useState } from "react";

import { ExecutionHistory } from "../components/ExecutionHistory";
import { ExecutionInspector } from "../components/ExecutionInspector";
import { MemoryPanel } from "../components/MemoryPanel";
import { TaskSubmission } from "../components/TaskSubmission";
import type { Execution } from "../types/executions";

export function HomePage() {
  const [selectedAgentId, setSelectedAgentId] = useState<number | null>(null);
  const [selectedExecutionId, setSelectedExecutionId] = useState<
    number | null
  >(null);

  const [updatedExecution, setUpdatedExecution] = useState<
    Execution | null
  >(null);

  const [historyRefreshKey, setHistoryRefreshKey] = useState(0);

  function handleTaskSubmitted(executionId: number) {
    setUpdatedExecution(null);
    setSelectedExecutionId(executionId);
    setHistoryRefreshKey((current) => current + 1);
  }

  return (
    <>
      <h1>AgentDesk</h1>

      <TaskSubmission onSubmitted={handleTaskSubmitted} onAgentSelected={setSelectedAgentId} />

      <MemoryPanel agentId={selectedAgentId} />

      <ExecutionHistory
        onSelectExecution={setSelectedExecutionId}
        updatedExecution={updatedExecution}
        refreshKey={historyRefreshKey}
      />

      <ExecutionInspector
        selectedExecutionId={selectedExecutionId}
        onExecutionUpdated={setUpdatedExecution}
      />
    </>
  );
}
