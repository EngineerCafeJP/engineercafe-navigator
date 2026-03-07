"""Tests for the reception RLS optimization migration."""

from pathlib import Path
import re

MIGRATION_PATH = (
    Path(__file__).resolve().parents[2]
    / "supabase"
    / "migrations"
    / "20260308000002_optimize_reception_rls.sql"
)

EXPECTED_POLICIES = {
    "reception_sessions_service_select",
    "reception_sessions_service_insert",
    "reception_sessions_service_update",
    "reception_sessions_service_delete",
    "visits_service_select",
    "visits_service_insert",
    "visits_service_update",
    "visits_service_delete",
}


def _read_sql() -> str:
    return MIGRATION_PATH.read_text(encoding="utf-8")


def _split_sql_statements(sql: str) -> list[str]:
    statements: list[str] = []
    current: list[str] = []
    in_single_quote = False

    for char in sql:
        if char == "'" and (not current or current[-1] != "\\"):
            in_single_quote = not in_single_quote

        current.append(char)

        if char == ";" and not in_single_quote:
            statement = "".join(current).strip()
            if statement:
                statements.append(statement)
            current = []

    trailing = "".join(current).strip()
    if trailing:
        statements.append(trailing)

    return statements


class TestReceptionRlsMigration:
    def test_sql_file_exists(self) -> None:
        assert MIGRATION_PATH.exists()

    def test_sql_is_syntactically_shaped_like_valid_policy_migration(self) -> None:
        sql = _read_sql()
        statements = _split_sql_statements(sql)

        assert statements, "Migration must contain SQL statements"
        assert sql.strip().endswith(";")
        assert sql.count("(") == sql.count(")")

        create_policy_matches = re.findall(
            r"CREATE POLICY\s+([a-z_]+)\s+ON\s+([a-z_]+)\s+FOR\s+(SELECT|INSERT|UPDATE|DELETE)",
            sql,
        )
        drop_policy_matches = re.findall(
            r"DROP POLICY IF EXISTS\s+(?:\"[^\"]+\"|[a-z_]+)\s+ON\s+([a-z_]+)",
            sql,
        )

        assert len(create_policy_matches) == 8
        assert len(drop_policy_matches) == 10

    def test_contains_all_expected_policy_names(self) -> None:
        sql = _read_sql()

        for policy_name in EXPECTED_POLICIES:
            assert policy_name in sql

    def test_contains_drop_policy_if_exists_statements(self) -> None:
        sql = _read_sql()

        assert 'DROP POLICY IF EXISTS "Service role has full access to reception_sessions"' in sql
        assert 'DROP POLICY IF EXISTS "Service role has full access to visits"' in sql
        assert "DROP POLICY IF EXISTS reception_sessions_service_select" in sql
        assert "DROP POLICY IF EXISTS visits_service_select" in sql
