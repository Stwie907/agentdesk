import json

import requests

from app.tools.registry import get_tool_metadata, list_tool_metadata

OLLAMA_URL = "http://localhost:11434/api/generate"

def normalize_allowed_tools(
    allowed_tools: list[str] | None,
) -> list[str]:
    """
    Normalize the tools visible to the planner.

    None keeps backward compatibility and means all currently
    registered tools are available.
    """

    registered_names = [
        metadata["name"]
        for metadata in list_tool_metadata()
    ]

    if allowed_tools is None:
        return registered_names

    normalized = []

    for tool_name in allowed_tools:
        if (
            tool_name in registered_names
            and tool_name not in normalized
        ):
            normalized.append(tool_name)

    return normalized


def build_tools_prompt(
    allowed_tools: list[str],
) -> str:
    """
    Build the tool section shown to the LLM dynamically
    from Tool Registry metadata.
    """

    if not allowed_tools:
        return "当前 Agent 没有任何可用工具。"

    sections = []

    for index, tool_name in enumerate(allowed_tools, start=1):
        metadata = get_tool_metadata(tool_name)

        if metadata is None:
            continue

        input_schema = json.dumps(
            metadata["input_schema"],
            ensure_ascii=False,
        )

        sections.append(
            f"""
{index}. {metadata["name"]}
用途: {metadata["description"]}
输入格式: {input_schema}
返回:
{{
    "tool": "{metadata["name"]}",
    "input": "<tool input>"
}}
""".strip()
        )

    if not sections:
        return "当前 Agent 没有任何可用工具。"

    return "\n\n".join(sections)

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
            "arguments": {},
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
            "arguments": {},
            "input": user_input,
        }

    tool_name = result.get("tool")

    # Planner-side safety check.
    # The Executor remains the final hard security boundary.
    if tool_name is not None and tool_name not in available_tools:
        return {
            "tool": None,
            "arguments": {},
            "input": user_input,
        }

    arguments = result.get("arguments")

    # New structured contract.
    if isinstance(arguments, dict):
        return {
            "tool": tool_name,
            "arguments": arguments,
            "input": result.get(
                "input",
                user_input,
            ),
        }

    # Backward compatibility with the legacy Planner contract.
    legacy_input = result.get(
        "input",
        user_input,
    )

    if tool_name == "calculator":
        arguments = {
            "expression": legacy_input,
        }
    elif tool_name == "datetime":
        arguments = {}
    else:
        arguments = {}

    return {
        "tool": tool_name,
        "arguments": arguments,
        "input": legacy_input,
    }
