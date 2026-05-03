import subprocess
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[3]
SCRIPT = ROOT_DIR / "scripts" / "alpha-smoke-comprehensive.sh"


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
