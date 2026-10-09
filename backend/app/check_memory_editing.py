"""Check scoped memory editing, conflicts, Runtime retrieval, and persistence."""

import argparse
import json
import os
from pathlib import Path
from tempfile import NamedTemporaryFile
from urllib.error import HTTPError, URLError
from uuid import uuid4

from sqlalchemy.engine import make_url

from app.check_demo import request_json, require, verify_snapshot
from app.check_memory import memory_request
from app.check_memory_search import preview
from app.config import DATABASE_URL, get_llm_settings


ORIGINAL = "AgentDeskMemoryEditPython original."
EDITED = "AgentDeskMemoryEditRust updated."


def default_state_file() -> Path:
    database = make_url(DATABASE_URL).database
    require(bool(database) and database != ":memory:", "Use a persistent SQLite database for this check")
    return Path(database).resolve().parent / "memory-edit-acceptance.json"


def patch(base_url, row, content, expected=None, status=200, agent_id=None):
    scope = row["agent_id"] if agent_id is None else agent_id
    return memory_request(base_url, f'/memories/item/{row["id"]}?agent_id={scope}', {
        "content": content, "expected_content": row["content"] if expected is None else expected,
    }, method="PATCH", status=status)


def check_memory_editing(base_url: str, verify_persistence: bool = False, state_file: Path | None = None) -> dict:
    state_file = default_state_file() if state_file is None else Path(state_file)
    agents = request_json(base_url, "/agents")
    demos = [row for row in agents if row["name"] == "Demo Agent"]
    others = [row for row in agents if row["name"] == "MCP Order Agent"]
    require(len(demos) == len(others) == 1, "Run the demo initializer first")
    agent_id, other_id = demos[0]["id"], others[0]["id"]
    before = request_json(base_url, f"/memories/{agent_id}")
    checkpoint = None
    if state_file.exists():
        state = json.loads(state_file.read_text(encoding="utf-8"))
        require(isinstance(state, dict) and state.get("version") == 1 and isinstance(state.get("memory"), dict),
                "Memory edit persistence checkpoint is invalid")
        checkpoint = state["memory"]
        require(checkpoint.get("agent_id") == agent_id and checkpoint.get("content") == EDITED,
                "Memory edit persistence checkpoint has the wrong Agent or content")
        require(checkpoint in before, "Edited demo memory was lost or changed; persistence verification made no replacement write")
    if verify_persistence:
        require(checkpoint is not None, "Memory edit checkpoint was lost; run the initial check before restart")
    existing = [row for row in before if row["content"] == EDITED]
    require(len(existing) <= 1, "Duplicate edited demo memories exist")
    if existing:
        saved = existing[0]
        require(patch(base_url, saved, EDITED) == saved, "An unchanged edit changed memory identity")
    else:
        original = memory_request(base_url, "/memories", {"agent_id": agent_id, "content": ORIGINAL})
        saved = patch(base_url, original, "  " + EDITED + "  ")
        require(saved == {**original, "content": EDITED}, "Edit changed the memory ID, Agent, or creation time")
    require(saved["content"] == EDITED and saved["agent_id"] == agent_id, "Memory edit was not trimmed and scoped")
    if checkpoint is not None:
        require(saved == checkpoint, "Edited demo memory identity or creation time changed")
    require(preview(base_url, agent_id, "AgentDeskMemoryEditPython")["results"] == [], "Old memory content still matches")
    matched = preview(base_url, agent_id, "AgentDeskMemoryEditRust")["results"]
    require(len(matched) == 1 and matched[0]["memory"] == saved, "Preview did not use the edited record")

    own_before = request_json(base_url, f"/memories/{agent_id}")
    other_before = request_json(base_url, f"/memories/{other_id}")
    history_before = request_json(base_url, f"/executions?agent_id={agent_id}&limit=100")
    conversations_before = request_json(base_url, f"/conversations?agent_id={agent_id}")
    transient = memory_request(base_url, "/memories", {"agent_id": agent_id, "content": "AgentDeskEditDuplicate " + uuid4().hex})
    try:
        rows = request_json(base_url, f"/memories/{agent_id}")
        patch(base_url, saved, transient["content"], status=409)
        patch(base_url, saved, "Do not overwrite the current record.", expected=ORIGINAL, status=409)
        patch(base_url, saved, "Wrong Agent", agent_id=other_id, status=404)
        for payload in (
            {"content": " \n\t", "expected_content": EDITED},
            {"content": "x" * 2001, "expected_content": EDITED},
            {"content": "New", "expected_content": EDITED, "agent_id": other_id},
            {"content": "New"},
        ):
            memory_request(base_url, f'/memories/item/{saved["id"]}?agent_id={agent_id}', payload, method="PATCH", status=422)
        memory_request(base_url, f'/memories/item/{saved["id"]}',
                       {"content": "New", "expected_content": EDITED}, method="PATCH", status=422)
        memory_request(base_url, f'/memories/item/1000000000?agent_id={agent_id}',
                       {"content": "New", "expected_content": EDITED}, method="PATCH", status=404)
        require(request_json(base_url, f"/memories/{agent_id}") == rows, "Rejected edits changed saved records")
        require(request_json(base_url, f"/memories/{other_id}") == other_before, "Memory edits crossed Agent scope")
        require(request_json(base_url, f"/executions?agent_id={agent_id}&limit=100") == history_before,
                "Memory editing created or changed an execution")
        require(request_json(base_url, f"/conversations?agent_id={agent_id}") == conversations_before,
                "Memory editing changed conversations")
    finally:
        memory_request(base_url, f'/memories/item/{transient["id"]}?agent_id={agent_id}', method="DELETE")
    require(request_json(base_url, f"/memories/{agent_id}") == own_before, "Conflict checks changed protected memories")

    chat = request_json(base_url, f"/agents/{agent_id}/chat", {"message": "What about AgentDeskMemoryEditRust?"})
    require(chat["status"] == "completed" and chat["response"].startswith("[MOCK]"), "Expected a fixed Mock reply")
    logs = request_json(base_url, f'/execution-logs/{chat["execution_id"]}')
    require(any(row["message"] == "memory_retrieved: Relevant memory loaded" for row in logs),
            "Runtime did not retrieve the edited memory")
    verify_snapshot(base_url, chat["execution_id"], chat["response"])
    require(request_json(base_url, f"/memories/{agent_id}") == own_before, "Runtime check changed saved memories")
    if checkpoint is None:
        state_file.parent.mkdir(parents=True, exist_ok=True)
        with NamedTemporaryFile(mode="w", encoding="utf-8", dir=state_file.parent, delete=False) as handle:
            temporary = Path(handle.name)
            json.dump({"version": 1, "memory": saved}, handle, ensure_ascii=False)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        try:
            os.replace(temporary, state_file)
        finally:
            temporary.unlink(missing_ok=True)
    return {"agent_id": agent_id, "memory_id": saved["id"], "created_at": saved["created_at"],
            "execution_id": chat["execution_id"], "checks_passed": 6,
            "persistence_verified": verify_persistence, "reply_mode": "fixed_mock_reply"}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://127.0.0.1:5173")
    parser.add_argument("--verify-persistence", action="store_true")
    parser.add_argument("--state-file", type=Path, help="Persistence checkpoint; stored beside the SQLite database by default")
    args = parser.parse_args()
    try:
        require(get_llm_settings().provider == "mock", "Run this check from the Mock backend container")
        result = check_memory_editing(args.base_url, args.verify_persistence, args.state_file)
    except (HTTPError, URLError, RuntimeError, ValueError, KeyError, TypeError, OSError) as error:
        parser.exit(1, f"Memory editing check failed: {error}\n")
    print(json.dumps({"status": "passed", **result}))


if __name__ == "__main__":
    main()
