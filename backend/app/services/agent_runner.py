import requests

from app.runtime.planner import plan
from app.runtime.plan_executor import execute_plan
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

    tool_names = [
        step.tool
        for step in execution_plan.steps
        if step.tool is not None
    ]

    if len(tool_names) == 0:
        planner_trace_message = "tool=none"
    elif len(tool_names) == 1:
        planner_trace_message = f"tool={tool_names[0]}"
    else:
        planner_trace_message = f"tools={tool_names}"

    trace(
        TraceEvent.PLANNER_DECISION,
        planner_trace_message,
    )

    for tool_name in tool_names:
        trace(
            TraceEvent.TOOL_CALLED,
            f"tool={tool_name}",
        )

    plan_result = execute_plan(
        execution_plan,
        allowed_tools=allowed_tools,
    )

    for step_result in plan_result.steps:
        if step_result.step.tool is not None:
            trace(
                TraceEvent.TOOL_RESULT,
                f"tool={step_result.step.tool}; result={step_result.output}",
            )

    tool_result = plan_result.last_output

    # Calculator output is deterministic,
    # so it can be returned directly.
    if (
        len(execution_plan.steps) == 1
        and execution_plan.steps[0].tool == "calculator"
    ):
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
