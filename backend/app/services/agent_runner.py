from app.config import get_llm_settings
from app.runtime.plan_executor import execute_plan
from app.runtime.trace_details import step_trace_detail
from app.tools.registry import get_tool
from app.database import SessionLocal
from app.services.execution_trace import TraceEvent, trace_event
from app.runtime.planner import plan_execution
from app.services.llm_provider import generate_text
from app.services.execution_snapshot import (
    persist_execution_plan_snapshot,
    persist_execution_output_snapshot,
)

def call_llm(model: str, prompt: str) -> str:
    return generate_text(model, prompt)


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

    settings = get_llm_settings()
    mock_mode = settings.provider == "mock"

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

    execution_plan = plan_execution(
        user_input,
        allowed_tools=allowed_tools,
    )

    if execution_id is not None:
        db = SessionLocal()

        try:
            persist_execution_plan_snapshot(
                db,
                execution_id,
                user_input,
                execution_plan,
            )
        finally:
            db.close()

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

    trace(
        TraceEvent.PLAN_STARTED,
        "provider=mock; planner=demo_rules" if mock_mode else "",
    )


    def on_step_started(step_index, step):
        trace(
            TraceEvent.STEP_STARTED,
            step_trace_detail(step_index, step),
        )

        if step.tool is not None:
            trace(
                TraceEvent.TOOL_CALLED,
                f"tool={step.tool}",
            )


    def on_step_completed(step_index, step_result):
        step = step_result.step

        if step.tool is not None:
            trace(
                TraceEvent.TOOL_RESULT,
                f"tool={step.tool}; result={step_result.output}",
            )

        trace(
            TraceEvent.STEP_COMPLETED,
            step_trace_detail(step_index, step, step_result.output),
        )

    failed_step = {
        "index": None,
    }


    def on_step_failed(step_index, step, exc):
        failed_step["index"] = step_index

        trace(
            TraceEvent.STEP_FAILED,
            f"{step_trace_detail(step_index, step)}; error={exc}",
        )

    try:
        plan_result = execute_plan(
            execution_plan,
            allowed_tools=allowed_tools,
            on_step_started=on_step_started,
            on_step_completed=on_step_completed,
            on_step_failed=on_step_failed,
        )
    except Exception as exc:
        detail = f"error={exc}"

        if failed_step["index"] is not None:
            detail = f"step={failed_step['index']}; {detail}"

        trace(
            TraceEvent.PLAN_FAILED,
            detail,
        )

        raise

    trace(
        TraceEvent.PLAN_COMPLETED,
        "",
    )

    tool_result = plan_result.last_output

    # Direct-result policy lives on each registered tool so new deterministic
    # tools do not require another Agent-specific branch or an LLM rewrite.
    direct_tool = get_tool(execution_plan.steps[0].tool) if len(execution_plan.steps) == 1 else None
    if (
        direct_tool is not None
        and direct_tool.return_direct
    ):
        final_result = str(tool_result)

        if execution_id is not None:
            db = SessionLocal()

            try:
                persist_execution_output_snapshot(
                    db,
                    execution_id,
                    final_result,
                )
            finally:
                db.close()

        return final_result

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
        f"provider=mock; simulated=true; model={model}" if mock_mode else f"model={model}",
    )

    result = call_llm(
        model,
        prompt,
    )

    trace(
        TraceEvent.LLM_COMPLETED,
        f"provider=mock; simulated=true; model={model}" if mock_mode else f"model={model}",
    )

    if execution_id is not None:
        db = SessionLocal()

        try:
            persist_execution_output_snapshot(
                db,
                execution_id,
                str(result),
            )
        finally:
            db.close()

    return result

def on_step_failed(step_index, step, exc):
    tool_detail = (
        f" tool={step.tool}"
        if step.tool is not None
        else ""
    )

    trace(
        TraceEvent.STEP_FAILED,
        f"step={step_index}{tool_detail}; error={exc}",
    )
