import { useState } from "react";

import { ExecutionHistory } from "../components/ExecutionHistory";
import { ExecutionInspector } from "../components/ExecutionInspector";
import type { Execution } from "../types/executions";

export function HomePage() {
  const [selectedExecutionId, setSelectedExecutionId] = useState<
    number | null
  >(null);

  const [updatedExecution, setUpdatedExecution] = useState<
    Execution | null
  >(null);

  return (
    <>
      <h1>AgentDesk</h1>

      <ExecutionHistory
        onSelectExecution={setSelectedExecutionId}
        updatedExecution={updatedExecution}
      />

      <ExecutionInspector
        selectedExecutionId={selectedExecutionId}
        onExecutionUpdated={setUpdatedExecution}
      />
    </>
  );
}
