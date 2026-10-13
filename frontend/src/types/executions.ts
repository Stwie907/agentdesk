export type Execution = {
  id: number;
  agent_id: number;
  input: string;
  output: string | null;
  status: string;

  retry_count: number;
  failure_type: string | null;
  failure_message: string | null;
  replay_of_execution_id: number | null;

  created_at: string;
};

export type ExecutionTraceEvent = {
  id: number;
  execution_id: number;

  event: string;

  step_index: number | null;
  tool: string | null;
  error: string | null;

  message: string;
  created_at: string;
};

export type ExecutionSnapshot = {
  id: number;
  execution_id: number;
  snapshot_version: number;

  input_snapshot: string;
  plan_snapshot: string | null;
  output_snapshot: string | null;

  created_at: string;
};

export type ExecutionInspection = {
  execution: Execution;
  trace: ExecutionTraceEvent[];
  snapshot: ExecutionSnapshot | null;
  replays: Execution[];
};
