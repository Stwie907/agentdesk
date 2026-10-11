import { useEffect, useState } from "react";

import { ApiError } from "../api/executions";
import { getRuntimeConfiguration, type RuntimeConfiguration } from "../api/runtimeConfiguration";

type Props = { agentId: number | null };

export function RuntimeConfigurationPanel({ agentId }: Props) {
  const [shown, setShown] = useState(false);
  return <RuntimeConfigurationSession key={agentId ?? "global"} agentId={agentId} shown={shown} onToggle={() => setShown((value) => !value)} />;
}

function RuntimeConfigurationSession({ agentId, shown, onToggle }: Props & { shown: boolean; onToggle: () => void }) {
  const [configuration, setConfiguration] = useState<RuntimeConfiguration | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [refreshKey, setRefreshKey] = useState(0);

  useEffect(() => {
    if (!shown) return;
    const controller = new AbortController();
    let active = true;
    setConfiguration(null);
    setError(null);
    setLoading(true);
    void (async () => {
      try {
        const result = await getRuntimeConfiguration(agentId, controller.signal);
        if (active) setConfiguration(result);
      } catch (failure) {
        if (active) setError(failure instanceof ApiError ? failure.message : "Unable to read runtime configuration. Check the connection and refresh.");
      } finally {
        if (active) setLoading(false);
      }
    })();
    return () => { active = false; controller.abort(); };
  }, [agentId, shown, refreshKey]);

  return (
    <section aria-labelledby="runtime-configuration-heading">
      <h2 id="runtime-configuration-heading">Runtime Configuration</h2>
      <button type="button" aria-expanded={shown} aria-controls={shown ? "runtime-configuration-details" : undefined} onClick={onToggle}>
        {shown ? "Hide runtime configuration" : "Show runtime configuration"}
      </button>
      {shown && <div id="runtime-configuration-details" aria-busy={loading}>
        <p>Current settings only. Model availability has not been checked.</p>
        <button type="button" disabled={loading} onClick={() => setRefreshKey((key) => key + 1)}>Refresh runtime configuration</button>
        {loading && <p role="status">Loading runtime configuration...</p>}
        {error !== null && <p role="alert">{error}</p>}
        {configuration !== null && <dl>
          <dt>LLM provider</dt><dd>{configuration.llm_provider === "mock" ? "Mock (simulated)" : "Ollama"}</dd>
          <dt>Selected Agent</dt><dd>{configuration.selected_agent === null ? "No Agent selected" : `ID: ${configuration.selected_agent.id}`}</dd>
          <dt>Selected Agent chat model</dt><dd>{configuration.selected_agent === null ? "Select an Agent to view its chat model" : configuration.selected_agent.chat_model.trim() === "" ? "Not set" : configuration.selected_agent.chat_model}</dd>
          <dt>Configured planner model</dt><dd>{configuration.configured_planner_model}</dd>
          <dt>Memory retrieval mode</dt><dd>{configuration.memory.retrieval_mode === "semantic" ? "Semantic" : "Keyword"}</dd>
          <dt>Configured embedding model</dt><dd>{configuration.memory.configured_embedding_model}</dd>
          <dt>Active embedding model</dt><dd>{configuration.memory.active_embedding_model ?? "Not used in keyword mode"}</dd>
          <dt>Configured minimum similarity</dt><dd>{configuration.memory.min_similarity}</dd>
          <dt>Vector cache setting</dt><dd>{configuration.memory.vector_cache_enabled ? "Enabled" : "Disabled"}</dd>
          <dt>Vector cache activity</dt><dd>{configuration.memory.vector_cache_active ? "Active for semantic retrieval" : "Inactive"}</dd>
          <dt>Database backend</dt><dd>{configuration.database_backend === "sqlite" ? "SQLite" : configuration.database_backend}</dd>
        </dl>}
      </div>}
    </section>
  );
}
