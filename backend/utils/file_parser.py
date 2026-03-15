"""
ファイルパーサーユーティリティ

.mdと.pdfファイルからテキストを抽出する。
"""

import logging
import re
from typing import Literal

import pymupdf

try:
    from langchain.text_splitter import RecursiveCharacterTextSplitter
except ImportError:  # pragma: no cover - compatibility for newer langchain packages
    from langchain_text_splitters import RecursiveCharacterTextSplitter

logger = logging.getLogger(__name__)


def detect_file_type(filename: str) -> Literal["text", "markdown", "pdf", "unknown"]:
    """ファイル名から種別を判定

    Args:
        filename: ファイル名

    Returns:
        ファイル種別文字列
    """
    lower = filename.lower()
    if lower.endswith(".md") or lower.endswith(".markdown"):
        return "markdown"
    if lower.endswith(".pdf"):
        return "pdf"
    if lower.endswith(".txt"):
        return "text"
    return "unknown"


def parse_markdown(content: bytes) -> str:
    """Markdownからプレーンテキストを抽出

    ヘッダー記号(#)、リンク記法、画像記法、強調記法を除去し、
    プレーンテキストとして返す。

    Args:
        content: Markdownファイルのバイト列

    Returns:
        抽出されたプレーンテキスト
    """
    text = content.decode("utf-8", errors="replace")

    # ヘッダー記号を除去 (# ## ### etc.)
    text = re.sub(r"^#{1,6}\s+", "", text, flags=re.MULTILINE)

    # 画像記法を除去 ![alt](url)
    text = re.sub(r"!\[([^\]]*)\]\([^)]+\)", r"\1", text)

    # リンク記法をテキストのみに [text](url)
    text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)

    # コードブロックを除去（インラインコードより先に処理する）
    text = re.sub(r"```[\s\S]*?```", "", text)

    # インラインコード記法を除去
    text = re.sub(r"`([^`]+)`", r"\1", text)

    # 強調記法を除去 **bold** *italic* __bold__ _italic_
    text = re.sub(r"\*\*([^*]+)\*\*", r"\1", text)
    text = re.sub(r"\*([^*]+)\*", r"\1", text)
    text = re.sub(r"__([^_]+)__", r"\1", text)
    text = re.sub(r"_([^_]+)_", r"\1", text)

    # 水平線を除去
    text = re.sub(r"^[-*_]{3,}\s*$", "", text, flags=re.MULTILINE)

    # 連続空行を1つに
    text = re.sub(r"\n{3,}", "\n\n", text)

    return text.strip()


def parse_pdf(content: bytes) -> str:
    """PDFからテキストを抽出

    PyMuPDFを使用してPDFからテキストを抽出する。

    Args:
        content: PDFファイルのバイト列

    Returns:
        抽出されたテキスト

    Raises:
        ImportError: pymupdfがインストールされていない場合
        ValueError: PDFの解析に失敗した場合
    """
    try:
        doc = pymupdf.open(stream=content, filetype="pdf")
        pages_text = []
        for page in doc:
            page_text = page.get_text()
            if page_text.strip():
                pages_text.append(page_text.strip())
        doc.close()

        if not pages_text:
            raise ValueError("No text content found in PDF")

        return "\n\n".join(pages_text)

    except pymupdf.FileDataError as e:
        raise ValueError(f"Invalid PDF file: {e}") from e


def chunk_text(
    text: str,
    chunk_size: int = 1000,
    chunk_overlap: int = 200,
) -> list[str]:
    """Split text into chunks using recursive character splitting."""
    if not text or not text.strip():
        return []

    normalized_text = text.strip()
    if len(normalized_text) <= chunk_size:
        return [normalized_text]

    splitter = RecursiveCharacterTextSplitter(
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        length_function=len,
        separators=["\n\n", "\n", "。", ".", " ", ""],
    )
    chunks = splitter.split_text(normalized_text)
    return [chunk.strip() for chunk in chunks if chunk.strip()]
