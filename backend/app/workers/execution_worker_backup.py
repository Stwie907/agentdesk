from app.database import SessionLocal

from app.models.execution import Execution
from app.models.agent import Agent
from app.models.memory import Memory

from app.services.agent_runner import run_agent

from app.crud.execution_log import create_log


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


        prompt = f"""
你是一个AI Agent。

你的历史记忆：

{memory_text}


用户输入：

{execution.input}


请结合历史记忆回答用户。
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
