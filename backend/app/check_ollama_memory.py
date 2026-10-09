"""Read-only acceptance of real Ollama retrieval using existing semantic fixtures."""

import argparse
import json
import math
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlsplit
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener

from app.check_demo import require
from app.check_semantic_memory import CHINESE_QUERY, QUERY, default_state_file, validate_checkpoint
from app.config import get_llm_settings
from app.memory_config import get_memory_settings


CONTROL_QUERY = "How can a database recover saved records after a computer reboot?"


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, request, response, code, message, headers, new_url):
        return None


class ReadOnlyAPI:
    def __init__(self, base_url, timeout=180):
        parsed = urlsplit(base_url)
        require(parsed.scheme in {"http", "https"} and bool(parsed.hostname)
                and not parsed.query and not parsed.fragment and not parsed.username,
                "Use an HTTP(S) API base URL without credentials, query, or fragment")
        require(math.isfinite(timeout) and timeout > 0, "HTTP timeout must be a positive finite number")
        self.base_url, self.timeout = base_url.rstrip("/"), timeout
        self.http = build_opener(ProxyHandler({}), NoRedirect())
        self.requests_made = 0

    def get(self, path):
        require(path.startswith("/") and not path.startswith("//"), "Use a relative API path")
        self.requests_made += 1
        request = Request(self.base_url + path, method="GET", headers={"Accept": "application/json"})
        try:
            with self.http.open(request, timeout=self.timeout) as response:
                require(response.headers.get_content_type() == "application/json",
                        "API returned non-JSON content; check the frontend proxy")
                return json.load(response)
        except HTTPError as error:
            detail = ""
            try:
                body = json.load(error)
                if isinstance(body, dict) and isinstance(body.get("detail"), str):
                    detail = ": " + body["detail"][:300]
            except (ValueError, OSError):
                pass
            raise RuntimeError(f"GET {path} returned HTTP {error.code}{detail}") from error


def capture_records(api, state):
    """Include both memory scopes, transcripts, history, and the saved inspection."""
    saved = {"/agents": api.get("/agents")}
    for agent_id in (state["agent_id"], state["peer_agent_id"], state["isolation_agent_id"]):
        for path in (f"/memories/{agent_id}", f"/user-memories/for-agent/{agent_id}",
                     f"/executions?agent_id={agent_id}&limit=100", f"/conversations?agent_id={agent_id}"):
            saved[path] = api.get(path)
        for row in saved[f"/conversations?agent_id={agent_id}"]:
            path = f'/conversations/{row["id"]}/messages'
            saved[path] = api.get(path)
    for suffix in ("", "/trace", "/snapshot"):
        path = f'/executions/{state["execution_id"]}' + suffix
        saved[path] = api.get(path)
    return saved


def validate_rows(rows, scope_key, scope):
    require(isinstance(rows, list), "Memory records must be a list")
    ids = set()
    for row in rows:
        require(isinstance(row, dict) and type(row.get("id")) is int and row["id"] > 0
                and type(row.get(scope_key)) is int and row[scope_key] == scope
                and isinstance(row.get("content"), str) and isinstance(row.get("created_at"), str)
                and row["id"] not in ids, "Memory records contain invalid identity or crossed scope")
        ids.add(row["id"])


def semantic_preview(api, state, before, settings, agent_id, query, *, shared=False, control=False):
    prefix = f"/user-memories/for-agent/{agent_id}" if shared else f"/memories/{agent_id}"
    limit, minimum = (20, 0.0) if control else (5, settings.min_similarity)
    params = {"query": query, "limit": limit}
    if control:
        params["min_similarity"] = minimum
    result = api.get(prefix + "/semantic-search?" + urlencode(params))
    require(isinstance(result, dict) and result.get("provider") == "ollama",
            "The running backend must use real Ollama, not Mock fixtures")
    require(result.get("mode") == "semantic" and result.get("runtime_mode") == "semantic",
            "Enable MEMORY_RETRIEVAL_MODE=semantic on the running Ollama backend")
    require(result.get("model") == settings.embedding_model,
            "Running backend embedding model differs from this check's configuration")
    require(type(result.get("agent_id")) is int and result["agent_id"] == agent_id
            and result.get("query") == query and type(result.get("limit")) is int and result["limit"] == limit
            and type(result.get("min_similarity")) in (int, float)
            and math.isfinite(result["min_similarity"]) and result["min_similarity"] == minimum,
            "Semantic preview returned invalid request metadata")
    context = before[prefix]
    scope_key, scope = ("user_id", context["user_id"]) if shared else ("agent_id", agent_id)
    rows = context["memories"] if shared else context
    validate_rows(rows, scope_key, scope)
    if shared:
        require(type(result.get("user_id")) is int and result["user_id"] == scope,
                "Semantic preview crossed user scope")
    results = result.get("results")
    require(isinstance(results, list) and len(results) <= limit, "Semantic preview returned an invalid result limit")
    previous, ids = None, set()
    for item in results:
        require(isinstance(item, dict), "Semantic result must contain a memory and similarity")
        memory, score = item.get("memory"), item.get("similarity")
        validate_rows([memory], scope_key, scope)
        require(memory in rows and memory["id"] not in ids, "Semantic preview leaked or duplicated a memory")
        require(type(score) in (int, float) and math.isfinite(score) and 0 < score <= 1 and score >= minimum,
                "Semantic preview returned an invalid cosine similarity")
        key = (score, memory["id"])
        require(previous is None or previous >= key, "Semantic results are not ordered by similarity and ID")
        previous = key
        ids.add(memory["id"])
    return results


