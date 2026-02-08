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
import base64
import io
import json
import logging
import math
import random
import sys
import wave
from typing import Dict, Any, Optional, List, Tuple

logger = logging.getLogger(__name__)

try:
    import numpy as np  # noqa: E402
    AUDIO_ANALYSIS_AVAILABLE = True
except ImportError:
    AUDIO_ANALYSIS_AVAILABLE = False
    logger.warning(
        "numpy not available. Audio-based lip sync will be disabled."
    )

from backend.utils.emotion_mapping import EmotionMapping  # noqa: E402
from backend.utils.kanji_converter import KanjiConverter  # noqa: E402

# TODO: 実装時に必要なインポート
# from llm.openrouter import OpenRouterProvider
# from llm.models import get_model_config


class CharacterControlAgent:
    """
    CharacterControlAgent

    VRMキャラクターの表情・モーション・リップシンクを制御するエージェント。

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

    def _analyze_audio_data(
        self, audio_data: str
    ) -> Tuple[float, List[Dict[str, Any]]]:
        """
        Base64エンコードされた音声データを解析してリップシンクデータを生成

        Args:
            audio_data: Base64エンコードされたWAV形式の音声データ

        Returns:
            (duration, frames) のタプル
            - duration: 音声の長さ（秒）
            - frames: リップシンクフレームのリスト

        Raises:
            Exception: 音声解析に失敗した場合
        """
        if not AUDIO_ANALYSIS_AVAILABLE:
            raise ImportError("numpy or scipy not available")

        try:
            # Base64文字列をデコード
            audio_bytes = base64.b64decode(audio_data)

            # WAVファイルとして読み込み
            audio_io = io.BytesIO(audio_bytes)
            with wave.open(audio_io, "rb") as wav_file:
                sample_rate = wav_file.getframerate()
                n_channels = wav_file.getnchannels()
                n_frames = wav_file.getnframes()
                sample_width = wav_file.getsampwidth()

                # 音声データを読み込み
                audio_frames = wav_file.readframes(n_frames)

            # バイナリデータをnumpy配列に変換
            if sample_width == 1:
                # 8-bit unsigned
                audio_array = np.frombuffer(audio_frames, dtype=np.uint8)
                audio_array = (audio_array.astype(np.float32) - 128) / 128.0
            elif sample_width == 2:
                # 16-bit signed
                audio_array = np.frombuffer(audio_frames, dtype=np.int16)
                audio_array = audio_array.astype(np.float32) / 32768.0
            else:
                raise ValueError(f"Unsupported sample width: {sample_width}")

            # モノラルに変換（複数チャンネルの場合）
            if n_channels > 1:
                audio_array = audio_array.reshape(-1, n_channels)
                audio_array = np.mean(audio_array, axis=1)

            duration = len(audio_array) / sample_rate

            # フレーム間隔（0.05秒）
            frame_interval = 0.05
            frame_count = math.floor(duration / frame_interval)
            frames: List[Dict[str, Any]] = []

            # 各フレームを処理
            for i in range(frame_count):
                start_sample = int(i * frame_interval * sample_rate)
                end_sample = int((i + 1) * frame_interval * sample_rate)
                end_sample = min(end_sample, len(audio_array))

                if start_sample >= len(audio_array):
                    break

                # フレームデータを取得
                frame_data = audio_array[start_sample:end_sample]

                if len(frame_data) == 0:
                    continue

                # RMS音量を計算
                rms = np.sqrt(np.mean(frame_data**2))

                # 簡易的な口の形状を決定
                mouth_shape = self._determine_mouth_shape_simplified(
                    rms, frame_data
                )

                frames.append(
                    {
                        "time": i * frame_interval,
                        "volume": min(rms * 10, 1.0),
                        "mouthOpen": min(rms * 15, 1.0),
                        "mouthShape": mouth_shape,
                    }
                )

            return (duration, frames)

        except Exception as e:
            logger.error(f"音声データ解析エラー: {e}", exc_info=True)
            raise

    def _determine_mouth_shape_simplified(
        self, rms: float, frame_data: np.ndarray
    ) -> str:
        """
        簡易的な口の形状を決定（音量と分散ベース）

        Args:
            rms: RMS音量
            frame_data: フレームの音声データ

        Returns:
            口の形状（"A", "I", "U", "E", "O", "Closed"）
        """
        if rms < 0.01:
            return "Closed"

        # 簡易的な分散を計算
        sample_points = min(4, len(frame_data))
        step = max(1, len(frame_data) // sample_points)
        sampled = frame_data[::step][:sample_points]

        variance = np.var(np.abs(sampled))

        # 簡易的なヒューリスティック
        if rms > 0.1:
            if variance > 0.05:
                return "A"  # 高エネルギー、高分散
            elif variance > 0.02:
                return "E"  # 高エネルギー、中分散
            else:
                return "I"  # 高エネルギー、低分散
        else:
            if variance > 0.02:
                return "O"  # 中エネルギー、高分散
            else:
                return "U"  # 中エネルギー、低分散

    def generate_lipsync_data(
        self,
        text: str,
        audio_duration: Optional[float] = None,
        audio_data: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """
        リップシンクデータを生成

        音声データが提供されている場合は音声解析を優先し、
        提供されていない場合や解析に失敗した場合はテキストベースの生成にフォールバックします。

        Args:
            text: 発話テキスト（必須）
            audio_duration: 音声の長さ（秒）。音声データが提供されない場合に使用。
                未指定の場合は文字数から自動計算（CHAR_DURATION_SECONDS使用）
            audio_data: Base64エンコードされたWAV形式の音声データ（オプション）。
                提供された場合、音声解析からリップシンクデータを生成

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

        Note:
            - 音声データ解析にはnumpy（1.x系）とscipyが必要です
            - 日本語テキストの場合、漢字は自動的に読みカナに変換されます
            - 日本語の「段」行（あ段、い段、う段、え段、お段）に対応
            - 日本語の「ん」「ン」は"Closed"として扱われます

        Examples:
            >>> agent = CharacterControlAgent()
            >>> # テキストベース（audio_duration指定）
            >>> data = agent.generate_lipsync_data("Hello", audio_duration=1.0)
            >>> len(data) > 0
            True
            >>> data[0]["mouthShape"] in ["A", "I", "U", "E", "O", "Closed"]
            True
            >>> # テキストベース（audio_duration自動計算）
            >>> data = agent.generate_lipsync_data("Hello")
            >>> len(data) > 0
            True
            >>> # 音声データベース（Base64エンコードWAV）
            >>> data = agent.generate_lipsync_data("Hello", audio_data="UklGRiQAAABXQVZF...")
            >>> len(data) > 0
            True
        """
        try:
            logger.info(
                f"リップシンクデータ生成開始: text_length={len(text) if text else 0}, "
                f"audio_duration={audio_duration}, has_audio_data={audio_data is not None}"
            )

            # 1. 音声データが提供されている場合は音声解析を試行
            if audio_data:
                try:
                    duration, frames = self._analyze_audio_data(audio_data)
                    logger.info(
                        f"音声データからリップシンクデータ生成完了: "
                        f"duration={duration}s, frames={len(frames)}"
                    )
                    return frames
                except Exception as e:
                    logger.warning(
                        f"音声データ解析に失敗しました: {e}. "
                        "テキストベースのフォールバック処理に移行します。"
                    )
                    # フォールバック処理に移行

            # 2. フォールバック処理（テキストベース）
            # textの検証
            if not text or not isinstance(text, str) or not text.strip():
                logger.warning(
                    f"テキストが空または無効です: text={text}. "
                    "フォールバック実装を使用します。"
                )
                fallback_duration = audio_duration if audio_duration and audio_duration > 0 else 1.0
                return self._generate_fallback_lipsync(fallback_duration)

            # audio_durationが提供されていない場合は、文字数から算出
            if audio_duration is None or audio_duration <= 0:
                # テキストを読みカナに変換
                converted_text = self._kanji_converter.convert_to_kana(text)
                char_count = len(converted_text)
                audio_duration = char_count * self.CHAR_DURATION_SECONDS
                logger.info(
                    f"audio_durationが未指定のため、文字数から算出: "
                    f"char_count={char_count}, duration={audio_duration}s"
                )

            # テキストベースのリップシンクデータ生成
            frames = self._generate_visemes_from_text(text, audio_duration)

            logger.info(f"リップシンクデータ生成完了: frames={len(frames)}")

            return frames

        except Exception as e:
            logger.error(
                f"リップシンクデータ生成エラー: text_length={len(text) if text else 0}, "
                f"audio_duration={audio_duration}, error={e}",
                exc_info=True,
            )
            # エラー時はフォールバック実装を返す
            fallback_duration = audio_duration if audio_duration and audio_duration > 0 else 1.0
            return self._generate_fallback_lipsync(fallback_duration)

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

        # 漢字を含む場合は読みカナに変換（変換後のテキストの長さを使用するため）
        converted_text = self._kanji_converter.convert_to_kana(text)

        # テキストを単語に分割（空白文字で分割）
        words = converted_text.lower().strip().split()

        # 各単語の母音マッピングを事前計算
        word_vowel_maps: List[List[tuple[int, str]]] = []
        converted_words: List[str] = []  # 変換後の単語を保持
        for word in words:
            # 変換済みテキストなので、_get_vowel_positions_from_word内での変換をスキップ
            # そのため、変換後の単語を直接使用
            converted_word = self._kanji_converter.convert_to_kana(word)
            converted_words.append(converted_word)
            # 変換済みテキストから直接母音を検出（二重変換を避ける）
            vowel_map = self._get_vowel_positions_from_converted_text(converted_word)
            word_vowel_maps.append(vowel_map)

        for i in range(frame_count):
            time = i * frame_interval
            progress = time / duration if duration > 0 else 0

            # 現在の単語を決定
            current_word_index = math.floor(progress * len(converted_words)) if converted_words else 0
            current_word = converted_words[current_word_index] if current_word_index < len(converted_words) else ""

            # 単語内の位置に応じた口の形状を決定
            if current_word and current_word_index < len(word_vowel_maps):
                vowel_map = word_vowel_maps[current_word_index]
                # 単語内の相対位置を計算（0.0-1.0）
                word_progress = (progress * len(converted_words)) - current_word_index
                word_progress = max(0.0, min(1.0, word_progress))
                # 単語内の文字位置を計算（変換後のテキストの長さを使用）
                char_position = math.floor(word_progress * len(current_word))
                char_position = max(0, min(len(current_word) - 1, char_position))
                # その位置に対応する母音を取得
                mouth_shape = self._get_vowel_at_position(vowel_map, char_position)
            else:
                mouth_shape = "Closed"

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

    def _get_vowel_positions_from_word(self, word: str) -> List[tuple[int, str]]:
        """
        単語内の各文字位置に対応する母音のリストを取得

        漢字を含む単語の場合は、KanjiConverterを使用して読みカナに変換してから母音を検出します。
        日本語の場合は、あ段（あかさたな...）→"A"、い段（いきしちに...）→"I"のように
        各行の母音を検出します。

        Args:
            word: 単語（小文字、漢字を含む可能性がある）

        Returns:
            母音の位置と種類のリスト [(位置, 母音), ...]
            例: [(1, "E"), (4, "O")] for "Hello"
            例: [(0, "A"), (1, "I")] for "かい"（か→A、い→I）
        """
        if not word:
            return []

        # 漢字を含む場合は読みカナに変換（KanjiConverterを使用）
        processed_word = self._kanji_converter.convert_to_kana(word)
        processed_word_lower = processed_word.lower()

        vowel_positions: List[tuple[int, str]] = []

        # 各文字位置を順番にチェック（実際の母音の位置のみを記録）
        for i, char in enumerate(processed_word_lower):
            vowel = self._detect_vowel_from_char(char)

            if vowel:
                vowel_positions.append((i, vowel))

        return vowel_positions

    def _get_vowel_positions_from_converted_text(
        self, converted_text: str
    ) -> List[tuple[int, str]]:
        """
        変換済みテキスト（カタカナ/ひらがな）から母音の位置を取得

        このメソッドは、既にKanjiConverterで変換済みのテキストを受け取り、
        二重変換を避けるために使用します。

        Args:
            converted_text: 変換済みテキスト（カタカナ/ひらがな）

        Returns:
            母音の位置と種類のリスト [(位置, 母音), ...]
        """
        if not converted_text:
            return []

        processed_word_lower = converted_text.lower()
        vowel_positions: List[tuple[int, str]] = []

        # 各文字位置を順番にチェック（実際の母音の位置のみを記録）
        for i, char in enumerate(processed_word_lower):
            vowel = self._detect_vowel_from_char(char)

            if vowel:
                vowel_positions.append((i, vowel))

        return vowel_positions

    def _detect_vowel_from_char(self, char: str) -> Optional[str]:
        """
        1文字から母音を検出

        英語の母音（a, i, u, e, o）と日本語の各段（あ段、い段、う段、え段、お段）
        を検出します。撥音（ん、ン）の場合は"Closed"を返します。

        Args:
            char: 1文字（英語、ひらがな、カタカナ）

        Returns:
            口の形状（"A", "I", "U", "E", "O", "Closed"）またはNone
        """
        if not char:
            return None

        # 英語の母音を検出
        if char == "a":
            return "A"
        elif char == "i":
            return "I"
        elif char == "u":
            return "U"
        elif char == "e":
            return "E"
        elif char == "o":
            return "O"

        # 「あ」の段
        if char in "あぁかさたなはまやゃらわがざだばぱアァカサタナハマヤャラワガザダバパ":
            return "A"

        # 「い」の段
        if char in "いぃきしちにひみりぎじぢびぴイィキシチニヒミリギジヂビピ":
            return "I"

        # 「う」の段
        if char in "うぅくすつぬふむゆゅるぐずづぶぷウゥクスツヌフムユュルグズヅブプ":
            return "U"

        # 「え」の段
        if char in "えぇけせてねへめれげぜでべぺエェケセテネヘメレゲゼデベペ":
            return "E"

        # 「お」の段
        if char in "おぉこそとのほもよょろをごぞどぼぽオォコソトノホモヨョロヲゴゾドボポ":
            return "O"

        # 撥音（ん、ン）
        if char == "ん" or char == "ン":
            return "Closed"

        return None

    def _get_vowel_at_position(
        self, vowel_map: List[tuple[int, str]], position: int
    ) -> str:
        """
        指定された文字位置に対応する母音を取得

        指定された位置が母音の場合はその母音を返し、
        子音の場合は前の母音を返します（前の母音がない場合は次の母音）。

        Args:
            vowel_map: 母音の位置と種類のリスト
            position: 文字位置

        Returns:
            口の形状（"A", "I", "U", "E", "O", "Closed"）
        """
        if not vowel_map:
            return "Closed"

        # 正確な位置の母音を探す
        for vowel_pos, vowel in vowel_map:
            if vowel_pos == position:
                return vowel

        # 正確な位置が見つからない場合（子音の位置）
        # 前の母音を優先的に探す
        prev_vowel = None
        next_vowel = None

        for vowel_pos, vowel in vowel_map:
            if vowel_pos < position:
                # 前の母音（最も近いものを保持）
                if prev_vowel is None or vowel_pos > prev_vowel[0]:
                    prev_vowel = (vowel_pos, vowel)
            elif vowel_pos > position:
                # 次の母音（最初に見つかったものを保持）
                if next_vowel is None:
                    next_vowel = (vowel_pos, vowel)
                break

        # 前の母音を優先、なければ次の母音
        if prev_vowel:
            return prev_vowel[1]
        elif next_vowel:
            return next_vowel[1]

        return "Closed"

    def _detect_mouth_shape_from_word(self, word: str) -> str:
        """
        単語から口の形状を検出（後方互換性のためのメソッド）

        このメソッドは最初の母音のみを返します。
        時間的な母音の変化が必要な場合は、_get_vowel_positions_from_wordを使用してください。

        Args:
            word: 単語（小文字、漢字を含む可能性がある）

        Returns:
            口の形状（"A", "I", "U", "E", "O", "Closed"）
        """
        vowel_map = self._get_vowel_positions_from_word(word)
        if vowel_map:
            return vowel_map[0][1]  # 最初の母音を返す
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
            3. リップシンクデータ生成（文字数から自動計算）
            4. keyframes構築: 各フレームにtime, bones, expressionsを設定
            
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
                        logger.info(
                            f"リップシンクデータ生成完了: frames={len(lipsync_data)}"
                        )
                except Exception as lipsync_error:
                    logger.warning(
                        f"リップシンクデータ生成エラー: {lipsync_error}, "
                        "リップシンクなしで続行します。",
                        exc_info=True,
                    )

            # 4. keyframes構築（greetings.json形式）
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
                    viseme = EmotionMapping.VISEME_MAPPING.get(
                        mouth_shape, "neutral"
                    )

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

                if prev_viseme is not None:
                    final_time = int(lipsync_data[-1]["time"] * 1000) + 50
                    final_expressions = dict(base_expressions)
                    final_expressions[prev_viseme] = 0.0
                    keyframes.append(
                        {
                            "time": final_time,
                            "bones": {},
                            "expressions": final_expressions,
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

            duration = (
                keyframes[-1]["time"] if keyframes else 0
            )
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
                f"CharacterControlAgent処理完了: name={result['name']}, "
                f"keyframes_count={len(keyframes)}, "
                f"duration={duration}, "
                f"lipsync_frames={len(lipsync_data) if has_lipsync else 0}"
            )

            return result

        except Exception as e:
            logger.error(
                f"CharacterControlAgent処理エラー: emotion={emotion}, "
                f"text_length={len(text) if text else 0}, error={e}",
                exc_info=True,
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
