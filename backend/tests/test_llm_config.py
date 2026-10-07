import pytest

from app.config import get_llm_settings


def test_llm_defaults_preserve_ollama_settings():
    settings = get_llm_settings()
    assert settings.provider == "ollama"
    assert settings.generate_url == "http://localhost:11434/api/generate"
    assert settings.planner_model == "qwen2.5:7b"
    assert settings.timeout_seconds == 120


def test_llm_environment_overrides_are_normalized(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", " MOCK ")
    monkeypatch.setenv("OLLAMA_BASE_URL", " http://127.0.0.1:12345/ ")
    monkeypatch.setenv("OLLAMA_PLANNER_MODEL", " local-planner ")
    monkeypatch.setenv("OLLAMA_TIMEOUT_SECONDS", "2.5")
    settings = get_llm_settings()
    assert settings.provider == "mock"
    assert settings.generate_url == "http://127.0.0.1:12345/api/generate"
    assert settings.planner_model == "local-planner"
    assert settings.timeout_seconds == 2.5


@pytest.mark.parametrize("provider", ["", "unknown", "openai"])
def test_invalid_provider_is_rejected(monkeypatch, provider):
    monkeypatch.setenv("LLM_PROVIDER", provider)
    with pytest.raises(ValueError, match="LLM_PROVIDER"):
        get_llm_settings()


@pytest.mark.parametrize("base_url", [
    "", "localhost:11434", "ftp://localhost", "http://",
    "http://localhost?query=1", "http://localhost#fragment",
])
def test_invalid_ollama_base_url_is_rejected(monkeypatch, base_url):
    monkeypatch.setenv("OLLAMA_BASE_URL", base_url)
    with pytest.raises(ValueError, match="OLLAMA_BASE_URL"):
        get_llm_settings()


@pytest.mark.parametrize("timeout", ["0", "-1", "nan", "inf", "-inf", "", "slow"])
def test_invalid_timeout_is_rejected(monkeypatch, timeout):
    monkeypatch.setenv("OLLAMA_TIMEOUT_SECONDS", timeout)
    with pytest.raises(ValueError, match="OLLAMA_TIMEOUT_SECONDS"):
        get_llm_settings()


def test_blank_planner_model_is_rejected(monkeypatch):
    monkeypatch.setenv("OLLAMA_PLANNER_MODEL", "   ")
    with pytest.raises(ValueError, match="OLLAMA_PLANNER_MODEL"):
        get_llm_settings()
