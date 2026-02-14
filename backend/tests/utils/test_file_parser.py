"""File Parser Tests"""

from unittest.mock import MagicMock, patch

import pytest

from utils.file_parser import detect_file_type, parse_markdown, parse_pdf


class TestDetectFileType:
    def test_markdown_md(self):
        assert detect_file_type("readme.md") == "markdown"

    def test_markdown_extension(self):
        assert detect_file_type("doc.markdown") == "markdown"

    def test_pdf(self):
        assert detect_file_type("document.pdf") == "pdf"

    def test_text(self):
        assert detect_file_type("notes.txt") == "text"

    def test_unknown(self):
        assert detect_file_type("image.png") == "unknown"

    def test_case_insensitive(self):
        assert detect_file_type("README.MD") == "markdown"
        assert detect_file_type("DOCUMENT.PDF") == "pdf"


class TestParseMarkdown:
    def test_basic(self):
        """基本的なMarkdownテキスト抽出"""
        md = b"Hello world\n\nThis is a test."
        result = parse_markdown(md)
        assert "Hello world" in result
        assert "This is a test." in result

    def test_headers_links(self):
        """ヘッダー・リンク記法除去"""
        md = b"# Title\n## Subtitle\n[Click here](https://example.com)\n![Alt](img.png)"
        result = parse_markdown(md)
        assert "# " not in result
        assert "## " not in result
        assert "Click here" in result
        assert "https://example.com" not in result
        assert "Alt" in result
        assert "img.png" not in result

    def test_bold_italic(self):
        """強調記法除去"""
        md = b"**bold** and *italic* text"
        result = parse_markdown(md)
        assert "bold" in result
        assert "italic" in result
        assert "**" not in result
        assert result.count("*") == 0

    def test_code_blocks(self):
        """コードブロック除去"""
        md = b"Before\n```python\nprint('hello')\n```\nAfter"
        result = parse_markdown(md)
        assert "Before" in result
        assert "After" in result
        assert "```" not in result

    def test_inline_code(self):
        """インラインコード記法除去"""
        md = b"Use `pip install` command"
        result = parse_markdown(md)
        assert "pip install" in result
        assert "`" not in result


class TestParsePdf:
    def test_basic(self):
        """PDFテキスト抽出（モック）"""
        mock_page = MagicMock()
        mock_page.get_text.return_value = "PDF page content"

        mock_doc = MagicMock()
        mock_doc.__iter__ = MagicMock(return_value=iter([mock_page]))
        mock_doc.close = MagicMock()

        with patch("utils.file_parser.pymupdf") as mock_pymupdf:
            mock_pymupdf.open.return_value = mock_doc
            mock_pymupdf.FileDataError = Exception

            result = parse_pdf(b"fake pdf content")

        assert "PDF page content" in result

    def test_invalid_pdf(self):
        """無効なPDFでValueError"""

        class FakeFileDataError(Exception):
            pass

        with patch("utils.file_parser.pymupdf") as mock_pymupdf:
            mock_pymupdf.FileDataError = FakeFileDataError
            mock_pymupdf.open.side_effect = FakeFileDataError("bad PDF")

            with pytest.raises(ValueError, match="Invalid PDF"):
                parse_pdf(b"not a real pdf")
