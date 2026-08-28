from app.models.execution import Execution
from app.schemas.execution import ExecutionRead


def test_execution_model_has_retry_count():
    assert hasattr(Execution, "retry_count")


def test_execution_model_has_failure_type():
    assert hasattr(Execution, "failure_type")


def test_execution_model_has_failure_message():
    assert hasattr(Execution, "failure_message")


def test_execution_read_exposes_retry_count():
    assert "retry_count" in ExecutionRead.model_fields


def test_execution_read_exposes_failure_type():
    assert "failure_type" in ExecutionRead.model_fields


def test_execution_read_exposes_failure_message():
    assert "failure_message" in ExecutionRead.model_fields
