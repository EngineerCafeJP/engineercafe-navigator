"""
CharacterControlAgent骨組み（専門エンジニア向け）

VRMキャラクターの表情・モーションを制御するエージェント。
応答テキストの感情タグに基づいて、適切な表情やアニメーションを指示。

参考:
- docs/migration/agents/character-control-agent/README.md
- engineer-cafe-navigator-repo/src/mastra/agents/character-control-agent.ts (Mastra版)

TODO (専門エンジニア - Chie, takegg0311):
1. 感情→表情マッピング実装
2. VRM制御コマンド生成
3. アニメーション選択ロジック実装
4. リップシンク制御（音声と口の動きの同期）
5. 複数感情の優先順位付け
6. エラーハンドリングとフォールバック
"""

import logging
import math
import random
from typing import Dict, Any, Optional, List

from backend.utils.emotion_mapping import EmotionMapping, SupportedExpression
from backend.utils.kanji_converter import KanjiConverter

# TODO: 実装時に必要なインポート
# from llm.openrouter import OpenRouterProvider
# from llm.models import get_model_config

logger = logging.getLogger(__name__)


class CharacterControlAgent:
    """
    CharacterControlAgent骨組み（専門エンジニア向け）

    このクラスは骨組みのみを提供します。完全実装は専門エンジニア（Chie, takegg0311）が担当。
    """

    DEFAULT_EXPRESSION: str = EmotionMapping.DEFAULT_EXPRESSION
    DEFAULT_INTENSITY: float = EmotionMapping.DEFAULT_INTENSITY
    DEFAULT_EXPRESSION_DURATION: float = EmotionMapping.DEFAULT_EXPRESSION_DURATION
    DEFAULT_ANIMATION: str = EmotionMapping.DEFAULT_ANIMATION

    def __init__(self):
        """
        初期化

        感情マッピングテーブル、アニメーションマッピング、状態変数を初期化します。
        """
        logger.info("CharacterControlAgent初期化開始")

        # 現在の状態変数の初期化
        self.current_expression: str = self.DEFAULT_EXPRESSION
        self.current_intensity: float = self.DEFAULT_INTENSITY
        self.current_expression_duration: float = self.DEFAULT_EXPRESSION_DURATION
        self.current_animation: str = self.DEFAULT_ANIMATION

        # 漢字→読みカナ変換ユーティリティの初期化
        self._kanji_converter = KanjiConverter()

        # リップシンク関連のプレースホルダー（将来の拡張用）
        # TODO: リップシンク解析器の実装
        # self.lip_sync_analyzer = None
        # TODO: リップシンクキャッシュの実装
        # self.lip_sync_cache = None

        logger.info(
            f"CharacterControlAgent初期化完了: expression={self.current_expression}, "
            f"intensity={self.current_intensity}, "
            f"expression_duration={self.current_expression_duration}, "
            f"animation={self.current_animation}"
        )

    def map_emotion_to_expression(self, emotion: str) -> Dict[str, Any]:
        """
        感情を表情パラメータにマッピング

        Args:
            emotion: 感情タグ（"happy", "sad", "neutral", "excited", "confused"等）

        Returns:
            表情パラメータ
            {
                "expression": str,  # 表情名（"neutral", "happy", "sad"等）
                "intensity": float,  # 表情の強度（0.0～1.0）
                "duration": float  # 表情の持続時間（秒）
            }

        Examples:
            >>> agent = CharacterControlAgent()
            >>> result = agent.map_emotion_to_expression("happy")
            >>> result["expression"]
            'happy'
            >>> result["intensity"]
            0.8
        """
        try:
            # 入力検証
            if not emotion or not isinstance(emotion, str):
                logger.warning(
                    f"無効な感情値: {emotion}, "
                    f"型: {type(emotion).__name__}. "
                    "デフォルト値'neutral'を使用します。"
                )
                emotion = "neutral"

            # 1. 感情→VRM表情と強度の取得
            # EmotionMappingを使用して感情を標準VRM表情と強度にマッピング
            expression_data = EmotionMapping.get_expression_with_intensity(emotion)
            mapped_expression = expression_data["expression"]
            intensity = expression_data["intensity"]

            # 将来の拡張用: intensityパラメータが追加された場合の処理
            # Mastra版では、intensity < 0.3 の場合はneutralを返す
            # TODO: メソッドシグネチャにintensityパラメータを追加する場合の処理
            # if intensity is not None and intensity < 0.3:
            #     mapped_expression = "neutral"

            # 2. durationの設定（デフォルト値を使用）
            duration = self.DEFAULT_EXPRESSION_DURATION

            logger.info(
                f"感情→表情マッピング: '{emotion}' -> "
                f"expression='{mapped_expression}', "
                f"intensity={intensity}, duration={duration}s"
            )

            return {
                "expression": mapped_expression,
                "intensity": intensity,
                "duration": duration,
            }

        except Exception as e:
            logger.error(
                f"感情→表情マッピングエラー: emotion={emotion}, "
                f"error={e}",
                exc_info=True,
            )
            # エラー時はデフォルト値を返す（EmotionMappingから取得）
            return {
                "expression": self.DEFAULT_EXPRESSION,
                "intensity": self.DEFAULT_INTENSITY,
                "duration": self.DEFAULT_EXPRESSION_DURATION,
            }

    def select_animation(self, emotion: str, context: Optional[Dict[str, Any]] = None) -> str:
        """
        感情に応じたアニメーションを選択

        Args:
            emotion: 感情タグ（"happy", "sad", "neutral"等）
            context: コンテキスト情報（将来の拡張用、現時点では未使用）

        Returns:
            アニメーション名（"idle", "greeting", "thinking", "explaining"等）

        Examples:
            >>> agent = CharacterControlAgent()
            >>> agent.select_animation("happy")
            'greeting'
            >>> agent.select_animation("sad")
            'thinking'
            >>> agent.select_animation("neutral")
            'idle'

        Note:
            contextパラメータは将来の拡張用として保持されています。
            将来的には、コンテキストに応じたアニメーション選択や
            ランダム性の導入が予定されています。
        """
        try:
            logger.info(f"アニメーション選択開始: emotion={emotion}")

            # 1. emotionのバリデーション
            if not emotion or not isinstance(emotion, str):
                logger.warning(
                    f"無効な感情値: {emotion}, 型: {type(emotion).__name__}. "
                    f"デフォルト値'{self.DEFAULT_ANIMATION}'を使用します。"
                )
                return self.DEFAULT_ANIMATION

            # 2. EmotionMappingを使用してアニメーション名を取得
            animation = EmotionMapping.get_animation_for_emotion(emotion)

            logger.info(
                f"アニメーション選択完了: emotion={emotion}, animation={animation}"
            )

            return animation

        except Exception as e:
            logger.error(
                f"アニメーション選択エラー: emotion={emotion}, error={e}",
                exc_info=True,
            )
            # エラー時はデフォルト値を返す
            return self.DEFAULT_ANIMATION

    def generate_lipsync_data(self, audio_duration: float, text: str) -> List[Dict[str, Any]]:
        """
        リップシンクデータを生成

        Args:
            audio_duration: 音声の長さ（秒）
            text: 発話テキスト

        Returns:
            リップシンクデータ（タイムスタンプと口の形状のリスト）
            [
                {
                    "time": float,        # タイムスタンプ（秒）
                    "volume": float,      # 音量（0.0-1.0）
                    "mouthOpen": float,   # 口の開き具合（0.0-1.0）
                    "mouthShape": str     # 口の形状（"A", "I", "U", "E", "O", "Closed"）
                },
                ...
            ]

        Examples:
            >>> agent = CharacterControlAgent()
            >>> data = agent.generate_lipsync_data(1.0, "Hello")
            >>> len(data) > 0
            True
            >>> data[0]["mouthShape"] in ["A", "I", "U", "E", "O", "Closed"]
            True
        """
        try:
            logger.info(
                f"リップシンクデータ生成開始: duration={audio_duration}s, "
                f"text_length={len(text) if text else 0}"
            )

            # 1. バリデーション
            # audio_durationの検証
            if not isinstance(audio_duration, (int, float)) or audio_duration <= 0:
                logger.warning(
                    f"無効な音声長: {audio_duration}, 型: {type(audio_duration).__name__}. "
                    "フォールバック実装を使用します。"
                )
                return self._generate_fallback_lipsync(audio_duration if audio_duration > 0 else 1.0)

            # textの検証
            if not text or not isinstance(text, str) or not text.strip():
                logger.warning(
                    f"テキストが空または無効です: text={text}. "
                    "フォールバック実装を使用します。"
                )
                return self._generate_fallback_lipsync(audio_duration)

            # 2. テキストベースのリップシンクデータ生成
            frames = self._generate_visemes_from_text(text, audio_duration)

            logger.info(f"リップシンクデータ生成完了: frames={len(frames)}")

            return frames

        except Exception as e:
            logger.error(
                f"リップシンクデータ生成エラー: duration={audio_duration}, "
                f"text_length={len(text) if text else 0}, error={e}",
                exc_info=True,
            )
            # エラー時はフォールバック実装を返す
            return self._generate_fallback_lipsync(audio_duration)

    def _generate_visemes_from_text(self, text: str, duration: float) -> List[Dict[str, Any]]:
        """
        テキストから口の形状（Viseme）を生成

        Args:
            text: 発話テキスト
            duration: 音声の長さ（秒）

        Returns:
            リップシンクフレームのリスト
        """
        frames: List[Dict[str, Any]] = []
        frame_interval = 0.05  # 50ms間隔
        frame_count = math.floor(duration / frame_interval)

        # テキストを単語に分割（空白文字で分割）
        words = text.lower().strip().split()

        for i in range(frame_count):
            time = i * frame_interval
            progress = time / duration if duration > 0 else 0

            # 現在の単語を決定
            current_word_index = math.floor(progress * len(words)) if words else 0
            current_word = words[current_word_index] if current_word_index < len(words) else ""

            # 単語内の母音を検出して口の形状を決定
            mouth_shape = self._detect_mouth_shape_from_word(current_word)

            # 音量と口の開き具合を設定（単語がある場合は0.3-0.7の範囲）
            if current_word:
                volume = 0.3 + random.random() * 0.4
                mouth_open = volume
            else:
                volume = 0.0
                mouth_open = 0.0

            frames.append(
                {
                    "time": time,
                    "volume": volume,
                    "mouthOpen": mouth_open,
                    "mouthShape": mouth_shape,
                }
            )

        return frames

    def _detect_mouth_shape_from_word(self, word: str) -> str:
        """
        単語から口の形状を検出

        漢字を含む単語の場合は、KanjiConverterを使用して読みカナに変換してから母音を検出します。

        Args:
            word: 単語（小文字、漢字を含む可能性がある）

        Returns:
            口の形状（"A", "I", "U", "E", "O", "Closed"）
        """
        if not word:
            return "Closed"

        # 漢字を含む場合は読みカナに変換（KanjiConverterを使用）
        processed_word = self._kanji_converter.convert_to_hiragana(word)

        # 英語の母音を検出
        if "a" in processed_word.lower():
            return "A"
        elif "i" in processed_word.lower():
            return "I"
        elif "u" in processed_word.lower():
            return "U"
        elif "e" in processed_word.lower():
            return "E"
        elif "o" in processed_word.lower():
            return "O"

        # 日本語の母音を検出（ひらがな・カタカナ）
        if "あ" in processed_word or "ア" in processed_word:
            return "A"
        elif "い" in processed_word or "イ" in processed_word:
            return "I"
        elif "う" in processed_word or "ウ" in processed_word:
            return "U"
        elif "え" in processed_word or "エ" in processed_word:
            return "E"
        elif "お" in processed_word or "オ" in processed_word:
            return "O"

        # 母音がない場合は閉じた口
        return "Closed"

    def _generate_fallback_lipsync(self, duration: float) -> List[Dict[str, Any]]:
        """
        フォールバックリップシンクデータを生成

        テキストが無効な場合やエラー時に使用される単純な口パクパターン。

        Args:
            duration: 音声の長さ（秒）

        Returns:
            リップシンクフレームのリスト
        """
        frames: List[Dict[str, Any]] = []
        frame_interval = 0.05  # 50ms間隔
        frame_count = math.floor(duration / frame_interval)

        for i in range(frame_count):
            time = i * frame_interval

            # 200msごとにA/Closedを交互に切り替え
            mouth_shape = "A" if (math.floor(time * 10) % 4) < 2 else "Closed"

            frames.append(
                {
                    "time": time,
                    "volume": 0.5,
                    "mouthOpen": 0.5,
                    "mouthShape": mouth_shape,
                }
            )

        return frames

    def combine_emotions(self, emotions: List[str]) -> str:
        """
        複数の感情を統合

        Args:
            emotions: 感情タグのリスト

        Returns:
            統合された感情タグ

        TODO:
        - 感情の優先順位付け
        - 複数感情のブレンド（例: happy + excited → very_happy）
        - 矛盾する感情の解決（例: happy + sad → neutral）
        """
        logger.info(f"感情統合（骨組み）: {emotions}")

        # TODO: 実装
        # プレースホルダー: 最初の感情を返す
        return emotions[0] if emotions else "neutral"

    def generate_vrm_command(self, expression: str, intensity: float = 1.0) -> Dict[str, Any]:
        """
        VRM制御コマンドを生成

        Args:
            expression: 表情名
            intensity: 表情の強度（0.0～1.0）

        Returns:
            VRM制御コマンド
            {
                "command": str,  # コマンドタイプ（"setExpression", "playAnimation"等）
                "params": Dict[str, Any]  # パラメータ
            }

        TODO:
        - VRMライブラリに応じたコマンド形式生成
        - BlendShapeの制御パラメータ生成
        - モーフターゲットの重み計算
        """
        logger.info(f"VRM制御コマンド生成（骨組み）: {expression}, intensity={intensity}")

        # TODO: 実装
        # プレースホルダー
        return {
            "command": "setExpression",
            "params": {"expression": expression, "intensity": intensity},
        }

    async def process(
        self,
        emotion: str,
        text: Optional[str] = None,
        audio_duration: Optional[float] = None,
        context: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        キャラクター制御のメインエントリーポイント

        Args:
            emotion: 感情タグ
            text: 発話テキスト（リップシンク用、オプション）
            audio_duration: 音声の長さ（リップシンク用、オプション）
            context: コンテキスト情報（オプション）

        Returns:
            制御コマンド
            {
                "expression": Dict[str, Any],  # 表情パラメータ
                "animation": str,  # アニメーション名
                "vrm_command": Dict[str, Any],  # VRM制御コマンド
                "lipsync": List[Dict[str, Any]]  # リップシンクデータ（オプション）
            }

        TODO:
        - 感情→表情→VRMコマンドの統合
        - アニメーション選択
        - リップシンクデータ生成（音声がある場合）
        - エラーハンドリング
        - ログ出力
        """
        logger.info(f"CharacterControlAgent処理開始（骨組み）: emotion={emotion}")

        try:
            # TODO: 実装
            # 1. 感情→表情マッピング
            expression_params = self.map_emotion_to_expression(emotion)

            # 2. VRM制御コマンド生成
            vrm_command = self.generate_vrm_command(
                expression_params["expression"], expression_params["intensity"]
            )

            # 3. アニメーション選択
            animation = self.select_animation(emotion, context)

            # 4. リップシンクデータ生成（音声がある場合）
            lipsync_data = []
            if text and audio_duration:
                lipsync_data = self.generate_lipsync_data(audio_duration, text)

            return {
                "expression": expression_params,
                "animation": animation,
                "vrm_command": vrm_command,
                "lipsync": lipsync_data,
            }

        except Exception as e:
            logger.error(f"CharacterControlAgent処理エラー（骨組み）: {e}", exc_info=True)
            # TODO: エラーハンドリング
            # エラー時はデフォルト値を返す（EmotionMappingから取得）
            default_data = EmotionMapping.get_expression_with_intensity("neutral")
            return {
                "expression": {
                    "expression": default_data["expression"],
                    "intensity": default_data["intensity"],
                    "duration": self.DEFAULT_EXPRESSION_DURATION,
                },
                "animation": "idle",
                "vrm_command": {},
                "lipsync": [],
                "error": str(e),
            }
