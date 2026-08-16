from app.tools.registry import get_tool

from app.database import SessionLocal
from app.models.execution import Execution
from app.models.execution_log import ExecutionLog


def execute_tool(tool_name: str, input: str):

    db = SessionLocal()

    execution = Execution(
        agent_id=1,
        input=input,
        status="running"
    )

    db.add(execution)
    db.commit()
    db.refresh(execution)

    try:

        tool = get_tool(tool_name)

        if not tool:
            result = "Tool not found"

            execution.status = "failed"

        else:
            result = tool.run(input)

            execution.status = "completed"


        log = ExecutionLog(
            execution_id=execution.id,
            level="info",
            message=str(result)
        )

        db.add(log)

        db.commit()


        return result


    except Exception as e:

        execution.status = "failed"

        log = ExecutionLog(
            execution_id=execution.id,
            level="error",
            message=str(e)
        )

        db.add(log)

        db.commit()

        return str(e)


    finally:

        db.close()
