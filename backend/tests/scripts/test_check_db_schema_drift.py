import os
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
SCRIPT = ROOT / "scripts" / "check-db-schema-drift.sh"


def _fake_supabase(tmp_path: Path, output: str = "No schema changes found\n") -> dict[str, str]:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    calls_file = tmp_path / "supabase-calls.txt"
    fake = bin_dir / "supabase"
    fake.write_text(
        "\n".join(
            [
                "#!/usr/bin/env bash",
                'printf \'%s\\n\' "$*" >> "$SUPABASE_CALLS_FILE"',
                'if [[ -n "${SUPABASE_FAKE_STDERR:-}" ]]; then',
                "  printf '%s' \"$SUPABASE_FAKE_STDERR\" >&2",
                "fi",
                'if [[ "$1 $2" == "db diff" ]]; then',
                "  printf '%s' \"$SUPABASE_FAKE_OUTPUT\"",
                "fi",
                'exit "${SUPABASE_FAKE_EXIT:-0}"',
            ]
        ),
        encoding="utf-8",
    )
    fake.chmod(0o755)
    return {
        "PATH": f"{bin_dir}{os.pathsep}{os.environ['PATH']}",
        "SUPABASE_CALLS_FILE": str(calls_file),
        "SUPABASE_FAKE_OUTPUT": output,
    }


def _run(tmp_path: Path, env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    full_env = os.environ.copy()
    for name in (
        "SUPABASE_DB_URI",
        "SUPABASE_DB_URL",
        "SUPABASE_ACCESS_TOKEN",
        "SUPABASE_PROJECT_ID",
        "SUPABASE_DB_PASSWORD",
    ):
        full_env.pop(name, None)
    full_env.update(env)
    return subprocess.run(
        ["bash", str(SCRIPT)],
        cwd=ROOT,
        env=full_env,
        text=True,
        capture_output=True,
        check=False,
    )


def test_requires_db_url_or_legacy_supabase_credentials(tmp_path: Path) -> None:
    result = _run(tmp_path, _fake_supabase(tmp_path))

    assert result.returncode == 2
    assert "SUPABASE_DB_URI" in result.stderr
    assert "SUPABASE_ACCESS_TOKEN" in result.stderr


def test_uses_direct_db_uri_to_diff_migrations_against_remote(tmp_path: Path) -> None:
    env = _fake_supabase(tmp_path)
    env["SUPABASE_DB_URI"] = "postgresql://postgres:p!ss@example.supabase.co:5432/postgres"

    result = _run(tmp_path, env)

    assert result.returncode == 0, result.stderr
    calls = Path(env["SUPABASE_CALLS_FILE"]).read_text(encoding="utf-8")
    assert (
        "db diff --from migrations --to "
        "postgresql://postgres:p%21ss@example.supabase.co:5432/postgres --schema public"
    ) in calls
    assert "No Supabase schema drift detected." in result.stdout


def test_reports_schema_drift_when_direct_diff_outputs_sql(tmp_path: Path) -> None:
    env = _fake_supabase(tmp_path, output="create table public.example(id bigint);\n")
    env["SUPABASE_DB_URI"] = "postgresql://postgres:secret@example.supabase.co:5432/postgres"

    result = _run(tmp_path, env)

    assert result.returncode == 1
    assert "create table public.example" in result.stdout
    assert "Supabase schema drift detected" in result.stderr


def test_redacts_normalized_db_uri_from_supabase_errors(tmp_path: Path) -> None:
    env = _fake_supabase(tmp_path)
    env["SUPABASE_DB_URI"] = "postgresql://postgres:p!ss@example.supabase.co:5432/postgres"
    env["SUPABASE_FAKE_EXIT"] = "1"
    env["SUPABASE_FAKE_STDERR"] = (
        "failed to connect to postgresql://postgres:p%21ss@example.supabase.co:5432/postgres"
    )

    result = _run(tmp_path, env)

    assert result.returncode == 2
    assert "p!ss" not in result.stderr
    assert "p%21ss" not in result.stderr
    assert "<redacted>" in result.stderr


def test_keeps_legacy_linked_project_flow(tmp_path: Path) -> None:
    env = _fake_supabase(tmp_path)
    env.update(
        {
            "SUPABASE_ACCESS_TOKEN": "token",
            "SUPABASE_PROJECT_ID": "project-ref",
            "SUPABASE_DB_PASSWORD": "password",
        }
    )

    result = _run(tmp_path, env)

    assert result.returncode == 0, result.stderr
    calls = Path(env["SUPABASE_CALLS_FILE"]).read_text(encoding="utf-8")
    assert "link --project-ref project-ref --password password" in calls
    assert "db diff --linked --schema public" in calls
