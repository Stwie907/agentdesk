import os
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.models.conversation import Conversation
from app.models.execution import Execution
from app.models.execution_log import ExecutionLog
from app.models.execution_snapshot import ExecutionSnapshot
from app.models.memory import Memory
from app.models.message import Message
from app.models.user_memory import UserMemory
from app.seed_demo import seed_demo


BACKEND_DIR = Path(__file__).resolve().parents[1]
ALEMBIC_INI_PATH = BACKEND_DIR / "alembic.ini"

EXPECTED_HEAD_TABLES = {
    "alembic_version",
    "users",
    "projects",
    "agents",
    "executions",
    "execution_logs",
    "conversations",
    "messages",
    "memories",
    "user_memories",
    "execution_snapshots",
}

EXPECTED_EXECUTION_COLUMNS = {
    "id",
    "agent_id",
    "input",
    "output",
    "status",
    "created_at",
    "retry_count",
    "failure_type",
    "failure_message",
    "replay_of_execution_id",
}

EXPECTED_SNAPSHOT_COLUMNS = {
    "id",
    "execution_id",
    "snapshot_version",
    "input_snapshot",
    "plan_snapshot",
    "output_snapshot",
    "created_at",
}


def run_alembic(
    *args: str,
    database_url: str,
) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["DATABASE_URL"] = database_url

    return subprocess.run(
        [
            sys.executable,
            "-m",
            "alembic",
            "-c",
            str(ALEMBIC_INI_PATH),
            *args,
        ],
        cwd=BACKEND_DIR,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )


def assert_alembic_succeeded(
    result: subprocess.CompletedProcess[str],
    command: str,
) -> None:
    assert result.returncode == 0, (
        f"Alembic {command} failed.\n"
        f"stdout:\n{result.stdout}\n"
        f"stderr:\n{result.stderr}"
    )


def get_alembic_head_revision() -> str:
    config = Config(str(ALEMBIC_INI_PATH))
    script = ScriptDirectory.from_config(config)

    head_revision = script.get_current_head()

    assert head_revision is not None

    return head_revision


def get_tables(
    connection: sqlite3.Connection,
) -> set[str]:
    return {
        row[0]
        for row in connection.execute(
            """
            SELECT name
            FROM sqlite_master
            WHERE type = 'table'
            """
        )
    }


def get_table_columns(
    connection: sqlite3.Connection,
    table_name: str,
) -> set[str]:
    return {
        row[1]
        for row in connection.execute(
            f"PRAGMA table_info({table_name})"
        )
    }


def get_table_info(
    connection: sqlite3.Connection,
    table_name: str,
) -> dict[str, tuple]:
    return {
        row[1]: row
        for row in connection.execute(
            f"PRAGMA table_info({table_name})"
        )
    }


def get_foreign_keys(
    connection: sqlite3.Connection,
    table_name: str,
) -> set[tuple[str, str, str]]:
    return {
        (
            row[3],
            row[2],
            row[4],
        )
        for row in connection.execute(
            f"PRAGMA foreign_key_list({table_name})"
        )
    }


def get_index_names(
    connection: sqlite3.Connection,
    table_name: str,
) -> set[str]:
    return {
        row[1]
        for row in connection.execute(
            f"PRAGMA index_list({table_name})"
        )
    }


