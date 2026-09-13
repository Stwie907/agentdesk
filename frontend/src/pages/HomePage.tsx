import { useState } from "react";

import { ExecutionHistory } from "../components/ExecutionHistory";
import { ExecutionInspector } from "../components/ExecutionInspector";

export function HomePage() {
  const [selectedExecutionId, setSelectedExecutionId] = useState<number | null>(
    null,
  );

  return (
    <>
      <h1>AgentDesk</h1>

      <ExecutionHistory onSelectExecution={setSelectedExecutionId} />

      <ExecutionInspector selectedExecutionId={selectedExecutionId} />
    </>
  );
}
