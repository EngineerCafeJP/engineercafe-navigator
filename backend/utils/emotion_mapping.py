"""
EmotionMapping - 感情マッピングユーティリティ

VRMキャラクターの表情・アニメーション制御のための感情マッピングを提供します。
Mastra版の`emotion-mapping.ts`を参考にしたPython実装。

参考:
- frontend/src/lib/emotion-mapping.ts
"""

from typing import Dict, Literal, Any, List, Optional

# サポートされているVRM表情タイプ (VRM1.0準拠)
SupportedExpression = Literal["neutral", "happy", "sad", "angry", "surprised", "relaxed"]


class EmotionMapping:
    """
    感情マッピングクラス

    様々な感情エイリアスを標準VRM表情にマッピングし、
    アニメーションや強度情報を提供します。
    """

    # 感情タグ→(VRM表情, 強度)マッピングテーブル
    # 感情タグをキーとして、値として(VRM表情, 強度)のタプルを持つ
    EXPRESSION_MAP: Dict[str, tuple[SupportedExpression, float]] = {
        "happy": ("happy", 1.0),
        "sad": ("sad", 1.0),
        "angry": ("angry", 1.0),
        "relaxed": ("relaxed", 1.0),
        "surprised": ("surprised", 1.0),
        "apologetic": ("sad", 1.0),
        "informative": ("relaxed", 1.0),
        "guiding": ("relaxed", 1.0),
        "helpful": ("happy", 1.0),
        "neutral": ("neutral", 1.0),
        "serious": ("sad", 1.0),
        "confident": ("relaxed", 1.0),
        "grateful": ("happy", 1.0),
        "confused": ("sad", 1.0),
    }

    DEFAULT_EXPRESSION: SupportedExpression = "neutral"
    DEFAULT_INTENSITY: float = 1.0
    DEFAULT_EXPRESSION_DURATION: float = 2.0

    # VRM表情→アニメーションマッピングテーブル
    ANIMATION_MAP: Dict[SupportedExpression, str] = {
        "neutral": "idle",
        "happy": "greeting",
        "sad": "thinking",
        "angry": "explaining",
        "surprised": "greeting",
        "relaxed": "thinking",
    }

    DEFAULT_ANIMATION: str = "idle"

    # Visemeマッピング（リップシンク用の口形状）
    # VRMのBlendShape名に対応: A→aa, I→ih, U→ou, E→ee, O→oh, Closed→neutral
    VISEME_MAPPING: Dict[str, str] = {
        "A": "aa",
        "I": "ih",
        "U": "ou",
        "E": "ee",
        "O": "oh",
        "Closed": "neutral",
    }

    # Visemeのtransition時間（口の動きは素早く）
    VISEME_TRANSITION_DURATION: float = 0.1

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
            return {
                "expression": cls.DEFAULT_EXPRESSION,
                "intensity": cls.DEFAULT_INTENSITY,
            }

        normalized_emotion = emotion.lower().strip()

        # EXPRESSION_MAPから直接取得
        if normalized_emotion in cls.EXPRESSION_MAP:
            expression, intensity = cls.EXPRESSION_MAP[normalized_emotion]
        else:
            # EXPRESSION_MAPに定義されていない場合、
            # "neutral"をデフォルトとして使用
            expression, intensity = cls.EXPRESSION_MAP[cls.DEFAULT_EXPRESSION]

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

    @classmethod
    def extract_viseme_from_lipsync_data(
        cls, lipsync_data: List[Dict[str, Any]]
    ) -> Optional[Dict[str, Any]]:
        """
        リップシンクデータからViseme式を抽出

        リップシンクデータの最初のフレームから口形状情報を取得し、
        VRM制御用のViseme式オブジェクトを生成します。

        Args:
            lipsync_data: リップシンクデータのリスト
                [
                    {
                        "time": float,
                        "volume": float,
                        "mouthOpen": float,
                        "mouthShape": str  # "A", "I", "U", "E", "O", "Closed"
                    },
                    ...
                ]

        Returns:
            Viseme式オブジェクト（リップシンクデータが無効な場合はNone）
            {
                "name": str,  # Viseme名（"aa", "ih", "ou", "ee", "oh", "neutral"）
                "value": float,  # 口の開き具合（0.0-1.0）
                "transition": float  # 遷移時間（秒）
            }

        Examples:
            >>> lipsync_data = [
            ...     {"time": 0.0, "volume": 0.5, "mouthOpen": 0.3, "mouthShape": "A"}
            ... ]
            >>> viseme = EmotionMapping.extract_viseme_from_lipsync_data(lipsync_data)
            >>> viseme["name"]
            'aa'
            >>> viseme["value"]
            0.3
        """
        if not lipsync_data or len(lipsync_data) == 0:
            return None

        try:
            # 最初のフレームからmouthShapeとmouthOpenを取得
            first_frame = lipsync_data[0]
            mouth_shape = first_frame.get("mouthShape", "Closed")
            mouth_open = first_frame.get("mouthOpen", 0.0)

            # mouth_openの値を検証（0.0-1.0の範囲に制限）
            if not isinstance(mouth_open, (int, float)):
                mouth_open = 0.0
            else:
                mouth_open = max(0.0, min(1.0, float(mouth_open)))

            # Visemeマッピングを適用
            viseme_name = cls.VISEME_MAPPING.get(mouth_shape, "neutral")

            # Viseme式オブジェクトを生成
            return {
                "name": viseme_name,
                "value": mouth_open,
                "transition": cls.VISEME_TRANSITION_DURATION,
            }

        except Exception:
            # エラー時はNoneを返す（呼び出し側でエラーハンドリング）
            return None
