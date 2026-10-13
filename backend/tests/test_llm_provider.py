import json

import pytest
import requests

from app.runtime import planner
from app.services import agent_runner, llm_provider


def ollama_response(body, status=200):
    response = requests.Response()
    response.status_code = status
    response.url = "http://localhost:11434/api/generate"
    response._content = json.dumps(body).encode()
    return response


def test_mock_generation_is_marked_and_never_sends_http(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "mock")

    def forbid_request(*args, **kwargs):
        raise AssertionError("Mock must not call an HTTP service")

    monkeypatch.setattr(requests.sessions.Session, "request", forbid_request)
    assert agent_runner.call_llm("unused-model", "first prompt") == llm_provider.MOCK_RESPONSE
    assert agent_runner.call_llm("another-model", "second prompt") == llm_provider.MOCK_RESPONSE
    assert llm_provider.MOCK_RESPONSE.startswith("[MOCK]")


def test_final_generation_uses_configured_url_timeout_and_agent_model(monkeypatch):
    monkeypatch.setenv("OLLAMA_BASE_URL", "http://127.0.0.1:12345/")
    monkeypatch.setenv("OLLAMA_TIMEOUT_SECONDS", "2.5")
    monkeypatch.setenv("OLLAMA_PLANNER_MODEL", "planner-model")
    captured = {}

    def fake_post(url, **kwargs):
        captured.update(url=url, **kwargs)
        return ollama_response({"response": "Real provider response"})

    monkeypatch.setattr(llm_provider.requests, "post", fake_post)
    assert agent_runner.call_llm("agent-model", "Hello") == "Real provider response"
    assert captured == {
        "url": "http://127.0.0.1:12345/api/generate",
        "timeout": 2.5,
        "json": {"model": "agent-model", "prompt": "Hello", "stream": False},
    }


@pytest.mark.parametrize("entry_point", [planner.plan, planner.plan_execution])
def test_both_planner_entry_points_use_configured_model_and_timeout(monkeypatch, entry_point):
    monkeypatch.setenv("OLLAMA_BASE_URL", "https://ollama.example.test")
    monkeypatch.setenv("OLLAMA_PLANNER_MODEL", "demo-planner-model")
    monkeypatch.setenv("OLLAMA_TIMEOUT_SECONDS", "3")
    captured = {}

    def fake_post(url, **kwargs):
        captured.update(url=url, **kwargs)
        return ollama_response({"response": json.dumps({
            "tool": "calculator", "arguments": {"expression": "40+2"},
        })})

    monkeypatch.setattr(llm_provider.requests, "post", fake_post)
    entry_point("计算40+2", allowed_tools=["calculator"])
    assert captured["url"] == "https://ollama.example.test/api/generate"
    assert captured["timeout"] == 3
    assert captured["json"]["model"] == "demo-planner-model"
    assert captured["json"]["stream"] is False


@pytest.mark.parametrize("error, expected", [
    (requests.Timeout("timed out"), TimeoutError),
    (requests.ConnectionError("refused"), ConnectionError),
])
def test_network_errors_use_existing_failure_categories_without_mock_fallback(
    monkeypatch, error, expected,
):
    def fake_post(*args, **kwargs):
        raise error

    monkeypatch.setattr(llm_provider.requests, "post", fake_post)
    with pytest.raises(expected, match="Ollama"):
        agent_runner.call_llm("agent-model", "Hello")


@pytest.mark.parametrize("entry_point", [planner.plan, planner.plan_execution])
def test_planner_http_errors_do_not_become_mock_responses(monkeypatch, entry_point):
    monkeypatch.setattr(llm_provider.requests, "post", lambda *args, **kwargs:
        ollama_response({"error": "model not found"}, status=404))
    with pytest.raises(requests.HTTPError):
        entry_point("计算40+2", allowed_tools=["calculator"])


@pytest.mark.parametrize("body", [{}, [], {"response": None}, {"response": 42}])
def test_malformed_ollama_response_is_a_failure(monkeypatch, body):
    monkeypatch.setattr(llm_provider.requests, "post", lambda *args, **kwargs:
        ollama_response(body))
    with pytest.raises(RuntimeError, match="string 'response'"):
        llm_provider.generate_text("agent-model", "Hello")


def test_non_json_ollama_response_is_a_failure(monkeypatch):
    response = ollama_response({})
    response._content = b"not JSON"
    monkeypatch.setattr(llm_provider.requests, "post", lambda *args, **kwargs: response)
    with pytest.raises(RuntimeError, match="invalid JSON"):
        llm_provider.generate_text("agent-model", "Hello")
