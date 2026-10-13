"""Check persisted Runtime retrieval evidence using existing offline semantic fixtures."""

import argparse
import json
import os
from pathlib import Path
from tempfile import NamedTemporaryFile
from urllib.error import HTTPError, URLError

from app import check_semantic_memory as semantic
from app.check_demo import request_json, require
from app.check_memory import memory_request
from app.check_user_memory import inspection
from app.config import get_llm_settings
from app.schemas.memory_evidence import MemoryEvidence


LABELS = ("semantic", "fallback", "isolation")


def default_state_file():
    return semantic.default_state_file().with_name("memory-evidence-acceptance.json")


def read_capture(base_url, execution_id, agent_id, query):
    body = request_json(base_url, f"/executions/{execution_id}/memory-context?agent_id={agent_id}")
    require(body.get("execution_id") == execution_id and body.get("available") is True,
            "Runtime memory evidence was lost or was not recorded")
    facts = MemoryEvidence.model_validate_json(json.dumps(body.get("evidence")))
    require(facts.agent_id == agent_id and facts.query == query, "Runtime evidence belongs to another execution")
    return body


def check_cases(cases, source):
    require(isinstance(cases, dict) and set(cases) == set(LABELS), "Memory evidence checkpoint cases are invalid")
    expected = {
        "semantic": (source["agent_id"], semantic.QUERY),
        "fallback": (source["agent_id"], semantic.PRIVATE),
        "isolation": (source["isolation_agent_id"], semantic.QUERY),
    }
    for label, (agent_id, query) in expected.items():
        case = cases[label]
        require(isinstance(case, dict) and type(case.get("execution_id")) is int and case["execution_id"] > 0
                and case.get("agent_id") == agent_id and case.get("query") == query
                and isinstance(case.get("inspection"), dict), "Memory evidence checkpoint has invalid execution data")
        body = case.get("memory_context")
        require(isinstance(body, dict) and body.get("execution_id") == case["execution_id"] and body.get("available") is True,
                "Memory evidence checkpoint capture is invalid")
        facts = MemoryEvidence.model_validate_json(json.dumps(body.get("evidence")))
        require(facts.agent_id == agent_id and facts.query == query and facts.requested_mode == "semantic",
                "Memory evidence checkpoint has the wrong retrieval context")
        if label == "fallback":
            require(facts.mode == "keyword" and facts.fallback_reason
                    and any(row.memory_id == source["private"]["id"] and row.content == semantic.PRIVATE and row.score > 0
                            for row in facts.agent_memories), "Keyword fallback evidence is missing its original result or reason")
        else:
            require(facts.mode == "semantic" and facts.provider == "mock" and facts.model == "mock-fixtures-v1",
                    "Expected explicitly marked Mock semantic evidence")
            if label == "semantic":
                require(facts.user_id == source["user_id"]
                        and any(row.memory_id == source["private"]["id"] and row.content == semantic.PRIVATE and row.similarity == 0.96
                                for row in facts.agent_memories)
                        and any(row.memory_id == source["shared"]["id"] and row.content == semantic.SHARED and row.similarity == 0.96
                                for row in facts.shared_memories), "Semantic evidence did not capture both memory scopes")
            else:
                require(facts.user_id == source["isolation_user_id"] and facts.agent_memories == []
                        and any(row.memory_id == source["isolated"]["id"] and row.content == semantic.PRIVATE and row.similarity == 0.96
                                for row in facts.shared_memories), "Memory evidence crossed the isolation fixture scope")
                require(all(row.scope_id == source["isolation_user_id"] for row in facts.shared_memories),
                        "Shared evidence leaked another user's memory")