def assert_database_at_head(
    database_path: Path,
) -> None:
    with sqlite3.connect(database_path) as connection:
        tables = get_tables(connection)

        current_revision = connection.execute(
            "SELECT version_num FROM alembic_version"
        ).fetchone()

        execution_columns = get_table_columns(
            connection,
            "executions",
        )

        snapshot_columns = get_table_columns(
            connection,
            "execution_snapshots",
        )

        execution_foreign_keys = get_foreign_keys(
            connection,
            "executions",
        )

        snapshot_foreign_keys = get_foreign_keys(
            connection,
            "execution_snapshots",
        )

        execution_indexes = get_index_names(
            connection,
            "executions",
        )

        snapshot_indexes = get_index_names(
            connection,
            "execution_snapshots",
        )

        snapshot_table_info = get_table_info(
            connection,
            "execution_snapshots",
        )

    assert current_revision is not None
    assert current_revision[0] == get_alembic_head_revision()

    missing_tables = EXPECTED_HEAD_TABLES - tables

    assert not missing_tables, (
        "Alembic database is missing expected tables: "
        f"{sorted(missing_tables)}"
    )

    missing_execution_columns = (
        EXPECTED_EXECUTION_COLUMNS - execution_columns
    )

    assert not missing_execution_columns, (
        "executions table is missing expected columns: "
        f"{sorted(missing_execution_columns)}"
    )

    missing_snapshot_columns = (
        EXPECTED_SNAPSHOT_COLUMNS - snapshot_columns
    )

    assert not missing_snapshot_columns, (
        "execution_snapshots table is missing expected columns: "
        f"{sorted(missing_snapshot_columns)}"
    )

    assert (
        "replay_of_execution_id",
        "executions",
        "id",
    ) in execution_foreign_keys

    assert (
        "execution_id",
        "executions",
        "id",
    ) in snapshot_foreign_keys

    assert (
        "ix_executions_replay_of_execution_id"
        in execution_indexes
    )

    assert (
        "ix_execution_snapshots_id"
        in snapshot_indexes
    )

    snapshot_version_info = snapshot_table_info[
        "snapshot_version"
    ]

    # PRAGMA table_info:
    # index 3 -> NOT NULL flag
    # index 4 -> default value
    assert snapshot_version_info[3] == 1

    snapshot_version_default = snapshot_version_info[4]

    assert snapshot_version_default is not None
    assert snapshot_version_default.strip("'\"") == "1"

    with sqlite3.connect(database_path) as connection:
        assert get_table_columns(connection, "user_memories") == {"id", "user_id", "content", "content_key", "created_at"}
        assert ("user_id", "users", "id") in get_foreign_keys(connection, "user_memories")
        assert {"ix_user_memories_id", "ix_user_memories_user_id"} <= get_index_names(connection, "user_memories")
        unique_indexes = [row[1] for row in connection.execute("PRAGMA index_list(user_memories)") if row[2]]
        assert any([row[2] for row in connection.execute(f"PRAGMA index_info({name})")] == ["user_id", "content_key"] for name in unique_indexes)


def assert_database_at_base(
    database_path: Path,
) -> None:
    with sqlite3.connect(database_path) as connection:
        tables = get_tables(connection)

        current_revision = connection.execute(
            "SELECT version_num FROM alembic_version"
        ).fetchone()

    application_tables = EXPECTED_HEAD_TABLES - {
        "alembic_version"
    }

    remaining_application_tables = (
        application_tables & tables
    )

    assert not remaining_application_tables, (
        "Application tables remain after Alembic downgrade base: "
        f"{sorted(remaining_application_tables)}"
    )

    assert "alembic_version" in tables
    assert current_revision is None


def test_alembic_migration_lifecycle_from_fresh_database(
    tmp_path,
):
    database_path = tmp_path / "alembic_lifecycle.db"
    database_url = f"sqlite:///{database_path.as_posix()}"

    first_upgrade = run_alembic(
        "upgrade",
        "head",
        database_url=database_url,
    )

    assert_alembic_succeeded(
        first_upgrade,
        "upgrade head",
    )

    assert database_path.exists()
    assert_database_at_head(database_path)

    downgrade = run_alembic("downgrade", "base", database_url=database_url)
    assert_alembic_succeeded(downgrade, "downgrade base")
    assert_database_at_base(database_path)
    second_upgrade = run_alembic("upgrade", "head", database_url=database_url)
    assert_alembic_succeeded(second_upgrade, "second upgrade head")
    assert_database_at_head(database_path)


def previous_database(path):
    url = f"sqlite:///{path.as_posix()}"
    assert_alembic_succeeded(run_alembic("upgrade", "d09aa76d1cdb", database_url=url), "upgrade previous head")
    engine = create_engine(url)
    with Session(engine) as db:
        ids = seed_demo(db)
        db.add(Memory(agent_id=ids["agent_id"], content="Keep original Agent memory"))
        conversation = Conversation(agent_id=ids["agent_id"], title="Keep original conversation")
        execution = Execution(agent_id=ids["agent_id"], input="Hello", output="[MOCK] Hello", status="completed")
        db.add_all([conversation, execution]); db.flush()
        db.add_all([Message(conversation_id=conversation.id, role="user", content="Keep original message"),
                    ExecutionLog(execution_id=execution.id, level="info", message="Keep original log"),
                    ExecutionSnapshot(execution_id=execution.id, input_snapshot="Hello", plan_snapshot="{}", output_snapshot="[MOCK] Hello")])
        db.commit()
    engine.dispose()
    return url, ids


