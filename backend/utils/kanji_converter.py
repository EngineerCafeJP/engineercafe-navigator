"""
漢字→読みカナ変換ユーティリティ

pykakasiを使用して、日本語テキスト内の漢字をカタカナに変換します。

参考:
- pykakasi: https://github.com/miurahr/pykakasi
"""

import logging
from typing import Optional, Any

# pykakasi for kanji to kana conversion
try:
    import pykakasi  # type: ignore
except ImportError:
    pykakasi = None

logger = logging.getLogger(__name__)

# pykakasiが利用できない場合の警告ログ（モジュール読み込み時）
if pykakasi is None:
    logger.warning(
        "pykakasi is not installed. "
        "Kanji to kana conversion will be disabled."
    )


class KanjiConverter:
    """
    漢字→読みカナ変換ユーティリティ

    pykakasiを使用して、日本語テキスト内の漢字をカタカナに変換します。
    VoiceAgentやCharacterControlAgentなど、複数のエージェントで使用可能です。

    Examples:
        >>> converter = KanjiConverter()
        >>> converter.convert_to_kana("会議室")
        'カイギシツ'
        >>> converter.convert_to_kana("エンジニアカフェ")
        'エンジニアカフェ'
        >>> converter.convert_to_kana("Hello World")
        'Hello World'  # 英語はそのまま返す
    """

    def __init__(self):
        """
        初期化

        pykakasiのコンバーターを初期化します。
        pykakasiが利用できない場合は、変換機能は無効になります。
        """
        self._kakasi_converter: Optional[Any] = None

        if pykakasi:
            try:
                kakasi = pykakasi.kakasi()
                kakasi.setMode("J", "K")  # 漢字→ひらがな
                kakasi.setMode("r", "Hepburn")  # ローマ字→ヘボン式
                self._kakasi_converter = kakasi.getConverter()
                logger.info("KanjiConverter初期化完了: 漢字→読みカナ変換が有効")
            except Exception as e:
                logger.warning(
                    f"KanjiConverter初期化エラー: {e}. "
                    "漢字→読みカナ変換は無効になります。"
                )
        else:
            logger.warning(
                "KanjiConverter: pykakasiが利用できません。"
                "漢字→読みカナ変換は無効になります。"
            )

    def convert_to_kana(self, text: str) -> str:
        """
        テキスト内の漢字をカタカナに変換

        Args:
            text: 変換するテキスト（漢字、カタカナ、ひらがな、英語を含む可能性がある）

        Returns:
            変換後のテキスト（漢字がカタカナに変換されたもの）
            エラー時やpykakasiが利用できない場合は、元のテキストをそのまま返します。

        Examples:
            >>> converter = KanjiConverter()
            >>> converter.convert_to_kana("会議室")
            'カイギシツ'
            >>> converter.convert_to_kana("質問")
            'シツモン'
            >>> converter.convert_to_kana("エンジニアカフェ")
            'エンジニアカフェ'
            >>> converter.convert_to_kana("Hello World")
            'Hello World'
        """
        if not text:
            return text

        if not self._kakasi_converter:
            # pykakasiが利用できない場合は元のテキストを返す
            return text

        try:
            # 漢字をひらがなに変換
            converted = self._kakasi_converter.do(text)
            logger.debug(f"漢字変換: '{text}' -> '{converted}'")
            return converted
        except Exception as e:
            logger.warning(
                f"KanjiConverter変換エラー (text: '{text}'): {e}. "
                "元のテキストを使用します。"
            )
            return text

    def is_available(self) -> bool:
        """
        pykakasiが利用可能かどうかを確認

        Returns:
            pykakasiが利用可能な場合はTrue、そうでない場合はFalse
        """
        return self._kakasi_converter is not None
