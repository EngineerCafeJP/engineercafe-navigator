import subprocess
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[3]
SCRIPT = ROOT_DIR / "scripts" / "alpha-smoke-comprehensive.sh"
RAG_API_SCRIPT = ROOT_DIR / "scripts" / "rag-api-live-test.sh"
ALPHA_WORKFLOW = ROOT_DIR / ".github" / "workflows" / "alpha-live-verification.yml"


def test_alpha_smoke_allows_vosk_fallback_by_default() -> None:
    result = subprocess.run(
        [str(SCRIPT), "--dry-run", "--scenarios", "A"],
        check=True,
        cwd=ROOT_DIR,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )

    assert "Require Qwen primary for A STT: 0" in result.stdout


def test_alpha_smoke_keeps_explicit_strict_qwen_option() -> None:
    result = subprocess.run(
        [str(SCRIPT), "--dry-run", "--scenarios", "A", "--require-qwen-primary"],
        check=True,
        cwd=ROOT_DIR,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )

    assert "Require Qwen primary for A STT: 1" in result.stdout


def test_rag_api_live_dry_run_prints_progress_artifact_paths() -> None:
    result = subprocess.run(
        [
            str(RAG_API_SCRIPT),
            "--dry-run",
            "--timestamp",
            "alpha-live-test-c",
            "--case-suite",
            "diagnostic-29",
        ],
        check=True,
        cwd=ROOT_DIR,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )

    assert "Expected progress JSON: " in result.stdout
    assert "live_api_eval_alpha-live-test-c.progress.json" in result.stdout
    assert "Expected progress log: " in result.stdout
    assert "live_api_eval_alpha-live-test-c.progress.log" in result.stdout


def test_alpha_workflow_uploads_ragas_progress_logs() -> None:
    workflow = ALPHA_WORKFLOW.read_text(encoding="utf-8")

    assert "backend/tests/evaluation/reports/*.json" in workflow
    assert "backend/tests/evaluation/reports/*.log" in workflow
