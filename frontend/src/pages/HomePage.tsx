import { useState } from "react";

import { ExecutionHistory } from "../components/ExecutionHistory";
import { ConversationPanel } from "../components/ConversationPanel";
import { ExecutionInspector } from "../components/ExecutionInspector";
import { MemoryPanel } from "../components/MemoryPanel";
import { UserMemoryPanel } from "../components/UserMemoryPanel";
import { TaskSubmission } from "../components/TaskSubmission";
import { RuntimeConfigurationPanel } from "../components/RuntimeConfigurationPanel";
import type { Execution } from "../types/executions";

export function HomePage() {
  const [selectedAgentId, setSelectedAgentId] = useState<number | null>(null);
  const [memoryRefreshKey, setMemoryRefreshKey] = useState(0);
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
      <header id="workbench-top" className="workbench-page-header">
        <div>
          <p className="workbench-eyebrow">AGENT WORKSPACE</p>
          <h1>AgentDesk</h1>
          <p>先选择 Agent，再开始聊天。使用导航直接查看配置、记忆和执行详情。</p>
        </div>
        <span className="workbench-local-label">本地工作台</span>
      </header>

      <div className="workbench-two-columns">
        <div id="workbench-task" className="workbench-region" tabIndex={-1}>
          <TaskSubmission onSubmitted={handleTaskSubmitted} onAgentSelected={setSelectedAgentId} />
        </div>
        <div id="workbench-runtime" className="workbench-region" tabIndex={-1}>
          <RuntimeConfigurationPanel agentId={selectedAgentId} />
        </div>
      </div>

      <div id="workbench-chat" className="workbench-region" tabIndex={-1}>
        <ConversationPanel agentId={selectedAgentId} onActivity={(agentId, executionId) => {
          if (agentId !== selectedAgentId) return;
          handleTaskSubmitted(executionId);
          setMemoryRefreshKey((key) => key + 1);
        }} />
      </div>

      <div className="workbench-two-columns">
        <div id="workbench-memory" className="workbench-region" tabIndex={-1}>
          <MemoryPanel agentId={selectedAgentId} refreshKey={memoryRefreshKey} />
        </div>
        <div id="workbench-shared-memory" className="workbench-region" tabIndex={-1}>
          <UserMemoryPanel agentId={selectedAgentId} />
        </div>
      </div>

      <div className="workbench-execution-columns">
        <div id="workbench-history" className="workbench-region" tabIndex={-1}>
          <ExecutionHistory
            onSelectExecution={setSelectedExecutionId}
            updatedExecution={updatedExecution}
            refreshKey={historyRefreshKey}
          />
        </div>
        <div id="workbench-inspector" className="workbench-region" tabIndex={-1}>
          <ExecutionInspector
            selectedExecutionId={selectedExecutionId}
            onExecutionUpdated={setUpdatedExecution}
          />
        </div>
      </div>
    </>
  );
}
