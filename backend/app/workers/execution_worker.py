from app.database import SessionLocal

from app.models.execution import Execution
from app.models.agent import Agent
from app.models.memory import Memory

from app.services.agent_runner import run_agent

from app.crud.execution_log import create_log

from app.runtime.planner import plan
from app.runtime.executor import execute_tool


def execute_agent(execution_id: int):

    db = SessionLocal()


    execution = (
        db.query(Execution)
        .filter(
            Execution.id == execution_id
        )
        .first()
    )


    if not execution:
        db.close()
        return


    execution.status = "running"
    db.commit()


    create_log(
        db,
        execution.id,
        "Execution started"
    )


    agent = (
        db.query(Agent)
        .filter(
            Agent.id == execution.agent_id
        )
        .first()
    )


    if not agent:

        execution.status = "failed"
        execution.output = "Agent not found"

        db.commit()
        db.close()

        return



    try:

        create_log(
            db,
            execution.id,
            "Loading memory"
        )


        memories = (
            db.query(Memory)
            .filter(
                Memory.agent_id == agent.id
            )
            .all()
        )


        memory_text = "\n".join(
            [
                m.content
                for m in memories
            ]
        )


        create_log(
            db,
            execution.id,
            "Planning task"
        )


        task = plan(
            execution.input
        )


        tool_result = ""


        if task["tool"]:

            create_log(
            db,
            execution.id,
            f"Using tool {task['tool']}"
        )

        tool_result = execute_tool(
            task["tool"],
            task["input"]
        )


        if task["tool"] == "calculator":

            execution.output = tool_result
            execution.status = "completed"

            create_log(
                db,
                execution.id,
                "Tool result returned directly"
            )

            db.commit()
            db.close()

            return

        prompt = f"""
你是一个AI Agent。

历史记忆:
{memory_text}


用户输入:
{execution.input}


工具结果:
{tool_result}


重要规则：

1. 如果工具执行结果存在，必须直接使用工具结果。
2. 不允许重新计算。
3. 不允许修改工具返回的数据。
4. 工具结果就是最终事实。


请根据以上信息回答用户。
"""


        create_log(
            db,
            execution.id,
            "Calling Ollama"
        )


        result = run_agent(
            agent.model,
            prompt
        )


        execution.output = result

        execution.status = "completed"


        create_log(
            db,
            execution.id,
            "Execution completed"
        )



    except Exception as e:


        execution.output = str(e)

        execution.status = "failed"


        create_log(
            db,
            execution.id,
            str(e)
        )



    finally:

        db.commit()

        db.close()