def original_rows(path):
    tables = sorted(EXPECTED_HEAD_TABLES - {"user_memories", "alembic_version"})
    with sqlite3.connect(path) as connection:
        return {table: connection.execute(f"SELECT * FROM {table} ORDER BY id").fetchall() for table in tables}


def test_additive_upgrade_and_scoped_downgrade_preserve_all_existing_data(tmp_path):
    path = tmp_path / "existing.db"
    url, ids = previous_database(path)
    before = original_rows(path)
    assert all(before.values()), "Fixture should cover every existing application table"
    assert_alembic_succeeded(run_alembic("upgrade", "head", database_url=url), "upgrade shared memories")
    assert_database_at_head(path)
    assert original_rows(path) == before
    engine = create_engine(url)
    with Session(engine) as db:
        db.add(UserMemory(user_id=ids["user_id"], content="Shared", content_key="key"))
        db.commit()
    engine.dispose()
    assert_alembic_succeeded(run_alembic("downgrade", "d09aa76d1cdb", database_url=url), "downgrade only shared memories")
    assert original_rows(path) == before
    with sqlite3.connect(path) as connection:
        assert "user_memories" not in get_tables(connection)
    assert_alembic_succeeded(run_alembic("upgrade", "head", database_url=url), "re-upgrade shared memories")
    assert_database_at_head(path)
    assert original_rows(path) == before


def test_migration_adopts_runtime_created_table_preserving_rows_and_repairing_indexes(tmp_path):
    path = tmp_path / "runtime-created.db"
    url, ids = previous_database(path)
    engine = create_engine(url)
    UserMemory.__table__.create(engine)
    with Session(engine) as db:
        db.add(UserMemory(user_id=ids["user_id"], content="Keep shared record", content_key="shared-key"))
        db.commit()
    engine.dispose()
    before = original_rows(path)
    with sqlite3.connect(path) as connection:
        shared = connection.execute("SELECT * FROM user_memories").fetchall()
        connection.execute("DROP INDEX ix_user_memories_user_id")
    assert_alembic_succeeded(run_alembic("upgrade", "head", database_url=url), "adopt runtime table")
    assert_database_at_head(path)
    assert original_rows(path) == before
    with sqlite3.connect(path) as connection:
        assert connection.execute("SELECT * FROM user_memories").fetchall() == shared


@pytest.mark.parametrize("drift", ["column", "foreign_key", "duplicate_constraint", "index"])
def test_migration_rejects_schema_drift_without_changing_existing_data(tmp_path, drift):
    path = tmp_path / f"drift-{drift}.db"
    url, _ = previous_database(path)
    engine = create_engine(url)
    if drift == "index":
        UserMemory.__table__.create(engine)
        with sqlite3.connect(path) as connection:
            connection.execute("DROP INDEX ix_user_memories_user_id")
            connection.execute("CREATE INDEX ix_user_memories_user_id ON user_memories (content)")
    else:
        key_type = "VARCHAR(63)" if drift == "column" else "VARCHAR(64)"
        foreign_key = "REFERENCES users(id)" if drift != "foreign_key" else ""
        unique = ", UNIQUE(user_id, content_key)" if drift != "duplicate_constraint" else ""
        with sqlite3.connect(path) as connection:
            connection.execute(f"CREATE TABLE user_memories (id INTEGER NOT NULL PRIMARY KEY, user_id INTEGER NOT NULL {foreign_key}, content TEXT NOT NULL, content_key {key_type} NOT NULL, created_at DATETIME NOT NULL{unique})")
    engine.dispose()
    before = original_rows(path)
    result = run_alembic("upgrade", "head", database_url=url)
    assert result.returncode != 0 and "Existing user_memories" in result.stderr
    assert original_rows(path) == before
    with sqlite3.connect(path) as connection:
        assert connection.execute("SELECT version_num FROM alembic_version").fetchone()[0] == "d09aa76d1cdb"
