import requests


def run_agent(
    model: str,
    prompt: str
):

    url = "http://localhost:11434/api/generate"

    print("OLLAMA URL:", url)
    print("OLLAMA MODEL:", model)

    response = requests.post(
        url,
        json={
            "model": model,
            "prompt": prompt,
            "stream": False
        },
        timeout=120
    )

    print("OLLAMA STATUS:", response.status_code)
    print("OLLAMA BODY:", response.text[:200])

    response.raise_for_status()

    data = response.json()

    return data["response"]
