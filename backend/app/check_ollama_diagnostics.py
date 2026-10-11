"""Check installed-model metadata while preserving existing SQLite and checkpoints."""

import argparse
from hashlib import sha256
import json
from urllib.error import URLError

from sqlalchemy.exc import SQLAlchemyError

from app import check_runtime_configuration as reads
from app.check_demo import require
from app.models.agent import Agent
from app.schemas.ollama_diagnostics import OllamaDiagnosticsResponse


CHECKS = ["versioned_metadata_only_contract", "configuration_and_agent_scope", "saved_chat_model",
          "installation_expectations", "invalid_agent_without_probe", "uncached_json_headers",
          "unchanged_sqlite_records_and_vectors", "retained_checkpoint_bytes"]


def validated_diagnostics(reply):
    headers = {key.lower(): value for key, value in reply["headers"].items()}
    require(headers.get("cache-control") == "no-store" and headers.get("x-content-type-options") == "nosniff"
            and headers.get("content-type", "").split(";")[0] == "application/json",
            "Model diagnostics must return uncached JSON with nosniff.")
    value = json.loads(reply["content"])
    require(isinstance(value, dict) and set(value) == set(OllamaDiagnosticsResponse.model_fields)
            and type(value["schema_version"]) is int and value["schema_version"] == 1,
            "Model diagnostics contract is incomplete or invalid.")
    return OllamaDiagnosticsResponse.model_validate(value, strict=True)


def check_ollama_diagnostics(base_url, agent_id, *, expected_provider=None, require_installed=False):
    require(type(agent_id) is int and 0 < agent_id <= 9223372036854775807, "Use a positive saved Agent ID.")
    anchor = reads.checkpoint_anchor()
    before, previous = reads.database_fingerprints(), reads.checkpoint_hashes(anchor)
    with reads.SessionLocal() as db:
        agent = db.get(Agent, agent_id)
        require(agent is not None, "Selected Agent is missing; this check will not create it.")
        saved_model = agent.model
        missing = 9223372036854775807
        while db.get(Agent, missing) is not None and missing > 0:
            missing -= 1
        require(missing > 0, "A missing Agent ID is required for read-only validation.")
    configuration = reads.validated_reply(reads.request_configuration(base_url, f"/runtime/config?agent_id={agent_id}"))
    global_reply = reads.request_configuration(base_url, "/runtime/ollama")
    scoped_reply = reads.request_configuration(base_url, f"/runtime/ollama?agent_id={agent_id}")
    global_value, value = validated_diagnostics(global_reply), validated_diagnostics(scoped_reply)
    require(global_value.selected_agent_id is None and value.selected_agent_id == agent_id,
            "Model diagnostics selected the wrong Agent.")
    require(value.models.chat.configured_model == saved_model, "Model diagnostics changed the saved chat-model selection.")
    for diagnostic in (global_value, value):
        require(diagnostic.llm_provider == configuration.llm_provider
                and diagnostic.memory_retrieval_mode == configuration.memory.retrieval_mode
                and diagnostic.models.planner.configured_model == configuration.configured_planner_model
                and diagnostic.models.embedding.configured_model == configuration.memory.configured_embedding_model,
                "Model diagnostics do not match the current runtime configuration.")
    require(expected_provider is None or value.llm_provider == expected_provider, "LLM provider does not match the expected value.")
    if require_installed:
        require(value.llm_provider == "ollama" and value.connection_status == "available",
                "Local Ollama inventory is unavailable; inspect the diagnostic panel.")
        required = [value.models.chat, value.models.planner]
        if value.memory_retrieval_mode == "semantic":
            required.append(value.models.embedding)
        require(all(item.status == "installed" for item in required),
                "A required local model is missing or unconfigured; inspect the diagnostic panel.")
    reads.request_configuration(base_url, f"/runtime/ollama?agent_id={missing}", 404)
    for invalid in ("0", "-1", "invalid", "9223372036854775808"):
        reads.request_configuration(base_url, "/runtime/ollama?agent_id=" + invalid, 422)
    require(reads.database_fingerprints() == before, "Original SQLite records or vectors changed during diagnostics acceptance.")
    require(reads.checkpoint_hashes(anchor) == previous, "An existing acceptance checkpoint changed during diagnostics acceptance.")
    replies = [sha256(global_reply["content"]).hexdigest(), sha256(scoped_reply["content"]).hexdigest()]
    return {"status": "passed", "checks_passed": len(CHECKS), "checks": CHECKS,
            "agent_id": agent_id, "llm_provider": value.llm_provider,
            "connection_status": value.connection_status, "model_count": value.model_count,
            "models": value.models.model_dump(), "memory_retrieval_mode": value.memory_retrieval_mode,
            "response_sha256": sha256(json.dumps(replies).encode()).hexdigest(),
            "previous_checkpoint_count": len(previous), "read_only": True, "inference_performed": False,
            "model_probe_performed": value.model_probe_performed,
            "original_records_and_vectors_unchanged": True, "previous_checkpoints_unchanged": True,
            "conversations_created": 0, "messages_created": 0, "chat_executions_created": 0}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://frontend")
    parser.add_argument("--agent-id", type=int, required=True)
    parser.add_argument("--expected-provider", choices=("ollama", "mock"))
    parser.add_argument("--require-installed", action="store_true")
    args = parser.parse_args()
    try:
        result = check_ollama_diagnostics(args.base_url, args.agent_id,
            expected_provider=args.expected_provider, require_installed=args.require_installed)
    except (RuntimeError, ValueError, URLError, SQLAlchemyError, OSError) as error:
        message = str(error) if isinstance(error, RuntimeError) else "Model diagnostics acceptance failed. Inspect runtime settings and local service health."
        print(json.dumps({"status": "failed", "message": message}, ensure_ascii=False, indent=2))
        raise SystemExit(1) from error
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
