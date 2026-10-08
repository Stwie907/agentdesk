"""An isolated SQLite store for idempotent synthetic support tickets."""

from datetime import datetime, timezone
import os
from pathlib import Path
import sqlite3
from typing import Annotated, Literal
from uuid import uuid4

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, field_validator


MAX_PROBLEM_LENGTH = 2000
TICKET_ID_PATTERN = r"^DEMO-TICKET-[a-f0-9]{32}$"


def normalize_problem(value: str) -> str:
    if not isinstance(value, str) or not 1 <= len(value) <= MAX_PROBLEM_LENGTH or not value.strip():
        raise ValueError("problem must be a non-blank string of at most 2000 characters")
    return value.strip()


Problem = Annotated[str, Field(strict=True, min_length=1, max_length=MAX_PROBLEM_LENGTH),
                    AfterValidator(normalize_problem)]


class DemoTicket(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    source: Literal["demo_ticket_store"] = "demo_ticket_store"
    ticket_id: str = Field(pattern=TICKET_ID_PATTERN)
    problem: Problem
    status: Literal["open"]
    created_at: str = Field(pattern=r"^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z$")

    @field_validator("created_at")
    @classmethod
    def valid_utc_timestamp(cls, value: str) -> str:
        datetime.fromisoformat(value.replace("Z", "+00:00"))
        return value


def ticket_db_path() -> Path:
    configured = os.getenv("MCP_TICKET_DB")
    if configured is None:
        return Path(__file__).resolve().parent / "data" / "tickets.db"
    path = Path(configured.strip()).expanduser()
    if not configured.strip() or not path.is_absolute():
        raise ValueError("MCP_TICKET_DB must be an absolute path to a dedicated ticket database")
    return path


class TicketStore:
    def __init__(self, path: Path):
        self.path = path

    def create(self, problem: str) -> DemoTicket:
        # Validate before creating directories or opening the database.
        problem = normalize_problem(problem)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(self.path, timeout=15, isolation_level=None)
        connection.row_factory = sqlite3.Row
        try:
            # Serialize schema setup and lookup/insert across per-call servers.
            connection.execute("BEGIN IMMEDIATE")
            version = connection.execute("PRAGMA user_version").fetchone()[0]
            if version not in (0, 1):
                raise ValueError("Unsupported ticket database schema version")
            tables = {row[0] for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%'"
            )}
            if tables - {"demo_tickets"}:
                raise ValueError("The ticket store requires a dedicated database")
            connection.execute("""
                CREATE TABLE IF NOT EXISTS demo_tickets (
                    ticket_id TEXT PRIMARY KEY NOT NULL,
                    problem TEXT NOT NULL UNIQUE,
                    status TEXT NOT NULL CHECK(status = 'open'),
                    created_at TEXT NOT NULL
                )
            """)
            columns = {row[1] for row in connection.execute("PRAGMA table_info(demo_tickets)")}
            if columns != {"ticket_id", "problem", "status", "created_at"}:
                raise ValueError("The ticket database schema is incompatible")
            connection.execute("PRAGMA user_version = 1")
            row = connection.execute(
                "SELECT ticket_id, problem, status, created_at FROM demo_tickets WHERE problem = ?", (problem,)
            ).fetchone()
            if row is None:
                ticket = DemoTicket(
                    ticket_id="DEMO-TICKET-" + uuid4().hex, problem=problem, status="open",
                    created_at=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                )
                connection.execute(
                    "INSERT INTO demo_tickets(ticket_id, problem, status, created_at) VALUES (?, ?, ?, ?)",
                    (ticket.ticket_id, ticket.problem, ticket.status, ticket.created_at),
                )
            else:
                ticket = DemoTicket.model_validate(dict(row))
            connection.execute("COMMIT")
            return ticket
        except Exception:
            if connection.in_transaction:
                connection.execute("ROLLBACK")
            raise
        finally:
            connection.close()
