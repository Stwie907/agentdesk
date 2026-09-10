import os
import sqlite3
import subprocess
import sys
from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory


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

    downgrade = run_alembic(
        "downgrade",
        "base",
        database_url=database_url,
    )

    assert_alembic_succeeded(
        downgrade,
        "downgrade base",
    )

    assert_database_at_base(database_path)

    second_upgrade = run_alembic(
        "upgrade",
        "head",
        database_url=database_url,
    )

    assert_alembic_succeeded(
        second_upgrade,
        "second upgrade head",
    )

    assert_database_at_head(database_path)
