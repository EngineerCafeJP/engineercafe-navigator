"""Voice route request and response models."""

from __future__ import annotations

from typing import Any, Dict, Literal, Optional

from pydantic import BaseModel, Field


class VoiceRequest(BaseModel):
    action: str
    audioData: Optional[str] = None
    sessionId: Optional[str] = None
    language: Optional[str] = Field(default="ja", max_length=10)
    text: Optional[str] = Field(default=None, max_length=5000)
    streaming: Optional[bool] = False
    conversationStage: Optional[str] = None
    emotion: Optional[str] = None
    outputEncoding: Optional[str] = Field(default=None, max_length=10)
    ttsProvider: Optional[str] = Field(default=None, max_length=20)
    includeVrmControl: Optional[bool] = False


class VoiceResponse(BaseModel):
    success: bool
    transcript: Optional[str] = None
    response: Optional[str] = None
    audioResponse: Optional[str] = None
    audioFormat: Optional[str] = None
    emotion: Optional[str] = None
    sessionId: Optional[str] = None
    error: Optional[str] = None
    detectedLanguage: Optional[str] = None
    confidence: Optional[float] = None
    sttProvider: Optional[str] = None
    sttPostprocessed: Optional[bool] = None
    interruptStatus: Optional[str] = None
    sttWarmupStatus: Optional[str] = None
    sttWarmupProvider: Optional[str] = None
    sttWarmupError: Optional[str] = None
    sttWarmupDurationMs: Optional[int] = None
    cleanText: Optional[str] = None
    vrmControl: Optional[Dict[str, Any]] = None
    requestId: Optional[str] = None
    phase: Optional[str] = None
    upstreamStatus: Optional[Dict[str, Any]] = None


class FillerRequest(BaseModel):
    query: str = Field(max_length=2000)
    language: Literal["ja", "en", "zh", "ko"] = "ja"


class FillerResponse(BaseModel):
    audioResponse: str
    intent: str
    audioFormat: str = "audio/wav"
    fillerText: str
    source: str = "static"
    requestId: Optional[str] = None
    phase: Optional[str] = "filler"
    upstreamStatus: Optional[Dict[str, Any]] = None
