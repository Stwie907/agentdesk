import { afterEach, expect, test, vi } from "vitest";

import { getOllamaDiagnostics, validateOllamaDiagnostics } from "../src/api/ollamaDiagnostics";
import { installedModels, failedModels } from "./ollamaDiagnosticsFixtures";
import { deferredResponse, jsonResponse } from "./taskFixtures";

afterEach(() => vi.unstubAllGlobals());

test.each([null, 7])("uses one uncached GET for the requested scope %s", async (agentId) => {
  const value = installedModels(agentId), fetchMock = vi.fn().mockResolvedValue(jsonResponse(value));
  const controller = new AbortController(); vi.stubGlobal("fetch", fetchMock);
  expect(await getOllamaDiagnostics(agentId, controller.signal)).toEqual(value);
  expect(fetchMock).toHaveBeenCalledOnce();
  expect(fetchMock).toHaveBeenCalledWith("/runtime/ollama" + (agentId === null ? "" : "?agent_id=7"), { cache: "no-store", signal: controller.signal });
});

test.each([0, -1, 1.5, Number.NaN, Number.POSITIVE_INFINITY, Number.MAX_SAFE_INTEGER + 1])("rejects invalid Agent %s before fetch", async (id) => {
  const fetchMock = vi.fn(); vi.stubGlobal("fetch", fetchMock);
  await expect(getOllamaDiagnostics(id)).rejects.toMatchObject({ status: 422 });
  expect(fetchMock).not.toHaveBeenCalled();
});

test.each([
  ["version", { schema_version: 2 }], ["boolean version", { schema_version: true }],
  ["write claim", { read_only: false }], ["inference claim", { inference_performed: true }],
  ["wrong scope", { selected_agent_id: 8 }], ["wrong provider", { llm_provider: "paid" }],
  ["missing probe", { model_probe_performed: false }], ["unknown mode", { memory_retrieval_mode: "hybrid" }],
  ["wrong connection", { connection_status: "ready" }], ["null count", { model_count: null }],
  ["zero count with installed models", { model_count: 0 }], ["large count", { model_count: 1001 }],
  ["fractional count", { model_count: 1.5 }], ["missing models", { models: null }],
])("rejects inconsistent %s", (_, patch) => {
  expect(() => validateOllamaDiagnostics({ ...installedModels(), ...patch }, 7)).toThrow(/invalid response/);
});

test.each([
  { status: "installed", installed_name: "qwen2.5:14b" },
  { status: "installed", installed_name: "qwen2.5:7b:latest" },
  { status: "installed", installed_name: null },
  { status: "missing", installed_name: "qwen2.5:7b" },
  { status: "not_selected", configured_model: null, installed_name: null },
  { status: "unknown", installed_name: null },
])("rejects invalid scoped chat observation %j", (patch) => {
  const value = installedModels(); Object.assign(value.models.chat, patch);
  expect(() => validateOllamaDiagnostics(value, 7)).toThrow(/invalid response/);
});

test("accepts a bare model's latest alias and keeps explicit tags exact", () => {
  const value = installedModels();
  expect(validateOllamaDiagnostics(value, 7).models.embedding.installed_name).toBe("embeddinggemma:latest");
});

test.each(["unreachable", "timeout", "http_error", "invalid_response"] as const)("accepts %s without pretending models are absent", (status) => {
  expect(validateOllamaDiagnostics(failedModels(status), 7).models.chat.status).toBe("unknown");
});

test("accepts skipped Mock and keyword embeddings but rejects contradictory probes", () => {
  const value = installedModels();
  value.llm_provider = "mock"; value.model_probe_performed = false; value.connection_status = "not_required"; value.model_count = null;
  Object.values(value.models).forEach((item) => { item.status = "not_required"; item.installed_name = null; });
  expect(validateOllamaDiagnostics(value, 7)).toEqual(value);
  expect(() => validateOllamaDiagnostics({ ...value, model_probe_performed: true }, 7)).toThrow();
  const keyword = installedModels(); keyword.memory_retrieval_mode = "keyword";
  expect(() => validateOllamaDiagnostics(keyword, 7)).toThrow();
  keyword.models.embedding.status = "not_required"; keyword.models.embedding.installed_name = null;
  expect(validateOllamaDiagnostics(keyword, 7)).toEqual(keyword);
});

test("does not accept another Agent or a selected model in global results", () => {
  expect(() => validateOllamaDiagnostics(installedModels(), null)).toThrow();
  const value = installedModels(null); value.models.chat.configured_model = "qwen2.5:7b";
  expect(() => validateOllamaDiagnostics(value, null)).toThrow();
});

test("rejects an already aborted read without contacting the backend", async () => {
  const controller = new AbortController(); controller.abort(); const fetchMock = vi.fn(); vi.stubGlobal("fetch", fetchMock);
  await expect(getOllamaDiagnostics(7, controller.signal)).rejects.toMatchObject({ name: "AbortError" });
  expect(fetchMock).not.toHaveBeenCalled();
});

test("late non-cooperative response still respects cancellation", async () => {
  const pending = deferredResponse(), controller = new AbortController();
  vi.stubGlobal("fetch", vi.fn().mockReturnValue(pending.promise));
  const result = getOllamaDiagnostics(7, controller.signal); controller.abort(); pending.resolve(jsonResponse(installedModels()));
  await expect(result).rejects.toMatchObject({ name: "AbortError" });
});

test("malformed JSON has a stable public error", async () => {
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: true, json: async () => { throw new SyntaxError("private raw text"); } }));
  await expect(getOllamaDiagnostics(7)).rejects.toMatchObject({ status: 502, message: "Local model check did not return valid JSON." });
});
