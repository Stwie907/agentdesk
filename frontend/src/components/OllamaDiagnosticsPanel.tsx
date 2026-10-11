import { useEffect, useState } from "react";

import { ApiError } from "../api/executions";
import { getOllamaDiagnostics, type ModelObservation, type OllamaDiagnostics } from "../api/ollamaDiagnostics";

type Props = { agentId: number | null };

const connectionLabels: Record<OllamaDiagnostics["connection_status"], string> = {
  available: "已连接并读取本地模型列表",
  unreachable: "无法连接 Ollama，请确认本地服务已启动及后端连接配置正确。",
  timeout: "读取本地模型列表超时，可以稍后重新检查。",
  http_error: "Ollama 没有返回模型列表，请检查本地服务。",
  invalid_response: "Ollama 返回的模型列表格式无效，请检查本地服务。",
  not_required: "当前使用 Mock 模拟模式，无需连接 Ollama。",
};
const modelLabels: Record<ModelObservation["status"], string> = {
  installed: "已安装", missing: "未安装", unknown: "尚未确认", not_selected: "先选择 Agent",
  not_configured: "尚未设置模型", not_required: "当前模式无需此模型",
};

export function OllamaDiagnosticsPanel({ agentId }: Props) {
  return <ModelCheckSession key={agentId ?? "global"} agentId={agentId} />;
}

function ModelCheckSession({ agentId }: Props) {
  const [trigger, setTrigger] = useState(0);
  const [result, setResult] = useState<OllamaDiagnostics | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (trigger === 0) return;
    const controller = new AbortController();
    let active = true;
    setLoading(true); setResult(null); setError(null);
    void (async () => {
      try {
        const value = await getOllamaDiagnostics(agentId, controller.signal);
        if (active) setResult(value);
      } catch (failure) {
        if (active) setError(failure instanceof ApiError ? failure.message : "本地模型检查失败，请检查连接后重试。");
      } finally {
        if (active) setLoading(false);
      }
    })();
    return () => { active = false; controller.abort(); };
  }, [agentId, trigger]);

  return <section aria-labelledby="ollama-model-check-heading" aria-busy={loading}>
    <h3 id="ollama-model-check-heading">Local Ollama Models / 本地模型检查</h3>
    <p>点击检查聊天、规划和向量模型是否已安装。检查只读取模型列表；安装状态不能证明推理或向量生成功能正常。</p>
    <button type="button" disabled={loading} onClick={() => setTrigger((value) => value + 1)}>检查本地 Ollama 模型</button>
    {loading && <p role="status">正在检查本地模型...</p>}
    {error !== null && <p role="alert">{error}</p>}
    {result !== null && <div>
      <p role={result.connection_status === "available" || result.connection_status === "not_required" ? "status" : "alert"}>
        {connectionLabels[result.connection_status]}{result.model_count !== null && "（共 " + result.model_count + " 个模型）"}
      </p>
      <dl>
        <dt>检查的 Agent</dt><dd>{result.selected_agent_id === null ? "未选择 Agent" : "ID: " + result.selected_agent_id}</dd>
        {([ ["chat", "聊天模型"], ["planner", "规划模型"], ["embedding", "向量模型"] ] as const).map(([role, label]) => {
          const model = result.models[role];
          return <div key={role} style={{ display: "contents" }}>
            <dt>{label}</dt><dd>{model.configured_model ?? "未选择"} — {modelLabels[model.status]}
              {model.installed_name !== null && "（匹配 " + model.installed_name + "）"}</dd>
          </div>;
        })}
      </dl>
    </div>}
  </section>;
}
