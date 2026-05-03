from pathlib import Path


def test_production_image_downloads_translation_models():
    dockerfile = Path(__file__).resolve().parents[1] / "Dockerfile"
    text = dockerfile.read_text(encoding="utf-8")
    production_stage = text.split("FROM base AS production", maxsplit=1)[1]

    assert "scripts/download_translation_models.sh models/translation" in production_stage
    assert "scripts/download_qwen_model.sh" in production_stage


def test_image_keeps_qwen_runtime_dependencies_after_translation_download():
    dockerfile = Path(__file__).resolve().parents[1] / "Dockerfile"
    text = dockerfile.read_text(encoding="utf-8")
    production_stage = text.split("FROM base AS production", maxsplit=1)[1]

    assert "pip uninstall -y torch transformers" not in text
    assert "from qwen_asr import Qwen3ASRModel" in production_stage
