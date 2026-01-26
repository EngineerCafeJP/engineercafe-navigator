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

    def generate_vrm_command(
        self, expression: str, intensity: float = 1.0, animation: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        VRM制御コマンドを生成

        Args:
            expression: 表情名（"neutral", "happy", "sad"等）
            intensity: 表情の強度（0.0～1.0）
            animation: アニメーション名（オプション、humanoid.poseに使用）

        Returns:
            VRM制御コマンド
            {
                "expressions": [
                    {
                        "name": str,  # 表情名またはViseme名
                        "value": float,  # 強度（0.0-1.0）
                        "transition": float  # 遷移時間（秒）
                    }
                ],
                "lookAt": {
                    "position": {"x": float, "y": float, "z": float},
                    "target": str  # "camera"等
                },
                "humanoid": {
                    "pose": Optional[str]  # ポーズ名（アニメーション名から決定）
                }
            }

        Examples:
            >>> agent = CharacterControlAgent()
            >>> cmd = agent.generate_vrm_command("happy", 0.8)
            >>> cmd["expressions"][0]["name"]
            'happy'
            >>> cmd["expressions"][0]["value"]
            0.8
        """
        try:
            logger.info(
                f"VRM制御コマンド生成開始: expression={expression}, "
                f"intensity={intensity}, animation={animation}"
            )

            # 1. 入力検証
            if not expression or not isinstance(expression, str):
                logger.warning(
                    f"無効な表情名: {expression}, 型: {type(expression).__name__}. "
                    "デフォルト値'neutral'を使用します。"
                )
                expression = self.DEFAULT_EXPRESSION

            # intensityの範囲チェック
            if not isinstance(intensity, (int, float)):
                logger.warning(
                    f"無効な強度値: {intensity}, 型: {type(intensity).__name__}. "
                    "デフォルト値1.0を使用します。"
                )
                intensity = self.DEFAULT_INTENSITY
            else:
                intensity = max(0.0, min(1.0, float(intensity)))

            # 2. メイン表情をexpressions配列に追加
            expressions: List[Dict[str, Any]] = [
                {
                    "name": expression,
                    "value": intensity,
                    "transition": self.DEFAULT_EXPRESSION_DURATION,
                }
            ]

            # 3. lookAt設定を追加（デフォルトでカメラを向く）
            look_at: Dict[str, Any] = {
                "position": {"x": 0, "y": 1.5, "z": 2.0},
                "target": "camera",
            }

            # 4. humanoidポーズ設定（アニメーション名から決定）
            humanoid: Dict[str, Any] = {"pose": animation if animation else None}

            vrm_control: Dict[str, Any] = {
                "expressions": expressions,
                "lookAt": look_at,
                "humanoid": humanoid,
            }

            logger.info(
                f"VRM制御コマンド生成完了: expression={expression}, "
                f"intensity={intensity}, expressions_count={len(expressions)}"
            )

            return vrm_control

        except Exception as e:
            logger.error(
                f"VRM制御コマンド生成エラー: expression={expression}, "
                f"intensity={intensity}, error={e}",
                exc_info=False,  # exc_info=True を False に変更してログフォーマッターの max() 呼び出しを回避
            )
            # エラー時はデフォルト値を返す
            return {
                "expressions": [
                    {
                        "name": self.DEFAULT_EXPRESSION,
                        "value": self.DEFAULT_INTENSITY,
                        "transition": self.DEFAULT_EXPRESSION_DURATION,
                    }
                ],
                "lookAt": {
                    "position": {"x": 0, "y": 1.5, "z": 2.0},
                    "target": "camera",
                },
                "humanoid": {"pose": None},
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
            制御コマンド（出力フォーマット例に合わせた構造）
            {
                "action": str,  # アクションタイプ（"speak"）
                "vrm_control": {
                    "expressions": [
                        {
                            "name": str,  # 表情名またはViseme名
                            "value": float,  # 強度（0.0-1.0）
                            "transition": float  # 遷移時間（秒）
                        }
                    ],
                    "lookAt": {
                        "position": {"x": float, "y": float, "z": float},
                        "target": str
                    },
                    "humanoid": {
                        "pose": Optional[str]  # ポーズ名
                    }
                },
                "text": Optional[str]  # 発話テキスト
            }

        Examples:
            >>> agent = CharacterControlAgent()
            >>> result = await agent.process("happy", "こんにちは", 1.0)
            >>> result["action"]
            'speak'
            >>> "vrm_control" in result
            True
        """
        logger.info(
            f"CharacterControlAgent処理開始: emotion={emotion}, "
            f"text_length={len(text) if text else 0}, "
            f"audio_duration={audio_duration}"
        )

        try:
            # 1. 感情→表情マッピング
            expression_params = self.map_emotion_to_expression(emotion)
            mapped_expression = expression_params["expression"]
            expression_intensity = expression_params["intensity"]

            # 2. アニメーション選択
            animation = self.select_animation(emotion, context)

            # 3. VRM制御コマンド生成（アニメーション名も渡す）
            vrm_control = self.generate_vrm_command(
                mapped_expression, expression_intensity, animation
            )

            # 4. リップシンクデータ生成（音声がある場合）
            lipsync_data: List[Dict[str, Any]] = []
            if text and audio_duration:
                try:
                    lipsync_data = self.generate_lipsync_data(audio_duration, text)

                    # 5. リップシンクデータからVisemeを抽出してvrm_control.expressionsに追加
                    if lipsync_data and len(lipsync_data) > 0:
                        try:
                            viseme_expression = EmotionMapping.extract_viseme_from_lipsync_data(
                                lipsync_data
                            )

                            if viseme_expression:
                                vrm_control["expressions"].append(viseme_expression)

                                logger.info(
                                    f"Viseme追加: viseme={viseme_expression['name']}, "
                                    f"value={viseme_expression['value']}"
                                )
                        except Exception as viseme_error:
                            logger.warning(
                                f"Viseme追加エラー: {viseme_error}, "
                                "Visemeなしで続行します。",
                                exc_info=True,
                            )
                except Exception as lipsync_error:
                    logger.warning(
                        f"リップシンクデータ生成エラー: {lipsync_error}, "
                        "リップシンクなしで続行します。",
                        exc_info=True,
                    )

            # 6. humanoid.poseをアニメーション名から設定
            if animation:
                vrm_control["humanoid"]["pose"] = animation

            # 7. 出力構造を生成（出力フォーマット例に合わせた構造）
            result: Dict[str, Any] = {
                "action": "speak",
                "vrm_control": vrm_control,
            }

            # textパラメータがある場合は追加
            if text:
                result["text"] = text

            logger.info(
                f"CharacterControlAgent処理完了: action={result['action']}, "
                f"expressions_count={len(vrm_control['expressions'])}, "
                f"animation={animation}"
            )

            return result

        except Exception as e:
            logger.error(
                f"CharacterControlAgent処理エラー: emotion={emotion}, "
                f"text_length={len(text) if text else 0}, error={e}",
                exc_info=True,
            )
            # エラー時はデフォルト値を返す
            default_data = EmotionMapping.get_expression_with_intensity("neutral")
            default_vrm_control = self.generate_vrm_command(
                default_data["expression"], default_data["intensity"], "idle"
            )

            return {
                "action": "speak",
                "vrm_control": default_vrm_control,
                "text": text if text else None,
                "error": str(e),
            }