def quality_result(label, target, relevant, control=None):
    found = next(((index + 1, row["similarity"]) for index, row in enumerate(relevant) if row["memory"] == target), None)
    require(found is not None, f"{label}: expected memory did not appear in the relevant top 5; inspect model quality or configured threshold")
    score = None if control is None else next((row["similarity"] for row in control if row["memory"] == target), None)
    require(score is None or found[1] > score,
            f"{label}: preference scored no better than the unrelated database query; inspect embedding quality")
    return {"scenario": label, "memory_id": target["id"], "rank": found[0], "similarity": found[1],
            "control_similarity": score, "similarity_margin": None if score is None else round(found[1] - score, 6)}


def check_ollama_memory(base_url, state_file=None, timeout=180):
    require(get_llm_settings().provider == "ollama", "Run this check from the Ollama backend without the Mock override")
    settings = get_memory_settings()
    state_file = default_state_file() if state_file is None else Path(state_file)
    require(state_file.is_file(), "Semantic memory checkpoint is missing; complete the Mock semantic acceptance first")
    checkpoint_bytes = state_file.read_bytes()
    state = json.loads(checkpoint_bytes)
    require(isinstance(state, dict) and type(state.get("version")) is int and state["version"] == 1,
            "Semantic memory checkpoint is invalid")
    for key in ("agent_id", "peer_agent_id", "isolation_agent_id", "user_id", "isolation_user_id", "execution_id"):
        require(type(state.get(key)) is int and state[key] > 0, "Semantic memory checkpoint has invalid IDs")
    require(len({state[key] for key in ("agent_id", "peer_agent_id", "isolation_agent_id")}) == 3,
            "Semantic memory checkpoint requires three distinct Agents")
    api = ReadOnlyAPI(base_url, timeout)
    before = capture_records(api, state)
    validate_checkpoint(base_url, state, state["agent_id"], state["peer_agent_id"], state["user_id"], before["/agents"],
                        read=lambda base, path: api.get(path))
    checked = ["saved_fixture_identity"]
    own, peer, other = (state[key] for key in ("agent_id", "peer_agent_id", "isolation_agent_id"))
    for chosen in (own, peer, other):
        context = before[f"/user-memories/for-agent/{chosen}"]
        owner = state["isolation_user_id"] if chosen == other else state["user_id"]
        require(type(context.get("agent_id")) is int and context["agent_id"] == chosen
                and type(context.get("user_id")) is int and context["user_id"] == owner,
                "Saved fixture owner or Agent changed")
    private = semantic_preview(api, state, before, settings, own, QUERY)
    private_control = semantic_preview(api, state, before, settings, own, CONTROL_QUERY, control=True)
    evidence = [quality_result("Agent English paraphrase", state["private"], private, private_control)]
    checked.append("agent_paraphrase_quality")
    shared = semantic_preview(api, state, before, settings, own, CHINESE_QUERY, shared=True)
    shared_control = semantic_preview(api, state, before, settings, own, CONTROL_QUERY, shared=True, control=True)
    evidence.append(quality_result("Shared Chinese paraphrase", state["shared"], shared, shared_control))
    checked.append("shared_chinese_quality")
    peer_shared = semantic_preview(api, state, before, settings, peer, QUERY, shared=True)
    evidence.append(quality_result("Same-user English to Chinese", state["shared"], peer_shared))
    checked.append("same_user_bilingual_retrieval")
    semantic_preview(api, state, before, settings, peer, QUERY)
    foreign = semantic_preview(api, state, before, settings, other, QUERY, shared=True)
    quality_result("Isolated user retrieval", state["isolated"], foreign)
    checked.append("agent_and_user_isolation")
    for prefix, query, target in ((f"/memories/{own}", QUERY, state["private"]),
                                  (f"/user-memories/for-agent/{own}", CHINESE_QUERY, state["shared"])):
        keyword = api.get(prefix + "/search?" + urlencode({"query": query, "limit": 5}))
        require(all(row["memory"] != target for row in keyword["results"]), "Paraphrase fixture unexpectedly overlaps keyword ranking")
    checked.append("keyword_contrast")
    require(capture_records(api, state) == before and state_file.read_bytes() == checkpoint_bytes,
            "Records or checkpoint changed during the read-only check; stop concurrent edits and inspect saved data")
    checked.append("read_only_records_and_checkpoint")
    return {"checks_passed": len(checked), "checks": checked, "embedding_provider": "ollama",
            "embedding_model": settings.embedding_model, "runtime_mode": "semantic", "read_only": True,
            "chat_executions_created": 0, "memory_id": state["private"]["id"], "shared_memory_id": state["shared"]["id"],
            "min_similarity": settings.min_similarity, "requests_made": api.requests_made, "evidence": evidence}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://127.0.0.1:5173")
    parser.add_argument("--state-file", type=Path, help="Existing Mock semantic checkpoint beside SQLite by default")
    parser.add_argument("--timeout", type=float, default=180, help="Positive HTTP timeout in seconds; backend embedding timeout remains separate")
    args = parser.parse_args()
    try:
        result = check_ollama_memory(args.base_url, args.state_file, args.timeout)
    except (HTTPError, URLError, RuntimeError, ValueError, KeyError, TypeError, OSError) as error:
        parser.exit(1, f"Ollama memory check failed: {error}\n")
    print(json.dumps({"status": "passed", **result}))


if __name__ == "__main__":
    main()
