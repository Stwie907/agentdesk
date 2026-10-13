"""Read-only configuration acceptance against the existing SQLite database."""

import argparse
from hashlib import sha256
import json
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener

from sqlalchemy.engine import make_url
from sqlalchemy.exc import SQLAlchemyError

from app.check_conversation_export import checkpoint_hashes
from app.check_conversation_pagination import database_fingerprints
from app.check_demo import require
from app.config import DATABASE_URL
from app.database import SessionLocal
from app.models.agent import Agent
from app.schemas.runtime_configuration import RuntimeConfigurationResponse


CHECKS = ["versioned_read_only_contract", "global_configuration", "selected_agent_chat_model",
          "agent_scope_and_validation", "uncached_response_headers", "configured_expectations",
          "unchanged_sqlite_records_and_vectors", "retained_checkpoint_bytes"]


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, request, file, code, message, headers, new_url):
        return None


def request_configuration(base_url, path, status=200):
    request = Request(base_url.rstrip("/") + path, method="GET")
    try:
        response = build_opener(ProxyHandler({}), NoRedirect()).open(request, timeout=15)
    except HTTPError as error:
        response = error
    with response:
        require(response.status == status, f"Runtime configuration returned {response.status}, expected {status}.")
        content = response.read(65537)
        require(len(content) <= 65536, "Runtime configuration response exceeds 64 KiB.")
        return {"status": response.status, "headers": {key.lower(): value for key, value in response.headers.items()},
                "content": content}


def checkpoint_anchor():
    database = make_url(DATABASE_URL)
    require(database.get_backend_name() == "sqlite" and database.database not in (None, "", ":memory:"),
            "Use the existing persistent SQLite database for this check.")
    return Path(database.database).resolve().parent / ".runtime-configuration-read-anchor"


def validated_reply(reply):
    headers = {key.lower(): value for key, value in reply["headers"].items()}
    require(headers.get("cache-control") == "no-store" and headers.get("x-content-type-options") == "nosniff"
            and headers.get("content-type", "").split(";")[0] == "application/json",
            "Runtime configuration must be uncached JSON with nosniff.")
    value = json.loads(reply["content"])
    require(isinstance(value, dict) and set(value) == set(RuntimeConfigurationResponse.model_fields)
            and type(value["schema_version"]) is int and value["schema_version"] == 1
            and value["read_only"] is True and value["model_probe_performed"] is False,
            "Runtime configuration contract is incomplete or invalid.")
    return RuntimeConfigurationResponse.model_validate(value, strict=True)


def check_runtime_configuration(base_url, agent_id, *, expected_provider=None, expected_chat_model=None,
                                expected_planner_model=None, expected_memory_mode=None, expected_vector_cache=None):
    require(type(agent_id) is int and 0 < agent_id <= 9223372036854775807, "Use a positive saved Agent ID.")
    anchor = checkpoint_anchor()
    before, previous = database_fingerprints(), checkpoint_hashes(anchor)
    with SessionLocal() as db:
        agent = db.get(Agent, agent_id)
        require(agent is not None, "Selected Agent is missing; this check will not create it.")
        saved_model = agent.model
        missing_id = 9223372036854775807
        while db.get(Agent, missing_id) is not None and missing_id > 0:
            missing_id -= 1
        require(missing_id > 0, "A missing Agent ID is required for the read-only scope probe.")
    global_uri, scoped_uri = "/runtime/config", f"/runtime/config?agent_id={agent_id}"
    global_reply = request_configuration(base_url, global_uri)
    scoped_reply = request_configuration(base_url, scoped_uri)
    global_config, scoped = validated_reply(global_reply), validated_reply(scoped_reply)
    require(global_config.selected_agent is None, "Global configuration must not select an Agent.")
    require(scoped.selected_agent is not None and scoped.selected_agent.id == agent_id
            and scoped.selected_agent.chat_model == saved_model, "Selected Agent model differs from the original saved record.")
    require(global_config.model_dump(exclude={"selected_agent"}) == scoped.model_dump(exclude={"selected_agent"})
            and scoped.database_backend == "sqlite", "Global and scoped process settings differ.")
    for value, expected, label in (
        (scoped.llm_provider, expected_provider, "LLM provider"),
        (scoped.selected_agent.chat_model, expected_chat_model, "Agent chat model"),
        (scoped.configured_planner_model, expected_planner_model, "planner model"),
        (scoped.memory.retrieval_mode, expected_memory_mode, "memory retrieval mode"),
        (scoped.memory.vector_cache_enabled, expected_vector_cache, "vector cache setting"),
    ):
        require(expected is None or value == expected, f"Configured {label} does not match the expected value.")
    request_configuration(base_url, f"/runtime/config?agent_id={missing_id}", 404)
    for invalid in ("0", "-1", "invalid", "9223372036854775808"):
        request_configuration(base_url, f"/runtime/config?agent_id={invalid}", 422)
    require(database_fingerprints() == before, "Original SQLite records or vectors changed during configuration acceptance.")
    require(checkpoint_hashes(anchor) == previous, "An existing acceptance checkpoint changed during configuration acceptance.")
    replies = {global_uri: sha256(global_reply["content"]).hexdigest(), scoped_uri: sha256(scoped_reply["content"]).hexdigest()}
    return {
        "status": "passed", "checks_passed": len(CHECKS), "checks": CHECKS,
        "agent_id": agent_id, "llm_provider": scoped.llm_provider,
        "agent_chat_model": scoped.selected_agent.chat_model,
        "configured_planner_model": scoped.configured_planner_model,
        "memory": scoped.memory.model_dump(), "database_backend": scoped.database_backend,
        "response_sha256": sha256(json.dumps(replies, sort_keys=True).encode()).hexdigest(),
        "previous_checkpoint_count": len(previous), "read_only": True, "model_probe_performed": False,
        "original_records_and_vectors_unchanged": True, "previous_checkpoints_unchanged": True,
        "conversations_created": 0, "messages_created": 0, "chat_executions_created": 0,
    }


def main():
    parser = argparse.ArgumentParser(description="Read runtime configuration without model requests or database writes.")
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--agent-id", type=int, required=True)
    parser.add_argument("--expected-provider", choices=("ollama", "mock"))
    parser.add_argument("--expected-chat-model")
    parser.add_argument("--expected-planner-model")
    parser.add_argument("--expected-memory-mode", choices=("keyword", "semantic"))
    parser.add_argument("--expected-vector-cache", choices=("true", "false"))
    args = parser.parse_args()
    try:
        result = check_runtime_configuration(args.base_url, args.agent_id,
            expected_provider=args.expected_provider, expected_chat_model=args.expected_chat_model,
            expected_planner_model=args.expected_planner_model, expected_memory_mode=args.expected_memory_mode,
            expected_vector_cache=None if args.expected_vector_cache is None else args.expected_vector_cache == "true")
    except (RuntimeError, ValueError, URLError, SQLAlchemyError, OSError) as error:
        # Do not echo URLs, environment values or SQL connection details.
        message = str(error) if isinstance(error, RuntimeError) else "Unable to verify runtime configuration. Check the backend, saved Agent and expected settings."
        print(json.dumps({"status": "failed", "error": message}))
        return 1
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
