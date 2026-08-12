import json
import requests


OLLAMA_URL = "http://localhost:11434/api/generate"


def plan(user_input: str):
    prompt = f"""
你是一个任务规划器。

你的任务是判断用户请求是否需要调用工具。

目前有两个工具：

1. calculator
用途：数学计算。
例如：
用户：计算12345*6789
返回：
{{
    "tool": "calculator",
    "input": "12345*6789"
}}

2. datetime
用途：获取当前日期和时间。
当用户询问现在时间、当前时间、今天日期、今天几号、现在几点等信息时使用。
例如：
用户：现在几点？
返回：
{{
    "tool": "datetime",
    "input": ""
}}

如果用户的问题不需要任何工具，返回：

{{
    "tool": null,
    "input": "{user_input}"
}}

重要规则：

1. 只返回合法 JSON。
2. 不要解释。
3. 不要使用 Markdown。
4. 不要输出 ```json。
5. 数学计算必须使用 calculator。
6. 当前日期或时间问题必须使用 datetime。
7. 不需要工具时 tool 必须为 null。

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
