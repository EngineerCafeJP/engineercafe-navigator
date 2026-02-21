"""file_parser ユニットテスト

utils/file_parser.py の全関数に対する包括的なユニットテスト。
detect_file_type, parse_markdown, parse_pdf の各関数について、
正常系・異常系・境界値を網羅する。
"""

from unittest.mock import MagicMock, patch

import pytest

from backend.utils.file_parser import detect_file_type, parse_markdown, parse_pdf


# ---------------------------------------------------------------------------
# detect_file_type
# ---------------------------------------------------------------------------
class TestDetectFileType:
    """detect_file_type のユニットテスト"""

    def test_md_extension_returns_markdown(self):
        """.md 拡張子は 'markdown' を返す"""
        assert detect_file_type("readme.md") == "markdown"

    def test_markdown_extension_returns_markdown(self):
        """.markdown 拡張子は 'markdown' を返す"""
        assert detect_file_type("document.markdown") == "markdown"

    def test_pdf_extension_returns_pdf(self):
        """.pdf 拡張子は 'pdf' を返す"""
        assert detect_file_type("report.pdf") == "pdf"

    def test_txt_extension_returns_text(self):
        """.txt 拡張子は 'text' を返す"""
        assert detect_file_type("notes.txt") == "text"

    def test_unknown_extension_returns_unknown(self):
        """未知の拡張子は 'unknown' を返す"""
        assert detect_file_type("photo.jpg") == "unknown"

    def test_uppercase_md_is_case_insensitive(self):
        """大文字の .MD でも 'markdown' を返す（大文字小文字を区別しない）"""
        assert detect_file_type("README.MD") == "markdown"

    def test_uppercase_pdf_is_case_insensitive(self):
        """大文字の .PDF でも 'pdf' を返す"""
        assert detect_file_type("DOCUMENT.PDF") == "pdf"

    def test_uppercase_txt_is_case_insensitive(self):
        """大文字の .TXT でも 'text' を返す"""
        assert detect_file_type("NOTES.TXT") == "text"

    def test_mixed_case_markdown(self):
        """混合ケースの .Markdown でも 'markdown' を返す"""
        assert detect_file_type("file.Markdown") == "markdown"

    def test_empty_string_returns_unknown(self):
        """空文字列は 'unknown' を返す"""
        assert detect_file_type("") == "unknown"

    def test_no_extension_returns_unknown(self):
        """拡張子なしのファイル名は 'unknown' を返す"""
        assert detect_file_type("Makefile") == "unknown"

    def test_dotfile_returns_unknown(self):
        """ドットファイル(.gitignore等)は 'unknown' を返す"""
        assert detect_file_type(".gitignore") == "unknown"

    def test_double_extension_uses_last(self):
        """二重拡張子は最後の拡張子で判定する"""
        assert detect_file_type("archive.tar.pdf") == "pdf"
        assert detect_file_type("backup.pdf.txt") == "text"

    def test_path_with_directory(self):
        """ディレクトリパスを含むファイル名も正しく判定する"""
        assert detect_file_type("docs/guide.md") == "markdown"
        assert detect_file_type("/home/user/report.pdf") == "pdf"


