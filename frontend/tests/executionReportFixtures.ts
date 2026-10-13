import type { ExecutionInspection } from "../src/types/executions";

export function reportFixture(id = 42): ExecutionInspection {
  return {
    execution: { id, agent_id: 1, status: "failed", input: "计算\n40+2", output: null,
      retry_count: 2, failure_type: "tool_error", failure_message: "工具失败\n再次检查",
      replay_of_execution_id: null, created_at: "2026-10-12T07:00:00" },
    trace: [{ id: 10, execution_id: id, event: "step_failed", step_index: 0,
      tool: "calculator", error: "bad expression", message: "原始内容\n```\n# Header\n<script>x</script>",
      created_at: "2026-10-12T07:00:01" }],
    snapshot: { id: 5, execution_id: id, snapshot_version: 1,
      input_snapshot: "计算\n40+2", plan_snapshot: '{"steps":[]}', output_snapshot: null,
      created_at: "2026-10-12T07:00:00" },
    replays: [{ id: id + 1, agent_id: 1, status: "completed", input: "计算\n40+2", output: "42",
      retry_count: 0, failure_type: null, failure_message: null, replay_of_execution_id: id,
      created_at: "2026-10-12T07:01:00" }],
  };
}