def check_memory_evidence(base_url, verify_persistence=False, state_file=None, semantic_state_file=None):
    state_file = default_state_file() if state_file is None else Path(state_file)
    source_file = semantic.default_state_file() if semantic_state_file is None else Path(semantic_state_file)
    require(not verify_persistence or state_file.is_file(), "Memory evidence checkpoint is missing; run the initial check first")
    require(source_file.is_file(), "Run the initial semantic memory check first and retain its checkpoint")
    source_bytes = source_file.read_bytes()
    source = json.loads(source_bytes)
    agents = request_json(base_url, "/agents")
    demos = [row for row in agents if row["name"] == "Demo Agent"]
    peers = [row for row in agents if row["name"] == "MCP Order Agent"]
    require(len(demos) == len(peers) == 1, "Run the demo initializer first")
    agent_id, peer_id = demos[0]["id"], peers[0]["id"]
    owner = request_json(base_url, f"/user-memories/for-agent/{agent_id}")["user_id"]
    semantic.validate_checkpoint(base_url, source, agent_id, peer_id, owner, agents, read=request_json)
    paths = [f"/memories/{chosen}" for chosen in (agent_id, peer_id, source["isolation_agent_id"])]
    paths += [f"/user-memories/for-agent/{chosen}" for chosen in (agent_id, peer_id, source["isolation_agent_id"])]
    before = {path: request_json(base_url, path) for path in paths}
    reused = state_file.is_file()
    if reused:
        state = json.loads(state_file.read_text(encoding="utf-8"))
        require(isinstance(state, dict) and type(state.get("version")) is int and state["version"] == 1
                and state.get("source_checkpoint") == source, "Memory evidence checkpoint is invalid or its source changed")
        cases = state.get("cases")
        check_cases(cases, source)
        for case in cases.values():
            require(read_capture(base_url, case["execution_id"], case["agent_id"], case["query"]) == case["memory_context"]
                    and inspection(base_url, case["execution_id"]) == case["inspection"],
                    "Persisted execution, trace, snapshot, or memory evidence was lost or changed")
    else:
        probe = semantic.preview(base_url, agent_id)
        require(probe["provider"] == "mock" and probe["model"] == "mock-fixtures-v1" and probe["runtime_mode"] == "semantic",
                "Enable semantic mode on the running Mock backend first")
        cases = {}
        for label, chosen, query in (("semantic", agent_id, semantic.QUERY),
                                     ("fallback", agent_id, semantic.PRIVATE),
                                     ("isolation", source["isolation_agent_id"], semantic.QUERY)):
            reply = request_json(base_url, f"/agents/{chosen}/chat", {"message": query})
            require(reply["status"] == "completed" and reply["response"].startswith("[MOCK]"), "Expected a fixed Mock reply")
            execution_id = reply["execution_id"]
            cases[label] = {"execution_id": execution_id, "agent_id": chosen, "query": query,
                            "memory_context": read_capture(base_url, execution_id, chosen, query),
                            "inspection": inspection(base_url, execution_id)}
        check_cases(cases, source)
    for path in ("/executions/0/memory-context", "/executions/1/memory-context?agent_id=0"):
        memory_request(base_url, path, status=422)
    memory_request(base_url, f'/executions/{cases["semantic"]["execution_id"]}/memory-context?agent_id={peer_id}', status=404)
    require({path: request_json(base_url, path) for path in paths} == before and source_file.read_bytes() == source_bytes,
            "Evidence checks changed source memories or their original checkpoint")
    semantic.validate_checkpoint(base_url, source, agent_id, peer_id, owner, agents, read=request_json)
    if not reused:
        state_file.parent.mkdir(parents=True, exist_ok=True)
        with NamedTemporaryFile(mode="w", encoding="utf-8", dir=state_file.parent, delete=False) as handle:
            temporary = Path(handle.name)
            json.dump({"version": 1, "source_checkpoint": source, "cases": cases}, handle, ensure_ascii=False)
            handle.write("\n"); handle.flush(); os.fsync(handle.fileno())
        try: os.replace(temporary, state_file)
        finally: temporary.unlink(missing_ok=True)
    return {"checks_passed": 6, "execution_ids": {label: case["execution_id"] for label, case in cases.items()},
            "persistence_verified": verify_persistence, "checkpoint_reused": reused,
            "chat_executions_created": 0 if reused else 3, "source_memories_unchanged": True,
            "embedding_provider": "mock", "captured_runtime_mode": "semantic", "reply_mode": "fixed_mock_reply"}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://127.0.0.1:5173")
    parser.add_argument("--verify-persistence", action="store_true")
    parser.add_argument("--state-file", type=Path)
    parser.add_argument("--semantic-state-file", type=Path)
    args = parser.parse_args()
    try:
        require(get_llm_settings().provider == "mock", "Run this check from the Mock backend")
        result = check_memory_evidence(args.base_url, args.verify_persistence, args.state_file, args.semantic_state_file)
    except (HTTPError, URLError, RuntimeError, ValueError, KeyError, TypeError, OSError) as error:
        parser.exit(1, f"Memory evidence check failed: {error}\n")
    print(json.dumps({"status": "passed", **result}))


if __name__ == "__main__": main()
