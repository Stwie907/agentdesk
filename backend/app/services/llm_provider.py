import requests

from app.config import get_llm_settings


MOCK_RESPONSE = (
    "[MOCK] AgentDesk demo response. No language model was called."
)


def generate_text(model: str, prompt: str) -> str:
    """Generate with the selected provider; Ollama failures never select Mock."""
    settings = get_llm_settings()

    if settings.provider == "mock":
        return MOCK_RESPONSE

    try:
        response = requests.post(
            settings.generate_url,
            json={
                "model": model,
                "prompt": prompt,
                "stream": False,
            },
            timeout=settings.timeout_seconds,
        )
        response.raise_for_status()
    except requests.Timeout as error:
        raise TimeoutError(f"Ollama request timed out: {error}") from error
    except requests.ConnectionError as error:
        raise ConnectionError(f"Unable to connect to Ollama: {error}") from error

    try:
        body = response.json()
    except ValueError as error:
        raise RuntimeError("Ollama returned invalid JSON.") from error

    if not isinstance(body, dict) or not isinstance(body.get("response"), str):
        raise RuntimeError("Ollama response must contain a string 'response' field.")

    return body["response"]