# ---------------------------------------------------------------------------
# parse_markdown
# ---------------------------------------------------------------------------
class TestParseMarkdown:
    """parse_markdown のユニットテスト"""

    def test_removes_h1_header(self):
        """H1 ヘッダー記号(#)を除去する"""
        content = b"# Title\nBody text"
        result = parse_markdown(content)
        assert "Title" in result
        assert result.startswith("Title")

    def test_removes_h2_header(self):
        """H2 ヘッダー記号(##)を除去する"""
        content = b"## Subtitle"
        result = parse_markdown(content)
        assert result == "Subtitle"

    def test_removes_h3_to_h6_headers(self):
        """H3-H6 ヘッダー記号を除去する"""
        content = b"### H3\n#### H4\n##### H5\n###### H6"
        result = parse_markdown(content)
        assert "###" not in result
        assert "H3" in result
        assert "H4" in result
        assert "H5" in result
        assert "H6" in result

    def test_removes_image_syntax_preserves_alt(self):
        """画像記法 ![alt](url) を除去し、alt テキストを保持する"""
        content = b"![Screenshot](https://example.com/img.png)"
        result = parse_markdown(content)
        assert "Screenshot" in result
        assert "https://example.com/img.png" not in result
        assert "![" not in result

    def test_removes_image_with_empty_alt(self):
        """alt テキストが空の画像記法も正しく除去する"""
        content = b"![](image.png)"
        result = parse_markdown(content)
        assert "image.png" not in result
        assert "![" not in result

    def test_converts_links_to_text(self):
        """リンク記法 [text](url) をテキストのみに変換する"""
        content = b"Visit [Google](https://google.com) for search."
        result = parse_markdown(content)
        assert "Google" in result
        assert "https://google.com" not in result
        assert "[" not in result
        assert "](" not in result

    def test_removes_inline_code_backticks(self):
        """インラインコードのバッククォートを除去する"""
        content = b"Use `pip install` to install packages."
        result = parse_markdown(content)
        assert "pip install" in result
        assert "`" not in result

    def test_removes_code_blocks(self):
        """コードブロック (```) を除去する"""
        content = b"Before\n```python\ndef hello():\n    pass\n```\nAfter"
        result = parse_markdown(content)
        assert "Before" in result
        assert "After" in result
        assert "```" not in result
        assert "def hello" not in result

    def test_removes_bold_double_asterisk(self):
        """太字記法 **text** を除去する"""
        content = b"This is **bold** text."
        result = parse_markdown(content)
        assert "bold" in result
        assert "**" not in result

    def test_removes_italic_single_asterisk(self):
        """斜体記法 *text* を除去する"""
        content = b"This is *italic* text."
        result = parse_markdown(content)
        assert "italic" in result
        assert result.count("*") == 0

    def test_removes_bold_double_underscore(self):
        """太字記法 __text__ を除去する"""
        content = b"This is __bold__ text."
        result = parse_markdown(content)
        assert "bold" in result
        assert "__" not in result

    def test_removes_italic_single_underscore(self):
        """斜体記法 _text_ を除去する"""
        content = b"This is _italic_ text."
        result = parse_markdown(content)
        assert "italic" in result
        # The underscores should be removed
        assert "_italic_" not in result

    def test_removes_horizontal_rule_dashes(self):
        """水平線 (---) を除去する"""
        content = b"Above\n---\nBelow"
        result = parse_markdown(content)
        assert "Above" in result
        assert "Below" in result
        assert "---" not in result

    def test_removes_horizontal_rule_asterisks(self):
        """水平線 (***) を除去する"""
        content = b"Above\n***\nBelow"
        result = parse_markdown(content)
        assert "***" not in result

    def test_removes_horizontal_rule_underscores(self):
        """水平線 (___) を除去する"""
        content = b"Above\n___\nBelow"
        result = parse_markdown(content)
        assert "___" not in result

    def test_collapses_multiple_blank_lines(self):
        """3行以上の連続空行を1つの空行に圧縮する"""
        content = b"Line 1\n\n\n\n\nLine 2"
        result = parse_markdown(content)
        # Should have at most one blank line between them
        assert "\n\n\n" not in result
        assert "Line 1" in result
        assert "Line 2" in result

    def test_handles_empty_content(self):
        """空のコンテンツを正しく処理する"""
        result = parse_markdown(b"")
        assert result == ""

    def test_handles_whitespace_only_content(self):
        """空白のみのコンテンツを正しく処理する"""
        result = parse_markdown(b"   \n\n   ")
        assert result == ""

    def test_handles_non_utf8_content_gracefully(self):
        """非UTF-8コンテンツをエラーなく処理する（errors='replace'）"""
        # Invalid UTF-8 bytes
        content = b"\xff\xfe Invalid bytes \x80\x81"
        result = parse_markdown(content)
        # Should not raise, should contain replacement characters
        assert isinstance(result, str)
        assert len(result) > 0

    def test_preserves_plain_text(self):
        """Markdown記法のないプレーンテキストはそのまま返す"""
        content = b"Just plain text without any markdown."
        result = parse_markdown(content)
        assert result == "Just plain text without any markdown."

    def test_result_is_stripped(self):
        """結果の前後の空白が除去される"""
        content = b"\n\n  # Title  \n\n"
        result = parse_markdown(content)
        assert not result.startswith("\n")
        assert not result.endswith("\n")
        assert not result.startswith(" ")

    def test_combined_markdown_elements(self):
        """複数のMarkdown要素を含む複合的なコンテンツを正しく処理する"""
        content = (
            b"# Main Title\n\n"
            b"Some **bold** and *italic* text.\n\n"
            b"## Section\n\n"
            b"A [link](https://example.com) and an ![image](pic.png).\n\n"
            b"```\ncode block\n```\n\n"
            b"Use `inline code` here.\n\n"
            b"---\n\n"
            b"End of document."
        )
        result = parse_markdown(content)
        assert "Main Title" in result
        assert "bold" in result
        assert "italic" in result
        assert "Section" in result
        assert "link" in result
        assert "https://example.com" not in result
        assert "image" in result
        assert "pic.png" not in result
        assert "```" not in result
        assert "code block" not in result
        assert "inline code" in result
        assert "End of document." in result
        assert "**" not in result
        assert result.count("*") == 0 or "*" not in result.replace("*", "")


