"""Keep MCP arguments and results visible in normal and replay step traces."""

import json

from app.tools.registry import get_tool


MISSING = object()


def step_trace_detail(step_index, step, output=MISSING) -> str:
    detail = f"step={step_index}"
    if step.tool is not None:
        detail += f" tool={step.tool}"
    tool = get_tool(step.tool) if step.tool is not None else None
    if tool is not None and tool.transport == "mcp_stdio":
        arguments = json.dumps(step.arguments, ensure_ascii=False, sort_keys=True, default=str)
        detail += f"; transport=mcp_stdio; arguments={arguments}"
        if output is not MISSING:
            detail += f"; result={output}"
    return detail
