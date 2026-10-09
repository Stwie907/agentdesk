"""Persist retrieval evidence in existing execution logs; never rerun retrieval."""

from sqlalchemy.orm import Session

from app.models.execution import Execution
from app.models.execution_log import ExecutionLog
from app.schemas.memory_evidence import MemoryEvidence
from app.services.execution_trace import TraceEvent, trace_event


class InvalidMemoryEvidence(ValueError):
    pass


def _check_execution(execution: Execution, evidence: MemoryEvidence):
    if evidence.agent_id != execution.agent_id or evidence.query != execution.input.strip():
        raise InvalidMemoryEvidence("Persisted memory evidence does not match this execution")


def save_memory_evidence(db: Session, execution: Execution, evidence: MemoryEvidence):
    _check_execution(execution, evidence)
    return trace_event(db, execution.id, TraceEvent.MEMORY_RETRIEVAL_DETAILS,
                       detail=evidence.model_dump_json())


def read_memory_evidence(db: Session, execution: Execution) -> MemoryEvidence | None:
    # The newest worker attempt owns the evidence. A corrupt newest record must
    # not silently reveal an older attempt or a fresh ranking of current rows.
    prefix = TraceEvent.MEMORY_RETRIEVAL_DETAILS.value
    log = db.query(ExecutionLog).filter(
        ExecutionLog.execution_id == execution.id,
        ExecutionLog.message.startswith(prefix, autoescape=True),
    ).order_by(ExecutionLog.id.desc()).first()
    if log is None:
        return None
    try:
        if not log.message.startswith(prefix + ": "):
            raise ValueError("Malformed evidence log")
        evidence = MemoryEvidence.model_validate_json(log.message[len(prefix) + 2:])
        _check_execution(execution, evidence)
        return evidence
    except (ValueError, TypeError) as error:
        raise InvalidMemoryEvidence("Persisted memory evidence is invalid; it cannot be reconstructed from current memories") from error
