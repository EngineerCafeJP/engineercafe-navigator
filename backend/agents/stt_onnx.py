"""Thin ONNX Runtime adapter for experimental Qwen3-ASR STT.

The exported Qwen3-ASR ONNX contract is intentionally configurable through
environment variables so this spike can work with generated artifacts without
making those artifacts part of the test suite.
"""

from __future__ import annotations

import importlib
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

import numpy as np


class QwenOnnxRuntimeError(RuntimeError):
    """Base error for the experimental Qwen ONNX runtime."""


class QwenOnnxRuntimeUnavailable(QwenOnnxRuntimeError):
    """ONNX Runtime is not installed in the current environment."""


class QwenOnnxModelArtifactsMissing(QwenOnnxRuntimeError):
    """Required ONNX model artifacts are missing or not configured."""


@dataclass(frozen=True)
class QwenOnnxTranscription:
    text: str
    language: Optional[str] = None
    confidence: Optional[float] = None


@dataclass(frozen=True)
class QwenOnnxRuntimeConfig:
    model_path: Optional[str]
    tokenizer_path: Optional[str] = None
    providers: tuple[str, ...] = ("CPUExecutionProvider",)
    audio_input_name: str = "audio"
    sample_rate_input_name: Optional[str] = "sample_rate"
    language_input_name: Optional[str] = None
    text_output_name: Optional[str] = None
    tokens_output_name: Optional[str] = None
    language_output_name: Optional[str] = None
    confidence_output_name: Optional[str] = None

    @classmethod
    def from_env(cls) -> "QwenOnnxRuntimeConfig":
        return cls(
            model_path=os.getenv("STT_QWEN_ONNX_MODEL_PATH"),
            tokenizer_path=os.getenv("STT_QWEN_ONNX_TOKENIZER_PATH"),
            providers=_parse_providers(os.getenv("STT_QWEN_ONNX_PROVIDERS")),
            audio_input_name=os.getenv("STT_QWEN_ONNX_AUDIO_INPUT", "audio"),
            sample_rate_input_name=_optional_env("STT_QWEN_ONNX_SAMPLE_RATE_INPUT", "sample_rate"),
            language_input_name=_optional_env("STT_QWEN_ONNX_LANGUAGE_INPUT"),
            text_output_name=_optional_env("STT_QWEN_ONNX_TEXT_OUTPUT"),
            tokens_output_name=_optional_env("STT_QWEN_ONNX_TOKENS_OUTPUT"),
            language_output_name=_optional_env("STT_QWEN_ONNX_LANGUAGE_OUTPUT"),
            confidence_output_name=_optional_env("STT_QWEN_ONNX_CONFIDENCE_OUTPUT"),
        )


def _optional_env(name: str, default: Optional[str] = None) -> Optional[str]:
    value = os.getenv(name, default)
    if value is None:
        return None
    value = value.strip()
    return value or None


def _parse_providers(raw_value: Optional[str]) -> tuple[str, ...]:
    if not raw_value or not raw_value.strip():
        return ("CPUExecutionProvider",)
    providers = tuple(part.strip() for part in raw_value.split(",") if part.strip())
    return providers or ("CPUExecutionProvider",)


