"""
EmotionMapping - 感情マッピングユーティリティ

VRMキャラクターの表情・アニメーション制御のための感情マッピングを提供します。
Mastra版の`emotion-mapping.ts`を参考にしたPython実装。

参考:
- frontend/src/lib/emotion-mapping.ts
- frontend/src/_reference/mastra/agents/character-control-agent.ts
"""

from typing import Dict, Literal, Any

# サポートされているVRM表情タイプ (VRM1.0準拠)
SupportedExpression = Literal[
    "neutral", "happy", "sad", "angry", "surprised", "relaxed"
]


class EmotionMapping:
    """
    感情マッピングクラス

    様々な感情エイリアスを標準VRM表情にマッピングし、
    アニメーションや強度情報を提供します。
    """

    # 感情タグ→(VRM表情, 強度)マッピングテーブル
    # 感情タグをキーとして、値として(VRM表情, 強度)のタプルを持つ
    EXPRESSION_MAP: Dict[str, tuple[SupportedExpression, float]] = {
        # Basic emotions
        "neutral": ("neutral", 1.0),
        "calm": ("neutral", 0.9),
        "normal": ("neutral", 1.0),
        "explaining": ("neutral", 0.8),
        "teaching": ("neutral", 0.8),
        "describing": ("neutral", 0.8),
        # Happy emotions
        "happy": ("happy", 0.8),
        "joy": ("happy", 0.9),
        "excited": ("happy", 0.9),
        "cheerful": ("happy", 0.85),
        "pleased": ("happy", 0.75),
        "greeting": ("happy", 0.9),
        "welcoming": ("happy", 0.85),
        "confident": ("happy", 0.8),
        "proud": ("happy", 0.85),
        "grateful": ("happy", 0.8),
        "warm": ("happy", 0.75),
        "helpful": ("happy", 0.8),
        # Sad emotions
        "sad": ("sad", 0.7),
        "disappointed": ("sad", 0.75),
        "melancholy": ("sad", 0.7),
        "down": ("sad", 0.7),
        "worried": ("sad", 0.7),
        "embarrassed": ("sad", 0.7),
        "apologetic": ("sad", 0.7),
        "sorry": ("sad", 0.7),
        "concerned": ("sad", 0.65),
        # Angry emotions
        "angry": ("angry", 0.9),
        "mad": ("angry", 0.9),
        "frustrated": ("angry", 0.85),
        "annoyed": ("angry", 0.8),
        # Relaxed emotions
        "relaxed": ("relaxed", 0.6),
        "thinking": ("relaxed", 0.6),
        "pondering": ("relaxed", 0.6),
        "wondering": ("relaxed", 0.6),
        "listening": ("relaxed", 0.6),
        "attentive": ("relaxed", 0.6),
        "shy": ("relaxed", 0.6),
        "confused": ("relaxed", 0.75),
        "thoughtful": ("relaxed", 0.6),
        "supportive": ("relaxed", 0.6),
        "gentle": ("relaxed", 0.6),
        "peaceful": ("relaxed", 0.65),
        "content": ("relaxed", 0.7),
        # Surprise and questioning
        "curious": ("surprised", 0.7),
        "surprised": ("surprised", 0.8),
        "shocked": ("surprised", 0.9),
        "amazed": ("surprised", 0.85),
        "astonished": ("surprised", 0.8),
        "questioning": ("surprised", 0.8),
        "inquisitive": ("surprised", 0.8),
    }

    # VRM表情→アニメーションマッピングテーブル
    ANIMATION_MAP: Dict[SupportedExpression, str] = {
        "neutral": "idle",
        "happy": "greeting",
        "sad": "thinking",
        "angry": "explaining",
        "surprised": "greeting",
        "relaxed": "thinking",
    }

    @classmethod
    def map_to_expression(cls, emotion: str) -> SupportedExpression:
        """
        任意の感情文字列をサポートされているVRM表情にマッピング

        Args:
            emotion: 感情タグ（"happy", "sad", "neutral", "excited"等）

        Returns:
            サポートされているVRM表情 (SupportedExpression)
            サポート外の場合は "neutral" を返す

        Examples:
            >>> EmotionMapping.map_to_expression("happy")
            'happy'
            >>> EmotionMapping.map_to_expression("excited")
            'happy'
            >>> EmotionMapping.map_to_expression("unknown")
            'neutral'
        """
        if not emotion or not isinstance(emotion, str):
            return "neutral"

        normalized_emotion = emotion.lower().strip()
        if normalized_emotion in cls.EXPRESSION_MAP:
            return cls.EXPRESSION_MAP[normalized_emotion][0]
        return "neutral"

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
        expression = cls.map_to_expression(emotion)
        return cls.ANIMATION_MAP.get(expression, "idle")

    @classmethod
    def get_intensity_for_emotion(cls, emotion: str) -> float:
        """
        感情のデフォルト強度を取得

        感情タグごとの強度マッピングを優先的に使用し、
        定義されていない場合はVRM表情のデフォルト強度を使用します。

        Args:
            emotion: 感情タグ

        Returns:
            強度（0.0-1.0）

        Examples:
            >>> EmotionMapping.get_intensity_for_emotion("happy")
            0.8
            >>> EmotionMapping.get_intensity_for_emotion("excited")
            0.9
            >>> EmotionMapping.get_intensity_for_emotion("neutral")
            1.0
        """
        if not emotion or not isinstance(emotion, str):
            return 1.0

        normalized_emotion = emotion.lower().strip()

        # EXPRESSION_MAPをチェック
        if normalized_emotion in cls.EXPRESSION_MAP:
            return cls.EXPRESSION_MAP[normalized_emotion][1]

        # EXPRESSION_MAPに定義されていない場合、
        # "neutral"の強度をデフォルトとして使用
        return cls.EXPRESSION_MAP["neutral"][1]

    @classmethod
    def get_expression_with_intensity(cls, emotion: str) -> Dict[str, Any]:
        """
        感情タグからVRM表情と強度を一度に取得

        EXPRESSION_MAPから直接、感情タグに対応するVRM表情と強度を取得します。

        Args:
            emotion: 感情タグ

        Returns:
            VRM表情と強度を含む辞書
            {
                "expression": str,  # VRM表情（"neutral", "happy", "sad"等）
                "intensity": float   # 表情の強度（0.0-1.0）
            }

        Examples:
            >>> result = EmotionMapping.get_expression_with_intensity("excited")
            >>> result["expression"]
            'happy'
            >>> result["intensity"]
            0.9
            >>> result = EmotionMapping.get_expression_with_intensity("happy")
            >>> result["expression"]
            'happy'
            >>> result["intensity"]
            0.8
        """
        if not emotion or not isinstance(emotion, str):
            return {"expression": "neutral", "intensity": 1.0}

        normalized_emotion = emotion.lower().strip()

        # EXPRESSION_MAPから直接取得
        if normalized_emotion in cls.EXPRESSION_MAP:
            expression, intensity = cls.EXPRESSION_MAP[normalized_emotion]
        else:
            # EXPRESSION_MAPに定義されていない場合、
            # "neutral"をデフォルトとして使用
            expression, intensity = cls.EXPRESSION_MAP["neutral"]

        return {
            "expression": expression,
            "intensity": intensity,
        }

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
        return emotion.lower() in cls.EXPRESSION_MAP

    @classmethod
    def get_supported_expressions(cls) -> list[SupportedExpression]:
        """
        サポートされているすべてのVRM表情を取得

        Returns:
            サポートされているVRM表情のリスト

        Examples:
            >>> expressions = EmotionMapping.get_supported_expressions()
            >>> "neutral" in expressions
            True
            >>> "happy" in expressions
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
        return list(cls.EXPRESSION_MAP.keys())

    @classmethod
    def normalize_emotion(
        cls, emotion: str, intensity: float | None = None
    ) -> dict[str, SupportedExpression | float]:
        """
        感情を正規化（VRM表情と強度を返す）

        Args:
            emotion: 感情タグ
            intensity: 強度（オプション、指定がない場合はデフォルト値を使用）

        Returns:
            正規化されたVRM表情と強度の辞書
            {
                "expression": SupportedExpression,
                "intensity": float
            }

        Examples:
            >>> result = EmotionMapping.normalize_emotion("happy")
            >>> result["expression"]
            'happy'
            >>> result["intensity"]
            0.8
            >>> result = EmotionMapping.normalize_emotion("happy", 0.5)
            >>> result["intensity"]
            0.5
        """
        expression = cls.map_to_expression(emotion)
        if intensity is not None:
            normalized_intensity = max(0.0, min(1.0, intensity))
        else:
            normalized_intensity = cls.get_intensity_for_emotion(emotion)

        return {
            "expression": expression,
            "intensity": normalized_intensity,
        }
