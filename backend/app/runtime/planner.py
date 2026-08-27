import json

import requests


OLLAMA_URL = "http://localhost:11434/api/generate"

DEFAULT_ALLOWED_TOOLS = [
    "calculator",
    "datetime",
]


TOOL_DESCRIPTIONS = {
    "calculator": """
1. calculator
用途：数学计算。
例如：
用户：计算12345*6789
返回：
{
    "tool": "calculator",
    "input": "12345*6789"
}
""",
    "datetime": """
2. datetime
用途：获取当前日期和时间。
当用户询问现在时间、当前时间、今天日期、今天几号、现在几点等信息时使用。
例如：
用户：现在几点？
返回：
{
    "tool": "datetime",
    "input": ""
}
""",
}


def normalize_allowed_tools(
    allowed_tools: list[str] | None,
) -> list[str]:
    """
    Normalize the tools visible to the planner.

    None keeps backward compatibility and means all currently
    supported tools are available.
    """

    if allowed_tools is None:
        return DEFAULT_ALLOWED_TOOLS.copy()

    normalized = []

    for tool_name in allowed_tools:
        if (
            tool_name in TOOL_DESCRIPTIONS
            and tool_name not in normalized
        ):
            normalized.append(tool_name)

    return normalized


def build_tools_prompt(
    allowed_tools: list[str],
) -> str:
    """
    Build the tool section shown to the LLM.

    The planner should only know about tools that the current
    Agent is allowed to use.
    """

    if not allowed_tools:
        return "当前 Agent 没有任何可用工具。"

    return "\n".join(
        TOOL_DESCRIPTIONS[tool_name]
        for tool_name in allowed_tools
    )


def plan(
    user_input: str,
    allowed_tools: list[str] | None = None,
):
    available_tools = normalize_allowed_tools(
        allowed_tools
    )

    # An Agent with no tool permissions does not need an LLM
    # tool-selection request at all.
    if not available_tools:
        return {
            "tool": None,
            "input": user_input,
        }

    tools_prompt = build_tools_prompt(
        available_tools
    )

    prompt = f"""
你是一个任务规划器。

你的任务是判断用户请求是否需要调用工具。

当前 Agent 只能使用下面列出的工具：

{tools_prompt}

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
5. 只能选择当前 Agent 被允许使用的工具。
6. 如果没有合适的已允许工具，tool 必须为 null。
7. 不允许选择未列出的工具。

用户输入：

{user_input}
"""

    response = requests.post(
        OLLAMA_URL,
        json={
            "model": "qwen2.5:7b",
            "prompt": prompt,
            "stream": False,
        },
    )

    text = response.json()["response"]

    try:
        result = json.loads(text)
    except Exception:
        return {
            "tool": None,
            "input": user_input,
        }

    tool_name = result.get("tool")

    # Planner-side safety check.
    #
    # The Executor remains the final hard security boundary,
    # but the Planner should never intentionally propagate a
    # tool decision outside the Agent's permissions.
    if tool_name is not None and tool_name not in available_tools:
        return {
            "tool": None,
            "input": user_input,
        }

    return {
        "tool": tool_name,
        "input": result.get(
            "input",
            user_input,
        ),
    }
