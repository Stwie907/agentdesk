"""Manual memory writes share retrieval policy and stay within an Agent scope."""

import pytest

from app.services.memory_service import build_memory_context, save_agent_memory
from test_mcp_runtime_api import demo_api  # noqa: F401


def save(client, agent_id, content):
    response = client.post("/memories", json={"agent_id": agent_id, "content": content})
    assert response.status_code == 200
    return response.json()


def test_trim_duplicate_name_policy_and_retrieval(demo_api):
    client, ids, sessions = demo_api
    agent_id = ids["agent_id"]
    first = save(client, agent_id, "  Python answers should be concise. \n")
    repeated = save(client, agent_id, "Python answers should be concise.")
    assert repeated == first
    assert len(client.get(f"/memories/{agent_id}").json()) == 1
    old_name = save(client, agent_id, "User's name is Tom.")
    new_name = save(client, agent_id, "User's name is Jane.")
    assert new_name["id"] == old_name["id"]
    assert new_name["created_at"] == old_name["created_at"]
    assert new_name["content"] == "User's name is Jane."
    with sessions() as db:
        assert build_memory_context(db, agent_id, "What about Python?") == first["content"]
        assert build_memory_context(db, ids["mcp_agent_id"], "Python") == ""


def test_list_and_scoped_delete_do_not_cross_agents(demo_api):
    client, ids, _ = demo_api
    first = save(client, ids["agent_id"], "Python")
    other = save(client, ids["mcp_agent_id"], "Python")
    assert first["id"] != other["id"]
    assert client.get(f'/memories/{ids["agent_id"]}').json() == [first]
    assert client.get(f'/memories/{ids["mcp_agent_id"]}').json() == [other]
    url = f'/memories/item/{other["id"]}?agent_id={ids["agent_id"]}'
    response = client.delete(url)
    assert response.status_code == 404
    assert response.json()["detail"] == "Memory not found for this Agent"
    assert client.get(f'/memories/{ids["mcp_agent_id"]}').json() == [other]
    own_url = f'/memories/item/{other["id"]}?agent_id={ids["mcp_agent_id"]}'
    assert client.delete(own_url).status_code == 200
    assert client.delete(own_url).status_code == 404
    assert client.get(f'/memories/{ids["mcp_agent_id"]}').json() == []
    assert client.get(f'/memories/{ids["agent_id"]}').json() == [first]


@pytest.mark.parametrize("content", ["", " \n\t ", "x" * 2001, None, 123, False, [], {}])
def test_invalid_content_never_writes(demo_api, content):
    client, ids, _ = demo_api
    assert client.post("/memories", json={"agent_id": ids["agent_id"], "content": content}).status_code == 422
    assert client.get(f'/memories/{ids["agent_id"]}').json() == []


@pytest.mark.parametrize("agent_id", [0, -1, "1", 1.5, True, None])
def test_invalid_create_agent_id_never_writes(demo_api, agent_id):
    client, ids, _ = demo_api
    assert client.post("/memories", json={"agent_id": agent_id, "content": "Python"}).status_code == 422
    assert client.get(f'/memories/{ids["agent_id"]}').json() == []


def test_maximum_content_and_internal_extraction_are_preserved(demo_api):
    client, ids, sessions = demo_api
    saved = save(client, ids["agent_id"], "  " + "x" * 2000 + "  ")
    assert len(saved["content"]) == 2000
    # The API limit must not add a new failure to existing automatic extraction.
    with sessions() as db:
        extracted = save_agent_memory(db, ids["agent_id"], "User likes " + "y" * 2000 + ".")
        assert len(extracted.content) > 2000
    rows = client.get(f'/memories/{ids["agent_id"]}').json()
    assert len(rows) == 2


def test_unknown_agent_is_404_without_orphan_memory(demo_api):
    client, ids, _ = demo_api
    agent_id = max(ids.values()) + 100000
    assert client.get(f"/memories/{agent_id}").status_code == 404
    assert client.post("/memories", json={"agent_id": agent_id, "content": "Python"}).status_code == 404
    assert client.get(f'/memories/{ids["agent_id"]}').json() == []


@pytest.mark.parametrize("url,method", [
    ("/memories/0", "get"),
    ("/memories/-1", "get"),
    ("/memories/item/0", "delete"),
    ("/memories/item/1?agent_id=0", "delete"),
])
def test_invalid_path_or_scope_is_422(demo_api, url, method):
    client, _, _ = demo_api
    assert getattr(client, method)(url).status_code == 422


def test_legacy_delete_without_scope_remains_compatible(demo_api):
    client, ids, _ = demo_api
    memory = save(client, ids["agent_id"], "A legacy client memory")
    assert client.delete(f'/memories/item/{memory["id"]}').json() == {"message": "Memory deleted successfully"}
    assert client.get(f'/memories/{ids["agent_id"]}').json() == []
