import json
import requests


OLLAMA_URL = "http://localhost:11434/api/generate"


def plan(user_input: str):

    prompt = f"""
你是一个任务规划器。

你需要判断用户是否需要调用工具。

目前只有一个工具：

calculator:
用于数学计算。

如果需要计算，返回：

{{
    "tool": "calculator",
    "input": "数学表达式"
}}

如果不需要工具，返回：

{{
    "tool": null,
    "input": "{user_input}"
}}

规则：
1. 只返回JSON
2. 不要解释


用户输入：

{user_input}
"""


    response = requests.post(
        OLLAMA_URL,
        json={
            "model": "qwen2.5:7b",
            "prompt": prompt,
            "stream": False
        }
    )


    text = response.json()["response"]


    try:
        return json.loads(text)

    except Exception:

        return {
            "tool": None,
            "input": user_input
        }
