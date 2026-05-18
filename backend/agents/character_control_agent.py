"""
CharacterControlAgent

VRMキャラクターの表情・モーションを制御するエージェント。
応答テキストの感情タグに基づいて、適切な表情やアニメーションを指示。

主な機能:
- 感情→表情マッピング
- VRM制御コマンド生成
- アニメーション選択
- リップシンクデータ生成（音声データ対応、テキストベースフォールバック）
- 日本語/英語対応の口の形状検出

依存関係:
- numpy>=1.24.0,<2.0: 音声データ解析に使用
- scipy>=1.10.0: 音声データ解析に使用
- pykakasi>=1.2.0: 漢字→読みカナ変換に使用

参考:
- docs/migration/agents/character-control-agent/README.md
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
from typing import Dict, Any, Optional, List

from backend.agents.character_control.lipsync import (
    AUDIO_ANALYSIS_AVAILABLE,  # noqa: F401
    CharacterLipSyncMixin,
)
from backend.utils.emotion_mapping import EmotionMapping  # noqa: E402
from backend.utils.kanji_converter import KanjiConverter  # noqa: E402

logger = logging.getLogger(__name__)


class CharacterControlAgent(CharacterLipSyncMixin):
    """
    CharacterControlAgent

    VRMキャラクターの表情・モーション・リップシンクを制御するエージェント。
    MainWorkflow ではオプション機能として初期化されますが、現時点では
    ワークフローグラフのノードには組み込まれていません。
    将来的な統合に備えて利用可能な状態を維持します。

    主な機能:
    - 感情タグから表情パラメータへのマッピング
    - VRM制御コマンドの生成
    - アニメーション選択
    - リップシンクデータ生成（音声データ解析またはテキストベース）

    リップシンク生成:
    - 音声データ（Base64エンコードWAV）が提供された場合、音声解析から生成
    - 音声データがない場合、テキストから口の形状を推定
    - audio_durationが未指定の場合、文字数から自動計算（CHAR_DURATION_SECONDS使用）
    """

    DEFAULT_EXPRESSION: str = EmotionMapping.DEFAULT_EXPRESSION
    DEFAULT_INTENSITY: float = EmotionMapping.DEFAULT_INTENSITY
    DEFAULT_EXPRESSION_DURATION: float = EmotionMapping.DEFAULT_EXPRESSION_DURATION
    DEFAULT_ANIMATION: str = EmotionMapping.DEFAULT_ANIMATION
    CHAR_DURATION_SECONDS: float = 0.15  # 読みカナ1文字あたりの長さ（秒）

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

        self._lip_sync_cache: dict[tuple[str, float], List[Dict[str, Any]]] = {}

        logger.info(
            "CharacterControlAgent初期化完了: "
            "expression=%s, intensity=%s, "
            "expression_duration=%s, animation=%s",
            self.current_expression,
            self.current_intensity,
            self.current_expression_duration,
            self.current_animation,
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
                    "無効な感情値: %s, 型: %s. デフォルト値'neutral'を使用します。",
                    emotion,
                    type(emotion).__name__,
                )
                emotion = "neutral"

            # 1. 感情→VRM表情と強度の取得
            # EmotionMappingを使用して感情を標準VRM表情と強度にマッピング
            expression_data = EmotionMapping.get_expression_with_intensity(emotion)
            mapped_expression = expression_data["expression"]
            intensity = expression_data["intensity"]

            # Mastra版と同じく、低強度の感情は表情をneutralへ寄せる。
            if intensity < 0.3:
                mapped_expression = "neutral"

            # 2. durationの設定（デフォルト値を使用）
            duration = self.DEFAULT_EXPRESSION_DURATION

            logger.info(
                "感情→表情マッピング: '%s' -> expression='%s', intensity=%s, duration=%ss",
                emotion,
                mapped_expression,
                intensity,
                duration,
            )

            return {
                "expression": mapped_expression,
                "intensity": intensity,
                "duration": duration,
            }

        except Exception as e:
            logger.exception(
                "感情→表情マッピングエラー: emotion=%s, error=%s",
                emotion,
                e,
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
            アニメーション名（SupportedAnimation: idle, greeting, thinking, talking 等）

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
            logger.info("アニメーション選択開始: emotion=%s", emotion)

            # 1. emotionのバリデーション
            if not emotion or not isinstance(emotion, str):
                logger.warning(
                    "無効な感情値: %s, 型: %s. デフォルト値'%s'を使用します。",
                    emotion,
                    type(emotion).__name__,
                    self.DEFAULT_ANIMATION,
                )
                return self.DEFAULT_ANIMATION

            # 2. EmotionMappingを使用してアニメーション名を取得
            animation = EmotionMapping.get_animation_for_emotion(emotion)

            logger.info("アニメーション選択完了: emotion=%s, animation=%s", emotion, animation)

            return animation

        except Exception as e:
            logger.exception(
                "アニメーション選択エラー: emotion=%s, error=%s",
                emotion,
                e,
            )
            # エラー時はデフォルト値を返す
            return self.DEFAULT_ANIMATION

    def combine_emotions(self, emotions: List[str]) -> str:
        """
        複数の感情を統合

        Args:
            emotions: 感情タグのリスト

        Returns:
            統合された感情タグ

        """
        logger.info("感情統合: %s", emotions)

        normalized = [str(emotion).strip().lower() for emotion in emotions if str(emotion).strip()]
        if not normalized:
            return "neutral"

        positive = {"happy", "excited", "relaxed"}
        negative = {"sad", "angry", "confused"}
        if any(emotion in positive for emotion in normalized) and any(
            emotion in negative for emotion in normalized
        ):
            return "neutral"

        priority = {
            "angry": 90,
            "sad": 80,
            "confused": 70,
            "surprised": 65,
            "excited": 60,
            "happy": 50,
            "relaxed": 40,
            "neutral": 10,
        }
        return max(normalized, key=lambda emotion: priority.get(emotion, 0))

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
                "VRM制御コマンド生成開始: expression=%s, intensity=%s, animation=%s",
                expression,
                intensity,
                animation,
            )

            # 1. 入力検証
            if not expression or not isinstance(expression, str):
                logger.warning(
                    "無効な表情名: %s, 型: %s. デフォルト値'neutral'を使用します。",
                    expression,
                    type(expression).__name__,
                )
                expression = self.DEFAULT_EXPRESSION

            # intensityの範囲チェック
            if not isinstance(intensity, (int, float)):
                logger.warning(
                    "無効な強度値: %s, 型: %s. デフォルト値1.0を使用します。",
                    intensity,
                    type(intensity).__name__,
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
                "VRM制御コマンド生成完了: expression=%s, intensity=%s, expressions_count=%d",
                expression,
                intensity,
                len(expressions),
            )

            return vrm_control

        except Exception as e:
            logger.error(
                "VRM制御コマンド生成エラー: expression=%s, intensity=%s, error=%s",
                expression,
                intensity,
                e,
                # False に変更: ログフォーマッターの max() 回避
                exc_info=False,
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
            制御コマンド（greetings.json形式）
            {
                "name": str,  # アニメーション名（select_animationの戻り値）
                "duration": int,  # 総時間（ミリ秒）
                "keyframes": [
                    {
                        "time": int,  # ミリ秒
                        "bones": {},  # 将来拡張用
                        "expressions": {表情名: 強度, Viseme名: 強度}
                    }
                ],
                "text": Optional[str]  # 発話テキスト
            }

        Examples:
            >>> agent = CharacterControlAgent()
            >>> result = await agent.process("happy", "こんにちは", 1.0)
            >>> result["name"]
            'greeting'
            >>> "keyframes" in result
            True

        実行例:
            emotion="describing", text="こんにちは、エンジニアカフェへようこそ。"の場合:

            処理フロー:
            1. 感情マッピング: "describing" -> expression="neutral", intensity=0.8
            2. アニメーション選択: "describing" -> animation="idle"
            3. VRM制御コマンド生成: neutral表情（強度0.8）を生成
            4. リップシンクデータ生成:
               - audio_duration未指定のため、文字数から自動計算（20文字 × 0.15秒 = 3.0秒）
               - テキストから口の形状を推定（日本語対応）
            5. Viseme抽出: リップシンクデータからViseme（"oh"など）を抽出して追加

            結果:
            {
                "name": "idle",
                "duration": 3000,
                "keyframes": [
                    {"time": 0, "bones": {}, "expressions": {"neutral": 0.8, "oh": 0.5}},
                    ...
                ],
                "text": "こんにちは、エンジニアカフェへようこそ。"
            }

        実行手順:
            # テストスクリプトを使用
            python -m backend.tests.utils.test_process_output

            # Pythonコードから直接実行
            import asyncio
            from backend.agents.character_control_agent import CharacterControlAgent

            async def main():
                agent = CharacterControlAgent()
                result = await agent.process(
                    emotion="describing",
                    text="こんにちは、エンジニアカフェへようこそ。"
                )
                print(result)

            asyncio.run(main())
        """
        logger.info(
            "CharacterControlAgent処理開始: emotion=%s, text_length=%d, audio_duration=%s",
            emotion,
            len(text) if text else 0,
            audio_duration,
        )

        try:
            # 1. 感情→表情マッピング
            expression_params = self.map_emotion_to_expression(emotion)
            mapped_expression = expression_params["expression"]
            expression_intensity = expression_params["intensity"]

            # 2. アニメーション選択
            animation = self.select_animation(emotion, context)

            # 3. リップシンクデータ生成（テキストがある場合、先に生成して表情遷移時間を調整）
            lipsync_data: List[Dict[str, Any]] = []
            has_lipsync = False
            if text:
                try:
                    # contextからaudio_dataを取得（可能な場合）
                    audio_data = None
                    if context and isinstance(context, dict):
                        audio_data = context.get("audio_data") or context.get("audioData")

                    lipsync_data = self.generate_lipsync_data(
                        text=text,
                        audio_duration=audio_duration,
                        audio_data=audio_data,
                    )

                    if lipsync_data and len(lipsync_data) > 0:
                        has_lipsync = True
                        logger.info("リップシンクデータ生成完了: frames=%d", len(lipsync_data))
                except Exception as lipsync_error:
                    logger.warning(
                        "リップシンクデータ生成エラー: %s, リップシンクなしで続行します。",
                        lipsync_error,
                        exc_info=True,
                    )

            # 4. VRM制御コマンド生成（リップシンクがある場合は表情遷移時間を短くする）
            expression_transition = 0.1 if has_lipsync else self.DEFAULT_EXPRESSION_DURATION
            vrm_control = self.generate_vrm_command(
                mapped_expression, expression_intensity, animation
            )
            if vrm_control["expressions"] and len(vrm_control["expressions"]) > 0:
                vrm_control["expressions"][0]["transition"] = expression_transition

            # 5. keyframes構築（greetings.json形式）
            keyframes: List[Dict[str, Any]] = []

            base_expressions: Dict[str, float] = {}
            if mapped_expression == "neutral":
                base_expressions["neutral"] = 1.0
            else:
                base_expressions[mapped_expression] = expression_intensity
                base_expressions["neutral"] = 1.0 - expression_intensity

            if has_lipsync and lipsync_data:
                prev_viseme: Optional[str] = None
                viseme_names = {"aa", "ih", "ou", "ee", "oh"}

                for frame in lipsync_data:
                    expressions = dict(base_expressions)
                    mouth_shape = frame.get("mouthShape", "Closed")
                    mouth_open = min(1.0, max(0.0, float(frame.get("mouthOpen", 0.0))))
                    viseme = EmotionMapping.VISEME_MAPPING.get(mouth_shape, "neutral")

                    if prev_viseme is not None and prev_viseme != viseme:
                        expressions[prev_viseme] = 0.0

                    if viseme in viseme_names:
                        expressions[viseme] = mouth_open
                        prev_viseme = viseme
                    else:
                        prev_viseme = None

                    keyframes.append(
                        {
                            "time": int(frame["time"] * 1000),
                            "bones": {},
                            "expressions": expressions,
                        }
                    )

                final_time = int(lipsync_data[-1]["time"] * 1000) + 50
                reset_expressions: Dict[str, float] = {}
                for expression_name in base_expressions.keys():
                    reset_expressions[expression_name] = 0.0
                for viseme_name in viseme_names:
                    reset_expressions[viseme_name] = 0.0
                keyframes.append(
                    {
                        "time": final_time,
                        "bones": {},
                        "expressions": reset_expressions,
                    }
                )
            else:
                keyframes.append(
                    {
                        "time": 0,
                        "bones": {},
                        "expressions": base_expressions,
                    }
                )

            duration = keyframes[-1]["time"] if keyframes else 0
            if duration == 0 and keyframes:
                duration = 2000

            # 5. 出力構造を生成（greetings.json形式）
            result: Dict[str, Any] = {
                "name": animation if animation else "idle",
                "duration": duration,
                "keyframes": keyframes,
            }

            if text:
                result["text"] = text

            logger.info(
                "CharacterControlAgent処理完了: "
                "name=%s, keyframes_count=%d, "
                "duration=%d, lipsync_frames=%d",
                result["name"],
                len(keyframes),
                duration,
                len(lipsync_data) if has_lipsync else 0,
            )

            return result

        except Exception as e:
            logger.exception(
                "CharacterControlAgent処理エラー: emotion=%s, text_length=%d, error=%s",
                emotion,
                len(text) if text else 0,
                e,
            )
            default_data = EmotionMapping.get_expression_with_intensity("neutral")
            default_expr = default_data["expression"]
            default_int = default_data["intensity"]
            default_expressions: Dict[str, float] = (
                {"neutral": 1.0}
                if default_expr == "neutral"
                else {
                    default_expr: default_int,
                    "neutral": 1.0 - default_int,
                }
            )
            default_keyframes = [
                {
                    "time": 0,
                    "bones": {},
                    "expressions": default_expressions,
                }
            ]
            result_error: Dict[str, Any] = {
                "name": "idle",
                "duration": 2000,
                "keyframes": default_keyframes,
                "error": str(e),
            }
            if text:
                result_error["text"] = text
            return result_error


