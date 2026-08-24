from sqlalchemy.orm import Session

from app.crud.conversation import get_conversation
from app.crud.message import create_message
from app.crud.execution import create_execution

from app.schemas.message import MessageCreate
from app.schemas.execution import ExecutionCreate

from app.workers.execution_worker import execute_agent


def run_conversation_chat(
    db: Session,
    conversation_id: int,
    user_input: str,
):
    """
    Run one complete conversation turn.

    Flow:
        conversation
            -> save user message
            -> create execution
            -> run agent
            -> save assistant message
            -> return execution
    """

    # 1. Find conversation
    conversation = get_conversation(
        db,
        conversation_id,
    )

    if not conversation:
        return None

    # 2. Save user message
    create_message(
        db,
        conversation_id,
        MessageCreate(
            role="user",
            content=user_input,
        ),
    )

    # 3. Create execution for the conversation's agent
    execution = create_execution(
        db,
        ExecutionCreate(
            agent_id=conversation.agent_id,
            input=user_input,
        ),
    )

    # 4. Run Agent Runtime
    execute_agent(execution.id)

    # 5. Reload execution because worker uses another DB session
    db.refresh(execution)

    # 6. Save assistant response
    assistant_response = execution.output or ""

    create_message(
        db,
        conversation_id,
        MessageCreate(
            role="assistant",
            content=assistant_response,
        ),
    )

    return execution