# ---------------------------------------------------------------------------
# parse_pdf
# ---------------------------------------------------------------------------
class TestParsePdf:
    """parse_pdf のユニットテスト（pymupdf をモック）"""

    def _make_mock_page(self, text: str) -> MagicMock:
        """テキストを返すモックページを生成するヘルパー"""
        page = MagicMock()
        page.get_text.return_value = text
        return page

    def _make_mock_doc(self, pages: list[MagicMock]) -> MagicMock:
        """モックページリストからモックドキュメントを生成するヘルパー"""
        doc = MagicMock()
        doc.__iter__ = MagicMock(return_value=iter(pages))
        doc.close = MagicMock()
        return doc

    def test_extracts_text_from_single_page(self):
        """単一ページのPDFからテキストを抽出する"""
        mock_page = self._make_mock_page("Hello PDF World")
        mock_doc = self._make_mock_doc([mock_page])

        with patch("backend.utils.file_parser.pymupdf") as mock_pymupdf:
            mock_pymupdf.open.return_value = mock_doc
            mock_pymupdf.FileDataError = Exception

            result = parse_pdf(b"fake pdf bytes")

        assert result == "Hello PDF World"
        mock_pymupdf.open.assert_called_once_with(stream=b"fake pdf bytes", filetype="pdf")
        mock_doc.close.assert_called_once()

    def test_multi_page_joins_with_double_newline(self):
        """複数ページのテキストを二重改行で結合する"""
        pages = [
            self._make_mock_page("Page 1 content"),
            self._make_mock_page("Page 2 content"),
            self._make_mock_page("Page 3 content"),
        ]
        mock_doc = self._make_mock_doc(pages)

        with patch("backend.utils.file_parser.pymupdf") as mock_pymupdf:
            mock_pymupdf.open.return_value = mock_doc
            mock_pymupdf.FileDataError = Exception

            result = parse_pdf(b"fake multi-page pdf")

        assert result == "Page 1 content\n\nPage 2 content\n\nPage 3 content"

    def test_raises_valueerror_for_empty_pdf(self):
        """テキストが抽出できないPDFは ValueError を発生させる"""
        # Pages with only whitespace
        mock_page = self._make_mock_page("   \n  ")
        mock_doc = self._make_mock_doc([mock_page])

        with patch("backend.utils.file_parser.pymupdf") as mock_pymupdf:
            mock_pymupdf.open.return_value = mock_doc
            mock_pymupdf.FileDataError = Exception

            with pytest.raises(ValueError, match="No text content found in PDF"):
                parse_pdf(b"empty pdf bytes")

    def test_raises_valueerror_for_zero_pages(self):
        """ページが0件のPDFは ValueError を発生させる"""
        mock_doc = self._make_mock_doc([])

        with patch("backend.utils.file_parser.pymupdf") as mock_pymupdf:
            mock_pymupdf.open.return_value = mock_doc
            mock_pymupdf.FileDataError = Exception

            with pytest.raises(ValueError, match="No text content found in PDF"):
                parse_pdf(b"zero page pdf")

    def test_raises_valueerror_for_invalid_pdf_data(self):
        """無効なPDFデータは pymupdf.FileDataError を捕捉して ValueError に変換する"""

        class FakeFileDataError(Exception):
            pass

        with patch("backend.utils.file_parser.pymupdf") as mock_pymupdf:
            mock_pymupdf.FileDataError = FakeFileDataError
            mock_pymupdf.open.side_effect = FakeFileDataError("cannot open broken data")

            with pytest.raises(ValueError, match="Invalid PDF file"):
                parse_pdf(b"this is not pdf data")

    def test_skips_pages_with_only_whitespace(self):
        """空白のみのページはスキップして有効なページのみ結合する"""
        pages = [
            self._make_mock_page("Valid page 1"),
            self._make_mock_page("   \n\t  "),  # whitespace only
            self._make_mock_page("Valid page 3"),
        ]
        mock_doc = self._make_mock_doc(pages)

        with patch("backend.utils.file_parser.pymupdf") as mock_pymupdf:
            mock_pymupdf.open.return_value = mock_doc
            mock_pymupdf.FileDataError = Exception

            result = parse_pdf(b"pdf with blank page")

        assert result == "Valid page 1\n\nValid page 3"

    def test_strips_page_text(self):
        """各ページのテキストの前後空白が除去される"""
        mock_page = self._make_mock_page("  trimmed text  \n")
        mock_doc = self._make_mock_doc([mock_page])

        with patch("backend.utils.file_parser.pymupdf") as mock_pymupdf:
            mock_pymupdf.open.return_value = mock_doc
            mock_pymupdf.FileDataError = Exception

            result = parse_pdf(b"pdf bytes")

        assert result == "trimmed text"

    def test_doc_close_called_on_success(self):
        """正常終了時に doc.close() が呼ばれる"""
        mock_page = self._make_mock_page("content")
        mock_doc = self._make_mock_doc([mock_page])

        with patch("backend.utils.file_parser.pymupdf") as mock_pymupdf:
            mock_pymupdf.open.return_value = mock_doc
            mock_pymupdf.FileDataError = Exception

            parse_pdf(b"pdf bytes")

        mock_doc.close.assert_called_once()

    def test_valueerror_from_file_data_error_chains_cause(self):
        """FileDataError から変換された ValueError に元の例外が __cause__ として連鎖する"""

        class FakeFileDataError(Exception):
            pass

        with patch("backend.utils.file_parser.pymupdf") as mock_pymupdf:
            mock_pymupdf.FileDataError = FakeFileDataError
            original_error = FakeFileDataError("corrupted stream")
            mock_pymupdf.open.side_effect = original_error

            with pytest.raises(ValueError) as exc_info:
                parse_pdf(b"corrupted pdf")

            assert exc_info.value.__cause__ is original_error
