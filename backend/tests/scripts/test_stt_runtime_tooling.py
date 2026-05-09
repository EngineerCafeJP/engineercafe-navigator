import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
PROFILE_SCRIPT = ROOT / "scripts" / "profile_stt.sh"
POSTDEPLOY_SCRIPT = ROOT / "scripts" / "stt-postdeploy-logging-check.sh"
COMPARE_SCRIPT = ROOT / "scripts" / "stt-runtime-compare.sh"


def _entry(event: str, revision: str, **payload: object) -> dict:
    return {
        "timestamp": "2026-05-09T00:00:00Z",
        "resource": {
            "type": "cloud_run_revision",
            "labels": {
                "service_name": "engineer-cafe-backend",
                "location": "asia-northeast1",
                "revision_name": revision,
            },
        },
        "jsonPayload": {"event": event, "stt_trace_id": f"{revision}-trace", **payload},
    }


def test_profile_stt_dry_run_prints_runtime_and_revision_labels() -> None:
    result = subprocess.run(
        [
            str(PROFILE_SCRIPT),
            "--dry-run",
            "--env-label",
            "prod",
            "--runtime-label",
            "pytorch-qwen-cpu",
            "--revision",
            "engineer-cafe-backend-00100-pytorch",
        ],
        check=True,
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )

    assert "Dry run: no API requests or gcloud logging reads will be executed." in result.stdout
    assert "Environment label: prod" in result.stdout
    assert "Runtime label: pytorch-qwen-cpu" in result.stdout
    assert "Revision: engineer-cafe-backend-00100-pytorch" in result.stdout
    assert 'resource.labels.revision_name="engineer-cafe-backend-00100-pytorch"' in result.stdout


def test_postdeploy_logging_check_dry_run_includes_compare_fields() -> None:
    result = subprocess.run(
        [
            str(POSTDEPLOY_SCRIPT),
            "--dry-run",
            "--since",
            "2026-05-09T00:00:00Z",
            "--env-label",
            "prod",
            "--revision",
            "engineer-cafe-backend-00101-onnx",
        ],
        check=True,
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )

    assert "Environment label: prod" in result.stdout
    assert "Revision: engineer-cafe-backend-00101-onnx" in result.stdout
    assert 'jsonPayload.event="stt_qwen_hedge_grace_start"' in result.stdout
    assert 'jsonPayload.event="stt_qwen_hedge_grace_skipped"' in result.stdout


def test_stt_runtime_compare_summarizes_saved_json_without_credentials(tmp_path: Path) -> None:
    baseline_json = tmp_path / "pytorch.json"
    candidate_json = tmp_path / "onnx.json"
    baseline_json.write_text(
        json.dumps(
            [
                _entry(
                    "stt_request_complete",
                    "engineer-cafe-backend-00100-pytorch",
                    stt_request_duration_ms=200,
                ),
                _entry(
                    "stt_qwen_runtime_complete",
                    "engineer-cafe-backend-00100-pytorch",
                    model_name="Qwen/Qwen3-ASR-Flash",
                    model_variant="0.6b-pytorch",
                    device="cpu",
                    stt_qwen_runtime_duration_ms=100,
                    stt_qwen_model_inference_duration_ms=80,
                ),
                _entry(
                    "stt_qwen_postprocess_complete",
                    "engineer-cafe-backend-00100-pytorch",
                    changed=True,
                    deterministic_changed=True,
                    llm_changed=False,
                ),
                _entry(
                    "stt_qwen_hedge_start",
                    "engineer-cafe-backend-00100-pytorch",
                    stt_hedge_wait_duration_ms=25,
                ),
                _entry(
                    "stt_qwen_hedge_grace_complete",
                    "engineer-cafe-backend-00100-pytorch",
                    stt_qwen_grace_wait_duration_ms=30,
                ),
                _entry(
                    "stt_winner",
                    "engineer-cafe-backend-00100-pytorch",
                    stt_winner="qwen",
                    stt_overall_duration_ms=240,
                    stt_qwen_grace_wait_duration_ms=30,
                ),
            ]
        ),
        encoding="utf-8",
    )
    candidate_json.write_text(
        json.dumps(
            [
                _entry(
                    "stt_request_complete",
                    "engineer-cafe-backend-00101-onnx",
                    stt_request_duration_ms=150,
                ),
                _entry(
                    "stt_qwen_runtime_complete",
                    "engineer-cafe-backend-00101-onnx",
                    model_name="Qwen/Qwen3-ASR-Flash-ONNX",
                    model_variant="0.6b-onnx",
                    device="cpu",
                    stt_qwen_runtime_duration_ms=70,
                    stt_qwen_model_inference_duration_ms=40,
                ),
                _entry(
                    "stt_qwen_postprocess_complete",
                    "engineer-cafe-backend-00101-onnx",
                    changed=False,
                    deterministic_changed=False,
                    llm_changed=False,
                ),
                _entry(
                    "stt_qwen_hedge_start",
                    "engineer-cafe-backend-00101-onnx",
                    stt_hedge_wait_duration_ms=20,
                ),
                _entry(
                    "stt_qwen_hedge_grace_complete",
                    "engineer-cafe-backend-00101-onnx",
                    stt_qwen_grace_wait_duration_ms=10,
                ),
                _entry(
                    "stt_winner",
                    "engineer-cafe-backend-00101-onnx",
                    stt_winner="qwen",
                    stt_overall_duration_ms=180,
                    stt_qwen_grace_wait_duration_ms=10,
                ),
            ]
        ),
        encoding="utf-8",
    )

    result = subprocess.run(
        [
            str(COMPARE_SCRIPT),
            "--baseline-json",
            str(baseline_json),
            "--candidate-json",
            str(candidate_json),
            "--env-label",
            "prod",
            "--baseline-label",
            "pytorch-qwen-cpu",
            "--candidate-label",
            "onnx-qwen-cpu",
        ],
        check=True,
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )

    assert "- Environment label: `prod`" in result.stdout
    assert "| request_total p50 | 200 | 150 | -50 | onnx-qwen-cpu |" in result.stdout
    assert "| qwen_runtime p50 | 100 | 70 | -30 | onnx-qwen-cpu |" in result.stdout
    assert "| qwen_model_inference p50 | 80 | 40 | -40 | onnx-qwen-cpu |" in result.stdout
    assert "| qwen | 1 | 1 |" in result.stdout
    assert "| qwen_postprocess_complete | 1 | 1 |" in result.stdout
    assert "| qwen_postprocess_deterministic_changed | 1 | 0 |" in result.stdout
    assert "| stt_qwen_hedge_grace_complete | 1 | 1 |" in result.stdout
    assert "0.6b-pytorch" in result.stdout
    assert "0.6b-onnx" in result.stdout