class QwenOnnxRuntime:
    """Lazy ONNX Runtime session wrapper.

    This intentionally supports two artifact styles:
    - a graph that returns a string transcript tensor;
    - a graph that returns token IDs plus a Hugging Face tokenizer path.
    """

    def __init__(self, config: Optional[QwenOnnxRuntimeConfig] = None):
        self.config = config or QwenOnnxRuntimeConfig.from_env()
        self._session: Any = None
        self._tokenizer: Any = None

    def ensure_ready(self) -> None:
        if self._session is not None:
            return

        try:
            ort = importlib.import_module("onnxruntime")
        except ImportError as exc:
            raise QwenOnnxRuntimeUnavailable(
                "STT_QWEN_RUNTIME=onnx requires onnxruntime. Install backend "
                "dependencies or unset STT_QWEN_RUNTIME to use the PyTorch Qwen path."
            ) from exc

        if not self.config.model_path:
            raise QwenOnnxModelArtifactsMissing(
                "STT_QWEN_RUNTIME=onnx requires STT_QWEN_ONNX_MODEL_PATH to point "
                "to an exported Qwen3-ASR ONNX model."
            )

        model_path = Path(self.config.model_path)
        if not model_path.is_file():
            raise QwenOnnxModelArtifactsMissing(
                f"Qwen3-ASR ONNX model not found at {model_path}. Set "
                "STT_QWEN_ONNX_MODEL_PATH to a readable .onnx file or unset "
                "STT_QWEN_RUNTIME."
            )

        self._session = ort.InferenceSession(str(model_path), providers=list(self.config.providers))

    def transcribe(
        self,
        pcm: np.ndarray,
        sample_rate: int,
        *,
        language: Optional[str] = None,
    ) -> QwenOnnxTranscription:
        self.ensure_ready()

        inputs = self._build_inputs(pcm, sample_rate, language)
        output_values = self._session.run(None, inputs)
        output_names = [output.name for output in self._session.get_outputs()]
        outputs = dict(zip(output_names, output_values))
        text = self._extract_text(outputs)
        if not text:
            raise QwenOnnxRuntimeError(
                "Qwen3-ASR ONNX inference produced no transcript. Configure "
                "STT_QWEN_ONNX_TEXT_OUTPUT for string outputs or "
                "STT_QWEN_ONNX_TOKENS_OUTPUT plus STT_QWEN_ONNX_TOKENIZER_PATH "
                "for token outputs."
            )

        return QwenOnnxTranscription(
            text=text,
            language=self._extract_optional_str(outputs, self.config.language_output_name),
            confidence=self._extract_optional_float(outputs, self.config.confidence_output_name),
        )

    def _build_inputs(
        self,
        pcm: np.ndarray,
        sample_rate: int,
        language: Optional[str],
    ) -> dict[str, Any]:
        audio = np.asarray(pcm, dtype=np.float32)
        if audio.ndim == 1:
            audio = audio[np.newaxis, :]

        inputs: dict[str, Any] = {self.config.audio_input_name: audio}
        if self.config.sample_rate_input_name:
            inputs[self.config.sample_rate_input_name] = np.asarray([sample_rate], dtype=np.int64)
        if self.config.language_input_name and language:
            inputs[self.config.language_input_name] = np.asarray([language])
        return inputs

    def _extract_text(self, outputs: dict[str, Any]) -> str:
        if self.config.text_output_name:
            return self._coerce_text(outputs.get(self.config.text_output_name))

        for value in outputs.values():
            text = self._coerce_text(value)
            if text:
                return text

        tokens = None
        if self.config.tokens_output_name:
            tokens = outputs.get(self.config.tokens_output_name)
        else:
            tokens = next(
                (value for value in outputs.values() if _looks_like_token_ids(value)), None
            )

        if tokens is None:
            return ""
        return self._decode_tokens(tokens)

    def _decode_tokens(self, tokens: Any) -> str:
        if not self.config.tokenizer_path:
            raise QwenOnnxModelArtifactsMissing(
                "Token output decoding requires STT_QWEN_ONNX_TOKENIZER_PATH. "
                "Set it to the matching Qwen tokenizer directory or configure "
                "STT_QWEN_ONNX_TEXT_OUTPUT for string transcript outputs."
            )

        tokenizer_path = Path(self.config.tokenizer_path)
        if not tokenizer_path.exists():
            raise QwenOnnxModelArtifactsMissing(
                f"Qwen3-ASR ONNX tokenizer not found at {tokenizer_path}. Set "
                "STT_QWEN_ONNX_TOKENIZER_PATH to a readable tokenizer directory."
            )

        if self._tokenizer is None:
            try:
                transformers = importlib.import_module("transformers")
            except ImportError as exc:
                raise QwenOnnxRuntimeUnavailable(
                    "Decoding Qwen3-ASR ONNX token outputs requires transformers. "
                    "Install backend dependencies or export a graph with string output."
                ) from exc
            self._tokenizer = transformers.AutoTokenizer.from_pretrained(str(tokenizer_path))

        token_array = np.asarray(tokens)
        if token_array.ndim > 1:
            token_array = token_array[0]
        return self._tokenizer.decode(token_array.tolist(), skip_special_tokens=True).strip()

    @staticmethod
    def _coerce_text(value: Any) -> str:
        if value is None:
            return ""
        array = np.asarray(value)
        if array.size == 0:
            return ""
        item = array.reshape(-1)[0]
        if isinstance(item, bytes):
            return item.decode("utf-8", errors="replace").strip()
        if isinstance(item, str):
            return item.strip()
        return ""

    @staticmethod
    def _extract_optional_str(outputs: dict[str, Any], output_name: Optional[str]) -> Optional[str]:
        if not output_name:
            return None
        return QwenOnnxRuntime._coerce_text(outputs.get(output_name)) or None

    @staticmethod
    def _extract_optional_float(
        outputs: dict[str, Any], output_name: Optional[str]
    ) -> Optional[float]:
        if not output_name or output_name not in outputs:
            return None
        array = np.asarray(outputs[output_name])
        if array.size == 0:
            return None
        return float(array.reshape(-1)[0])


def _looks_like_token_ids(value: Any) -> bool:
    try:
        array = np.asarray(value)
    except Exception:
        return False
    return array.size > 0 and np.issubdtype(array.dtype, np.integer)
