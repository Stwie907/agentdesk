from app.runtime.planner import plan
from app.runtime.executor import execute_tool


def run_agent(
    model: str,
    prompt: str
):

    # 1. planner 决策
    decision = plan(prompt)


    # 2. 判断是否需要工具
    tool = decision.get("tool")
    tool_input = decision.get("input")


    # 3. 执行工具
    if tool:

        result = execute_tool(
            tool,
            tool_input
        )

        return {
            "tool": tool,
            "result": result
        }


    # 4. 普通回答
    return {
        "tool": None,
        "result": decision.get("input")
    }
