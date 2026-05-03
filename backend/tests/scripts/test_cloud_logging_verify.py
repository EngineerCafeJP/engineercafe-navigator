import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
SCRIPT = ROOT / "scripts" / "cloud-logging-verify.sh"
SINCE = "2026-05-03T00:00:00Z"
UNTIL = "2026-05-03T00:05:00Z"


def _write_json(input_dir: Path, name: str, rows: list[dict]) -> None:
    (input_dir / f"{name}.json").write_text(json.dumps(rows), encoding="utf-8")


def _run_error_gate(
    input_dir: Path, output_dir: Path, timestamp: str
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            "bash",
            str(SCRIPT),
            "--input-dir",
            str(input_dir),
            "--output-dir",
            str(output_dir),
            "--timestamp",
            timestamp,
            "--since",
            SINCE,
            "--until",
            UNTIL,
            "--error-gate-only",
        ],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )


def test_error_gate_fails_on_chat_api_5xx(tmp_path: Path) -> None:
    input_dir = tmp_path / "logs"
    output_dir = tmp_path / "reports"
    input_dir.mkdir()

    _write_json(
        input_dir,
        "chat_api_5xx",
        [
            {
                "timestamp": "2026-05-03T00:01:00Z",
                "severity": "WARNING",
                "httpRequest": {
                    "requestMethod": "POST",
                    "requestUrl": "https://service.example/api/chat",
                    "status": 500,
                },
                "jsonPayload": {"message": "request_completed_slow"},
            }
        ],
    )

    result = _run_error_gate(input_dir, output_dir, "chat-5xx")

    assert result.returncode == 1
    report = (output_dir / "cloud-logging-check-chat-5xx.md").read_text(encoding="utf-8")
    assert "- 1 /api/chat 5xx log row(s) found." in report
    assert "| `/api/chat` 5xx rows | FAIL | 1 matching log row(s) |" in report


def test_error_gate_fails_on_ltm_store_write_failed(tmp_path: Path) -> None:
    input_dir = tmp_path / "logs"
    output_dir = tmp_path / "reports"
    input_dir.mkdir()

    _write_json(
        input_dir,
        "chat_response",
        [
            {
                "timestamp": "2026-05-03T00:02:00Z",
                "jsonPayload": {
                    "event": "chat_response",
                    "request_id": "req-alpha-d",
                    "language": "ja",
                    "route": "general_knowledge",
                    "rag_fallback": False,
                    "ltm_store_write": "failed",
                    "latency_ms": 1234,
                },
            }
        ],
    )

    result = _run_error_gate(input_dir, output_dir, "ltm-failed")

    assert result.returncode == 1
    report = (output_dir / "cloud-logging-check-ltm-failed.md").read_text(encoding="utf-8")
    assert "- 1 chat_response log(s) reported ltm_store_write=failed." in report
    assert (
        "| `ltm_store_write=failed` rows | FAIL | 1 matching chat_response log row(s) |" in report
    )


def test_error_gate_passes_without_chat_or_persistence_errors(tmp_path: Path) -> None:
    input_dir = tmp_path / "logs"
    output_dir = tmp_path / "reports"
    input_dir.mkdir()

    _write_json(
        input_dir,
        "chat_response",
        [
            {
                "timestamp": "2026-05-03T00:03:00Z",
                "jsonPayload": {
                    "event": "chat_response",
                    "request_id": "req-alpha-d-ok",
                    "language": "ja",
                    "route": "general_knowledge",
                    "rag_fallback": False,
                    "ltm_store_write": "success",
                    "latency_ms": 900,
                },
            }
        ],
    )

    result = _run_error_gate(input_dir, output_dir, "clean")

    assert result.returncode == 0, result.stderr
    report = (output_dir / "cloud-logging-check-clean.md").read_text(encoding="utf-8")
    assert "- Overall passed: yes" in report
    assert "| `/api/chat` 5xx rows | PASS | 0 matching log row(s) |" in report
