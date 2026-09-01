import requests

from app.runtime.planner import plan
from app.runtime.executor import execute_tool
from app.runtime.execution_plan import execution_plan_from_task
from app.database import SessionLocal
from app.services.execution_trace import TraceEvent, trace_event

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
    conversation_history: str = "",
    execution_id: int | None = None,
    allowed_tools: list[str] | None = None,
) -> str:
    """
    Agent runtime entry point.

    Flow:
        current user input
            -> planner
            -> optional tool execution
            -> combine memory + conversation history
            -> LLM
            -> final response

    When execution_id is provided, runtime trace events are persisted.
    """

    def trace(event: TraceEvent, message: str):
        if execution_id is None:
            return

        db = SessionLocal()

        try:
            trace_event(
                db,
                execution_id,
                event,
                message,
            )
        finally:
            db.close()

    # ---------------------------------------------------------
    # 1. Planner
    # ---------------------------------------------------------

    task = plan(
        user_input,
        allowed_tools=allowed_tools,
    )

    execution_plan = execution_plan_from_task(
        task,
        user_input=user_input,
    )

    step = execution_plan.steps[0]

    tool_name = step.tool
    tool_arguments = step.arguments

    trace(
        TraceEvent.PLANNER_DECISION,
        f"tool={tool_name or 'none'}",
    )

    # ---------------------------------------------------------
    # 2. Optional tool execution
    # ---------------------------------------------------------

    tool_result = ""

    if tool_name:
        trace(
            TraceEvent.TOOL_CALLED,
            f"tool={tool_name}",
        )

        tool_result = execute_tool(
            tool_name,
            tool_arguments,
            allowed_tools=allowed_tools,
        )

        trace(
            TraceEvent.TOOL_RESULT,
            f"tool={tool_name}; result={tool_result}",
        )

        # Calculator output is deterministic,
        # so it can be returned directly.
        if tool_name == "calculator":
            return str(tool_result)

    # ---------------------------------------------------------
    # 3. Build final LLM prompt
    # ---------------------------------------------------------

    prompt = f"""
你是一个 AI Agent。

长期记忆：
{memory_text or "无"}

当前会话历史：
{conversation_history or "无"}

当前用户输入：
{user_input}

工具执行结果：
{tool_result or "无"}

重要规则：

1. 当前会话历史用于理解上下文和多轮对话。
2. 当前用户输入是你现在必须回答的问题。
3. 如果工具执行结果存在，必须使用工具结果。
4. 不允许重新计算或修改工具返回的数据。
5. 不要把历史对话中的旧问题误认为当前问题。
6. 回答应结合历史上下文，但优先响应当前用户输入。

请回答用户。
"""

    # ---------------------------------------------------------
    # 4. LLM
    # ---------------------------------------------------------

    trace(
        TraceEvent.LLM_CALLED,
        f"model={model}",
    )

    result = call_llm(
        model,
        prompt,
    )

    trace(
        TraceEvent.LLM_COMPLETED,
        f"model={model}",
    )

    return result
