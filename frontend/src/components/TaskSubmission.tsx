import { type FormEvent, useEffect, useRef, useState } from "react";

import { getAgents, submitAgentTask } from "../api/agents";
import { ApiError } from "../api/executions";
import type { Agent, AgentChatResponse } from "../types/agents";

type TaskSubmissionProps = {
  onSubmitted: (executionId: number) => void;
  onAgentSelected?: (agentId: number | null) => void;
};

export function TaskSubmission({ onSubmitted, onAgentSelected }: TaskSubmissionProps) {
  const [agents, setAgents] = useState<Agent[]>([]);
  const [agentId, setAgentId] = useState("");
  const [message, setMessage] = useState("");
  const [loadingAgents, setLoadingAgents] = useState(true);
  const [agentError, setAgentError] = useState<string | null>(null);
  const [reloadKey, setReloadKey] = useState(0);
  const [submitting, setSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);
  const [result, setResult] = useState<AgentChatResponse | null>(null);
  const submissionInProgress = useRef(false);

  useEffect(() => {
    let cancelled = false;

    async function loadAgents() {
      setLoadingAgents(true);
      setAgentError(null);

      try {
        const availableAgents = await getAgents();

        if (!cancelled) {
          setAgents(availableAgents);
        }
      } catch (error) {
        if (!cancelled) {
          setAgentError(
            error instanceof ApiError
              ? error.message
              : "Unable to load Agents.",
          );
        }
      } finally {
        if (!cancelled) {
          setLoadingAgents(false);
        }
      }
    }

    void loadAgents();

    return () => {
      cancelled = true;
    };
  }, [reloadKey]);

  const selectedAgent = agents.find((agent) => String(agent.id) === agentId);
  const formDisabled = loadingAgents || agentError !== null || submitting;
  const selectedAgentId = loadingAgents || agentError !== null ? null : selectedAgent?.id ?? null;

  useEffect(() => {
    onAgentSelected?.(selectedAgentId);
  }, [onAgentSelected, selectedAgentId]);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();

    // Guard the request itself as well as disabling the submit button.
    if (
      submissionInProgress.current ||
      formDisabled ||
      selectedAgent === undefined ||
      message.trim() === ""
    ) {
      return;
    }

    submissionInProgress.current = true;
    setSubmitting(true);
    setSubmitError(null);
    setResult(null);

    try {
      const response = await submitAgentTask(selectedAgent.id, message.trim());
      setResult(response);
      setMessage("");
      onSubmitted(response.execution_id);
    } catch (error) {
      setSubmitError(
        error instanceof ApiError
          ? error.message
          : "Unable to submit task. Check the connection before trying again.",
      );
    } finally {
      submissionInProgress.current = false;
      setSubmitting(false);
    }
  }

  return (
    <section aria-labelledby="task-submission-heading">
      <h2 id="task-submission-heading">Submit Task</h2>

      {loadingAgents && <p>Loading Agents...</p>}

      {agentError !== null && (
        <>
          <p role="alert">{agentError}</p>
          <button
            type="button"
            disabled={loadingAgents}
            onClick={() => setReloadKey((current) => current + 1)}
          >
            Reload Agents
          </button>
        </>
      )}

      {!loadingAgents && agentError === null && agents.length === 0 && (
        <p>No Agents available. Create an Agent before submitting a task.</p>
      )}

      <form onSubmit={(event) => void handleSubmit(event)} aria-busy={submitting}>
        <div>
          <label htmlFor="task-agent">Agent</label>
          <select
            id="task-agent"
            value={agentId}
            disabled={formDisabled || agents.length === 0}
            onChange={(event) => {
              setAgentId(event.target.value);
              setSubmitError(null);
              setResult(null);
            }}
          >
            <option value="">Select an Agent</option>
            {agents.map((agent) => (
              <option key={agent.id} value={agent.id}>
                {agent.name} (ID: {agent.id})
              </option>
            ))}
          </select>
        </div>

        <div>
          <label htmlFor="task-message">Task</label>
          <textarea
            id="task-message"
            rows={4}
            value={message}
            disabled={formDisabled || agents.length === 0}
            onChange={(event) => {
              setMessage(event.target.value);
              setSubmitError(null);
              setResult(null);
            }}
          />
        </div>

        <button
          type="submit"
          disabled={formDisabled || selectedAgent === undefined || message.trim() === ""}
        >
          {submitting ? "Submitting..." : "Submit task"}
        </button>
      </form>

      {submitting && <p role="status">Waiting for the Agent to finish...</p>}
      {submitError !== null && <p role="alert">{submitError}</p>}
      {result !== null && (
        <p role="status">
          Execution {result.execution_id} returned with status: {result.status}.
        </p>
      )}
    </section>
  );
}