async def main():
    """
    CharacterControlAgentのprocessメソッドを実行するメイン関数

    使用例:
        python -m backend.agents.character_control_agent "こんにちは、エンジニアカフェへようこそ。"
        python -m backend.agents.character_control_agent "Hello" --emotion "happy"
        python -m backend.agents.character_control_agent "Hello" -e "happy" -d 2.0

    出力例（上記1つ目のコマンド実行時）:
        {
          "name": "idle",
          "duration": 3000,
          "text": "こんにちは、エンジニアカフェへようこそ。",
          "keyframes": [
            {"time": 0, "bones": {}, "expressions": {"neutral": 1.0, "oh": 0.33}},
            {"time": 50, "bones": {}, "expressions": {"neutral": 1.0, "oh": 0.49}},
            ...
          ]
        }
    """
    parser = argparse.ArgumentParser(
        description="CharacterControlAgentのprocessメソッドを実行",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
使用例:
  %(prog)s "こんにちは、エンジニアカフェへようこそ。"
  %(prog)s "Hello" --emotion "happy"
  %(prog)s "Hello" -e "happy" -d 2.0
        """,
    )
    parser.add_argument(
        "text",
        type=str,
        metavar="TEXT",
        help="発話テキスト（必須）",
    )
    parser.add_argument(
        "-e",
        "--emotion",
        type=str,
        default=CharacterControlAgent.DEFAULT_EXPRESSION,
        help=f"感情タグ（デフォルト: {CharacterControlAgent.DEFAULT_EXPRESSION}）",
    )
    parser.add_argument(
        "-d",
        "--duration",
        type=float,
        default=None,
        metavar="SECONDS",
        help="音声の長さ（秒）。未指定の場合は文字数から自動計算",
    )

    args = parser.parse_args()

    # ログレベルの設定
    logging.basicConfig(
        level=logging.INFO,
        format="%(levelname)s - %(message)s",
    )

    try:
        # CharacterControlAgentのインスタンスを作成
        agent = CharacterControlAgent()

        # パラメータ
        emotion = args.emotion
        text = args.text
        audio_duration = args.duration

        print("=" * 80, file=sys.stderr)
        print("CharacterControlAgent.process() 実行", file=sys.stderr)
        print("=" * 80, file=sys.stderr)
        print(f"emotion: {emotion}", file=sys.stderr)
        print(f"text: {text}", file=sys.stderr)
        if audio_duration is not None:
            print(f"audio_duration: {audio_duration}", file=sys.stderr)
        else:
            print("audio_duration: 自動計算", file=sys.stderr)
        print("", file=sys.stderr)

        # processメソッドを実行
        result = await agent.process(
            emotion=emotion,
            text=text,
            audio_duration=audio_duration,
        )

        # 結果をJSON形式で出力
        print(json.dumps(result, ensure_ascii=False, indent=2))

        return 0

    except KeyboardInterrupt:
        print("\n中断されました", file=sys.stderr)
        return 130
    except Exception as e:
        print(f"エラーが発生しました: {e}", file=sys.stderr)
        import traceback

        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
