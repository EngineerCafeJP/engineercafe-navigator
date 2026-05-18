from __future__ import annotations

import base64
import io
import logging
import math
import random
import wave
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

try:
    import numpy as np  # noqa: E402

    AUDIO_ANALYSIS_AVAILABLE = True
except ImportError:
    AUDIO_ANALYSIS_AVAILABLE = False
    logger.warning("numpy not available. Audio-based lip sync will be disabled.")


class CharacterLipSyncMixin:
    def _analyze_audio_data(self, audio_data: str) -> Tuple[float, List[Dict[str, Any]]]:
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
                mouth_shape = self._determine_mouth_shape_simplified(rms, frame_data)

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
            logger.exception("音声データ解析エラー: %s", e)
            raise

    def _determine_mouth_shape_simplified(self, rms: float, frame_data: np.ndarray) -> str:
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
                "リップシンクデータ生成開始: text_length=%d, audio_duration=%s, has_audio_data=%s",
                len(text) if text else 0,
                audio_duration,
                audio_data is not None,
            )

            # 1. 音声データが提供されている場合は音声解析を試行
            if audio_data:
                try:
                    duration, frames = self._analyze_audio_data(audio_data)
                    logger.info(
                        "音声データからリップシンクデータ生成完了: duration=%ss, frames=%d",
                        duration,
                        len(frames),
                    )
                    return frames
                except Exception as e:
                    logger.warning(
                        "音声データ解析に失敗しました: %s. "
                        "テキストベースのフォールバック処理に移行します。",
                        e,
                    )
                    # フォールバック処理に移行

            # 2. フォールバック処理（テキストベース）
            # textの検証
            if not text or not isinstance(text, str) or not text.strip():
                logger.warning(
                    "テキストが空または無効です: text=%s. " "フォールバック実装を使用します。", text
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
                    "audio_durationが未指定のため、文字数から算出: char_count=%d, duration=%ss",
                    char_count,
                    audio_duration,
                )

            # テキストベースのリップシンクデータ生成
            frames = self._generate_visemes_from_text(text, audio_duration)

            logger.info("リップシンクデータ生成完了: frames=%d", len(frames))

            return frames

        except Exception as e:
            logger.exception(
                "リップシンクデータ生成エラー: text_length=%d, audio_duration=%s, error=%s",
                len(text) if text else 0,
                audio_duration,
                e,
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
            current_word_index = (
                math.floor(progress * len(converted_words)) if converted_words else 0
            )
            current_word = (
                converted_words[current_word_index]
                if current_word_index < len(converted_words)
                else ""
            )

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

    def _get_vowel_at_position(self, vowel_map: List[tuple[int, str]], position: int) -> str:
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
