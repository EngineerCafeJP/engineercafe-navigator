"""
EmotionMapping - 感情マッピングユーティリティ

VRMキャラクターの表情・アニメーション制御のための感情マッピングを提供します。
Mastra版の`emotion-mapping.ts`を参考にしたPython実装。

参考:
- frontend/src/lib/emotion-mapping.ts
- frontend/src/_reference/mastra/agents/character-control-agent.ts
"""

from typing import Dict, Literal

# サポートされているVRM感情タイプ
SupportedEmotion = Literal[
    "neutral", "happy", "sad", "angry", "surprised", "relaxed"
]


class EmotionMapping:
    """
    感情マッピングクラス

    様々な感情エイリアスを標準VRM感情にマッピングし、
    アニメーションや強度情報を提供します。
    """

    # 感情→VRM表情マッピングテーブル
    # 様々な感情エイリアスを標準VRM感情にマッピング
    VRM_EMOTION_MAP: Dict[str, SupportedEmotion] = {
        # Basic emotions
        "neutral": "neutral",
        "calm": "neutral",
        "normal": "neutral",
        "explaining": "neutral",
        "teaching": "neutral",
        "describing": "neutral",
        # Happy emotions
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
        # Sad emotions
        "sad": "sad",
        "disappointed": "sad",
        "melancholy": "sad",
        "down": "sad",
        "worried": "sad",
        "embarrassed": "sad",
        "apologetic": "sad",
        # Angry emotions
        "angry": "angry",
        "mad": "angry",
        "frustrated": "angry",
        "annoyed": "angry",
        # Relaxed emotions
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
        # Surprise and questioning
        "curious": "surprised",
        "surprised": "surprised",
        "shocked": "surprised",
        "amazed": "surprised",
        "astonished": "surprised",
        "questioning": "surprised",
        "inquisitive": "surprised",
    }

    # 感情→アニメーションマッピングテーブル
    ANIMATION_MAP: Dict[SupportedEmotion, str] = {
        "neutral": "idle",
        "happy": "greeting",
        "sad": "thinking",
        "angry": "explaining",
        "surprised": "greeting",
        "relaxed": "thinking",
    }

    # 感情→強度マッピングテーブル
    INTENSITY_MAP: Dict[SupportedEmotion, float] = {
        "neutral": 1.0,
        "happy": 0.8,
        "sad": 0.7,
        "angry": 0.9,
        "surprised": 0.8,
        "relaxed": 0.6,
    }

    @classmethod
    def map_to_vrm_emotion(cls, emotion: str) -> SupportedEmotion:
        """
        任意の感情文字列をサポートされているVRM感情にマッピング

        Args:
            emotion: 感情タグ（"happy", "sad", "neutral", "excited"等）

        Returns:
            サポートされているVRM感情

        Examples:
            >>> EmotionMapping.map_to_vrm_emotion("happy")
            'happy'
            >>> EmotionMapping.map_to_vrm_emotion("excited")
            'happy'
            >>> EmotionMapping.map_to_vrm_emotion("unknown")
            'neutral'
        """
        if not emotion or not isinstance(emotion, str):
            return "neutral"

        normalized_emotion = emotion.lower().strip()
        return cls.VRM_EMOTION_MAP.get(normalized_emotion, "neutral")

    @classmethod
    def get_animation_for_emotion(cls, emotion: str) -> str:
        """
        感情に対応するアニメーション名を取得

        Args:
            emotion: 感情タグ

        Returns:
            アニメーション名

        Examples:
            >>> EmotionMapping.get_animation_for_emotion("happy")
            'greeting'
            >>> EmotionMapping.get_animation_for_emotion("sad")
            'thinking'
        """
        vrm_emotion = cls.map_to_vrm_emotion(emotion)
        return cls.ANIMATION_MAP.get(vrm_emotion, "idle")

    @classmethod
    def get_intensity_for_emotion(cls, emotion: str) -> float:
        """
        感情のデフォルト強度を取得

        Args:
            emotion: 感情タグ

        Returns:
            強度（0.0-1.0）

        Examples:
            >>> EmotionMapping.get_intensity_for_emotion("happy")
            0.8
            >>> EmotionMapping.get_intensity_for_emotion("neutral")
            1.0
        """
        vrm_emotion = cls.map_to_vrm_emotion(emotion)
        return cls.INTENSITY_MAP.get(vrm_emotion, 1.0)

    @classmethod
    def is_supported_emotion(cls, emotion: str) -> bool:
        """
        感情がサポートされているかチェック

        Args:
            emotion: 感情タグ

        Returns:
            サポートされている場合True

        Examples:
            >>> EmotionMapping.is_supported_emotion("happy")
            True
            >>> EmotionMapping.is_supported_emotion("unknown")
            False
        """
        if not emotion or not isinstance(emotion, str):
            return False
        return emotion.lower() in cls.VRM_EMOTION_MAP

    @classmethod
    def get_supported_emotions(cls) -> list[SupportedEmotion]:
        """
        サポートされているすべてのVRM感情を取得

        Returns:
            サポートされているVRM感情のリスト

        Examples:
            >>> emotions = EmotionMapping.get_supported_emotions()
            >>> "neutral" in emotions
            True
            >>> "happy" in emotions
            True
        """
        return ["neutral", "happy", "sad", "angry", "surprised", "relaxed"]

    @classmethod
    def get_all_emotion_aliases(cls) -> list[str]:
        """
        すべての感情エイリアスを取得

        Returns:
            感情エイリアスのリスト

        Examples:
            >>> aliases = EmotionMapping.get_all_emotion_aliases()
            >>> "happy" in aliases
            True
            >>> "excited" in aliases
            True
        """
        return list(cls.VRM_EMOTION_MAP.keys())

    @classmethod
    def normalize_emotion(
        cls, emotion: str, intensity: float | None = None
    ) -> dict[str, SupportedEmotion | float]:
        """
        感情を正規化（VRM感情と強度を返す）

        Args:
            emotion: 感情タグ
            intensity: 強度（オプション、指定がない場合はデフォルト値を使用）

        Returns:
            正規化された感情と強度の辞書
            {
                "emotion": SupportedEmotion,
                "intensity": float
            }

        Examples:
            >>> result = EmotionMapping.normalize_emotion("happy")
            >>> result["emotion"]
            'happy'
            >>> result["intensity"]
            0.8
            >>> result = EmotionMapping.normalize_emotion("happy", 0.5)
            >>> result["intensity"]
            0.5
        """
        normalized_emotion = cls.map_to_vrm_emotion(emotion)
        if intensity is not None:
            normalized_intensity = max(0.0, min(1.0, intensity))
        else:
            normalized_intensity = cls.get_intensity_for_emotion(emotion)

        return {"emotion": normalized_emotion, "intensity": normalized_intensity}
