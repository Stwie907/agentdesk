import requests

from app.runtime.planner import plan
from app.runtime.executor import execute_tool


OLLAMA_URL = "http://localhost:11434/api/generate"


def call_llm(model: str, prompt: str) -> str:
    response = requests.post(
        OLLAMA_URL,
        json={
            "model": model,
            "prompt": prompt,
            "stream": False,
        },
        timeout=120,
    )

    response.raise_for_status()

    data = response.json()

    return data["response"]


def run_agent(
    model: str,
    user_input: str,
    memory_text: str = "",
) -> str:
    """
    Agent runtime entry point.

    Flow:
        user input
            -> planner
            -> optional tool execution
            -> LLM
            -> final response
    """

    task = plan(user_input)

    tool_name = task.get("tool")
    tool_input = task.get("input", user_input)

    tool_result = ""

    if tool_name:
        tool_result = execute_tool(
            tool_name,
            tool_input,
        )

        # Calculator results are deterministic and can be returned directly.
        if tool_name == "calculator":
            return str(tool_result)

    prompt = f"""
你是一个 AI Agent。

历史记忆：
{memory_text}

用户输入：
{user_input}

工具执行结果：
{tool_result}

重要规则：

1. 如果工具执行结果存在，必须直接使用工具结果。
2. 不允许重新计算。
3. 不允许修改工具返回的数据。
4. 工具结果就是最终事实。

请根据以上信息回答用户。
"""

    return call_llm(
        model,
        prompt,
    )
