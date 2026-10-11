import { afterEach, expect, test, vi } from "vitest";

import { getRuntimeConfiguration } from "../src/api/runtimeConfiguration";
import { runtimeConfiguration, semanticRuntimeConfiguration } from "./runtimeConfigurationFixtures";
import { jsonResponse } from "./taskFixtures";

afterEach(() => { vi.unstubAllGlobals(); });

test.each([null, 7])("reads current settings for Agent %s with no-store, one signal and no writes", async (agentId) => {
  const controller = new AbortController(), value = runtimeConfiguration(agentId);
  const fetchMock = vi.fn().mockResolvedValue(jsonResponse(value));
  vi.stubGlobal("fetch", fetchMock);
  expect(await getRuntimeConfiguration(agentId, controller.signal)).toEqual(value);
  expect(fetchMock.mock.calls).toEqual([[agentId === null ? "/runtime/config" : "/runtime/config?agent_id=7",
    { cache: "no-store", signal: controller.signal }]]);
});

test.each(["ollama", "mock"] as const)("validates effective semantic settings for %s", async (provider) => {
  const value = semanticRuntimeConfiguration(7, provider);
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue(jsonResponse(value)));
  expect(await getRuntimeConfiguration(7)).toEqual(value);
});

test.each([0, -1, 1.5, NaN, Infinity, Number.MAX_SAFE_INTEGER + 1])("rejects invalid Agent ID %s before HTTP", async (agentId) => {
  const fetchMock = vi.fn(); vi.stubGlobal("fetch", fetchMock);
  await expect(getRuntimeConfiguration(agentId)).rejects.toMatchObject({ status: 422 });
  expect(fetchMock).not.toHaveBeenCalled();
});

test.each([
  { schema_version: 2 }, { schema_version: true }, { read_only: false }, { model_probe_performed: true },
  { llm_provider: "paid-provider" }, { configured_planner_model: " " }, { database_backend: null },
  { selected_agent: null }, { selected_agent: { id: 8, chat_model: "qwen2.5:7b" } },
  { selected_agent: { id: "7", chat_model: "qwen2.5:7b" } }, { selected_agent: { id: 7, chat_model: 7 } },
  { memory: null },
])("rejects a malformed or foreign response: %s", async (change) => {
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue(jsonResponse({ ...runtimeConfiguration(), ...change })));
  await expect(getRuntimeConfiguration(7)).rejects.toMatchObject({ status: 502 });
});

test.each([
  { retrieval_mode: "hybrid" }, { configured_embedding_model: "" }, { active_embedding_model: "wrong-model" },
  { min_similarity: -0.1 }, { min_similarity: 1.1 }, { min_similarity: NaN }, { min_similarity: "0.35" },
  { vector_cache_enabled: "true" }, { vector_cache_active: true },
])("rejects incoherent or invalid memory settings: %s", async (change) => {
  const value = runtimeConfiguration();
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue(jsonResponse({ ...value, memory: { ...value.memory, ...change } })));
  await expect(getRuntimeConfiguration(7)).rejects.toMatchObject({ status: 502 });
});

test("does not accept a selected Agent in the unscoped response", async () => {
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue(jsonResponse(runtimeConfiguration(7))));
  await expect(getRuntimeConfiguration(null)).rejects.toMatchObject({ status: 502 });
});

test.each([null, [], "html instead of JSON"])("rejects a response without the configuration envelope: %s", async (value) => {
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue(jsonResponse(value)));
  await expect(getRuntimeConfiguration(null)).rejects.toMatchObject({ status: 502 });
});

test.each([404, 503])("preserves the API's explicit %s error", async (status) => {
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue(jsonResponse({ detail: "Explicit configuration error" }, status)));
  await expect(getRuntimeConfiguration(7)).rejects.toMatchObject({ status, message: "Explicit configuration error" });
});

test("reports proxy HTML or malformed JSON as an invalid configuration response", async () => {
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: true, json: async () => { throw new SyntaxError("HTML response"); } }));
  await expect(getRuntimeConfiguration(7)).rejects.toMatchObject({ status: 502, message: "Runtime configuration did not return valid JSON." });
});

test.each(["before", "response", "error"])("honours cancellation %s even when transport ignores it", async (when) => {
  const controller = new AbortController();
  const fetchMock = vi.fn(async () => {
    controller.abort();
    return when === "error" ? jsonResponse({ detail: "Old Agent error" }, 404) : jsonResponse(runtimeConfiguration());
  });
  vi.stubGlobal("fetch", fetchMock);
  if (when === "before") controller.abort();
  await expect(getRuntimeConfiguration(7, controller.signal)).rejects.toMatchObject({ name: "AbortError" });
  expect(fetchMock).toHaveBeenCalledTimes(when === "before" ? 0 : 1);
});
