from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

logger = logging.getLogger("backend.agents.voice_agent")

# -----------------------------------------------------------------------------
# Emotion mapping (TS emotion-mapping.ts compatible)
# -----------------------------------------------------------------------------

VRM_EMOTION_MAP: Dict[str, str] = {
    # neutral
    "neutral": "neutral",
    "calm": "neutral",
    "normal": "neutral",
    "explaining": "neutral",
    "teaching": "neutral",
    "describing": "neutral",
    # happy
    "happy": "happy",
    "joy": "happy",
    "excited": "happy",
    "cheerful": "happy",
    "pleased": "happy",
    "greeting": "happy",
    "welcoming": "happy",
    "confident": "happy",
    "proud": "happy",
    "grateful": "happy",
    "warm": "happy",
    "helpful": "happy",
    # sad
    "sad": "sad",
    "disappointed": "sad",
    "melancholy": "sad",
    "down": "sad",
    "worried": "sad",
    "embarrassed": "sad",
    "apologetic": "sad",
    # angry
    "angry": "angry",
    "mad": "angry",
    "frustrated": "angry",
    "annoyed": "angry",
    # relaxed
    "relaxed": "relaxed",
    "thinking": "relaxed",
    "pondering": "relaxed",
    "wondering": "relaxed",
    "listening": "relaxed",
    "attentive": "relaxed",
    "concerned": "relaxed",
    "shy": "relaxed",
    "confused": "relaxed",
    "thoughtful": "relaxed",
    "supportive": "relaxed",
    "gentle": "relaxed",
    # surprised
    "curious": "surprised",
    "surprised": "surprised",
    "shocked": "surprised",
    "amazed": "surprised",
    "astonished": "surprised",
    "questioning": "surprised",
    "inquisitive": "surprised",
}


def is_supported_emotion_alias(emotion: str) -> bool:
    return isinstance(emotion, str) and emotion.lower().strip() in VRM_EMOTION_MAP


def map_to_vrm_emotion(emotion: Any) -> str:
    if not isinstance(emotion, str):
        return "neutral"
    return VRM_EMOTION_MAP.get(emotion.lower().strip(), "neutral")


def map_vrm_to_tts_emotion(vrm_emotion: str) -> str:
    """Map VRM emotion (6 kinds) to TTS emotion keys (TS GoogleCloudVoiceSimple).

    VRM: neutral/happy/sad/angry/surprised/relaxed
    TTS: happy/sad/angry/excited/calm
    """

    mapping = {
        "happy": "happy",
        "sad": "sad",
        "angry": "angry",
        "relaxed": "calm",
        "surprised": "excited",
        "neutral": "calm",
    }
    return mapping.get(vrm_emotion, "calm")


# -----------------------------------------------------------------------------
# Emotion tag parser (TS emotion-tag-parser.ts compatible)
# -----------------------------------------------------------------------------

# Matches: [happy], [/happy], [happy:0.8], [/happy:0.8]
EMOTION_TAG_REGEX = re.compile(r"\[/?([a-zA-Z_]+)(?::(\d*\.?\d+))?\]")


@dataclass
class EmotionTag:
    emotion: str
    position: int
    intensity: float = 1.0


@dataclass
class ParsedResponse:
    clean_text: str
    emotions: List[EmotionTag]
    primary_emotion: Optional[str]


def parse_emotion_tags(text: str) -> ParsedResponse:
    emotions: List[EmotionTag] = []
    if not text:
        return ParsedResponse(clean_text="", emotions=[], primary_emotion=None)

    for m in EMOTION_TAG_REGEX.finditer(text):
        raw = (m.group(1) or "").lower()
        intensity_str = m.group(2)
        intensity = float(intensity_str) if intensity_str else 1.0
        intensity = max(0.0, min(1.0, intensity))
        pos = m.start()

        if is_supported_emotion_alias(raw):
            vrm_emotion = map_to_vrm_emotion(raw)
            emotions.append(EmotionTag(emotion=vrm_emotion, position=pos, intensity=intensity))
        else:
            logger.warning("Unknown emotion tag: [%s]", raw)

    clean = EMOTION_TAG_REGEX.sub("", text).strip()
    clean = re.sub(r"\s+", " ", clean).strip()

    primary = None
    if emotions:
        primary = sorted(emotions, key=lambda e: e.intensity, reverse=True)[0].emotion

    return ParsedResponse(clean_text=clean, emotions=emotions, primary_emotion=primary)
