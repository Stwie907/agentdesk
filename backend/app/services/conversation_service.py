from sqlalchemy.orm import Session

from app.crud.conversation import get_conversation
from app.crud.message import create_message, get_messages
from app.crud.execution import create_execution

from app.schemas.message import MessageCreate
from app.schemas.execution import ExecutionCreate

from app.workers.execution_worker import execute_agent
from app.services.memory_extractor import extract_memories
from app.services.memory_service import save_agent_memory


def build_conversation_history(
    db: Session,
    conversation_id: int,
) -> str:
    """
    Build ordered conversation history from messages
    that already exist before the current user turn.
    """

    messages = get_messages(
        db,
        conversation_id,
    )

    ordered_messages = sorted(
        messages,
        key=lambda message: (
            message.created_at,
            message.id,
        ),
    )

    history_lines = []

    for message in ordered_messages:
        role = message.role.lower()

        if role == "user":
            speaker = "User"
        elif role == "assistant":
            speaker = "Assistant"
        else:
            speaker = role.capitalize()

        history_lines.append(
            f"{speaker}: {message.content}"
        )

    return "\n".join(history_lines)


def run_conversation_chat(
    db: Session,
    conversation_id: int,
    user_input: str,
):
    """
    Run one complete conversation turn.

    Flow:
        load previous conversation history
            -> save current user message
            -> create execution
            -> run agent with history
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

    # 2. Load PREVIOUS conversation history
    # before saving the current user message.
    conversation_history = build_conversation_history(
        db,
        conversation_id,
    )

    # 3. Save current user message
    create_message(
        db,
        conversation_id,
        MessageCreate(
            role="user",
            content=user_input,
        ),
    )

    # Extract long-term memories from the current user message.
    extracted_memories = extract_memories(user_input)

    for memory_content in extracted_memories:
        save_agent_memory(
            db,
            conversation.agent_id,
            memory_content,
        )

    # 4. Create execution for this conversation's agent
    execution = create_execution(
        db,
        ExecutionCreate(
            agent_id=conversation.agent_id,
            input=user_input,
        ),
    )

    # 5. Run Agent Runtime with conversation history
    execute_agent(
        execution.id,
        conversation_history,
    )

    # 6. Reload because worker uses another DB session
    db.refresh(execution)

    # 7. Save assistant response
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
