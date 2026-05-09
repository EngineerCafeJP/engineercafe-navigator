"""Knowledge CRUD API Tests"""

import asyncio
import io
from unittest.mock import AsyncMock, MagicMock, call, patch

import httpx
import pytest
from postgrest import APIError

pytest.importorskip("fastapi", reason="fastapi not installed")

from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from backend.api.knowledge import router as knowledge_router  # noqa: E402
from backend.utils.rate_limit import limiter  # noqa: E402

# main.pyの全体インポートを避け、knowledge routerのみテスト用appに登録
_test_app = FastAPI()
_test_app.include_router(knowledge_router, prefix="/api")
client = TestClient(_test_app)


@pytest.fixture(autouse=True)
def _reset_rate_limiter():
    """Reset rate limiter state between tests to avoid 429 flaps."""
    if limiter is not None:
        try:
            limiter.reset()
        except Exception:
            pass


# =============================================================================
# Test fixtures
# =============================================================================

FAKE_EMBEDDING = [0.1] * 1536

SAMPLE_ROW = {
    "id": "550e8400-e29b-41d4-a716-446655440000",
    "title": "テスト記事",
    "content": "テスト内容です",
    "category": "general",
    "subcategory": None,
    "language": "ja",
    "source": None,
    "metadata": {},
    "created_at": "2026-02-14T00:00:00+00:00",
    "updated_at": "2026-02-14T00:00:00+00:00",
}


def _mock_supabase():
    """共通のSupabaseモックを生成"""
    return MagicMock()


def _mock_table_result(data, count=None):
    """Supabaseのテーブル操作結果モック"""
    result = MagicMock()
    result.data = data
    result.count = count
    return result


# =============================================================================
# GET /api/knowledge/categories
# =============================================================================


@patch("backend.api.knowledge._get_supabase")
def test_get_knowledge_categories(mock_get_sb):
    """カテゴリ・サブカテゴリ・ソース・言語一覧取得"""
    mock_sb = _mock_supabase()
    mock_get_sb.return_value = mock_sb

    table_mock = mock_sb.table.return_value

    # Single query returns all 4 columns; Python-side deduplication handles the rest
    combined_query = MagicMock()
    combined_query.execute.return_value = _mock_table_result(
        [
            {
                "category": "facility-info",
                "subcategory": "equipment",
                "source": "manual",
                "language": "ja",
            },
            {
                "category": "hours",
                "subcategory": "holiday",
                "source": "web",
                "language": "en",
            },
            {
                "category": "hours",
                "subcategory": "weekday",
                "source": "manual",
                "language": "ja",
            },
            {
                "category": "hours",
                "subcategory": "holiday",
                "source": "manual",
                "language": "ja",
            },
            {
                "category": "facility-info",
                "subcategory": None,
                "source": None,
                "language": None,
            },
            {
                "category": None,
                "subcategory": None,
                "source": None,
                "language": None,
            },
        ]
    )

    table_mock.select.return_value = combined_query

    response = client.get("/api/knowledge/categories")

    assert response.status_code == 200
    assert response.json() == {
        "categories": ["facility-info", "hours"],
        "subcategories": {
            "facility-info": ["equipment"],
            "hours": ["holiday", "weekday"],
        },
        "sources": ["manual", "web"],
        "languages": ["en", "ja"],
        "stats": {
            "totalCategories": 2,
            "totalSubcategories": 3,
            "totalSources": 2,
            "totalLanguages": 2,
        },
    }


# =============================================================================
# GET /api/knowledge
# =============================================================================


@patch("backend.api.knowledge.generate_embedding", new_callable=AsyncMock)
@patch("backend.api.knowledge._get_supabase")
def test_list_knowledge(mock_get_sb, mock_embed):
    """一覧取得 + ページネーション"""
    mock_sb = _mock_supabase()
    mock_get_sb.return_value = mock_sb

    query_mock = MagicMock()
    mock_sb.table.return_value.select.return_value = query_mock
    query_mock.order.return_value.range.return_value.execute.return_value = _mock_table_result(
        [SAMPLE_ROW], count=1
    )

    response = client.get("/api/knowledge?page=1&limit=10")

    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert len(body["data"]) == 1
    assert body["total"] == 1
    assert body["page"] == 1


@patch("backend.api.knowledge.generate_embedding", new_callable=AsyncMock)
@patch("backend.api.knowledge._get_supabase")
def test_list_knowledge_filter_category(mock_get_sb, mock_embed):
    """カテゴリフィルタ"""
    mock_sb = _mock_supabase()
    mock_get_sb.return_value = mock_sb

    query_mock = MagicMock()
    mock_sb.table.return_value.select.return_value = query_mock
    query_mock.eq.return_value = query_mock
    query_mock.order.return_value.range.return_value.execute.return_value = _mock_table_result(
        [SAMPLE_ROW], count=1
    )

    response = client.get("/api/knowledge?category=general")

    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True


@patch("backend.api.knowledge.generate_embedding", new_callable=AsyncMock)
@patch("backend.api.knowledge._get_supabase")
def test_list_knowledge_filter_keyword(mock_get_sb, mock_embed):
    """キーワード検索"""
    mock_sb = _mock_supabase()
    mock_get_sb.return_value = mock_sb

    query_mock = MagicMock()
    mock_sb.table.return_value.select.return_value = query_mock
    query_mock.or_.return_value = query_mock
    query_mock.order.return_value.range.return_value.execute.return_value = _mock_table_result(
        [SAMPLE_ROW], count=1
    )

    response = client.get("/api/knowledge?keyword=テスト")

    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True


# =============================================================================
# GET /api/knowledge/{id}
# =============================================================================


@patch("backend.api.knowledge._get_supabase")
def test_get_knowledge_by_id(mock_get_sb):
    """単一取得"""
    mock_sb = _mock_supabase()
    mock_get_sb.return_value = mock_sb

    mock_sb.table.return_value.select.return_value.eq.return_value.execute.return_value = (
        _mock_table_result([SAMPLE_ROW])
    )

    response = client.get(f"/api/knowledge/{SAMPLE_ROW['id']}")

    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert body["data"]["id"] == SAMPLE_ROW["id"]


@patch("backend.api.knowledge._get_supabase")
def test_get_knowledge_not_found(mock_get_sb):
    """存在しないID→404"""
    mock_sb = _mock_supabase()
    mock_get_sb.return_value = mock_sb

    mock_sb.table.return_value.select.return_value.eq.return_value.execute.return_value = (
        _mock_table_result([])
    )

    response = client.get("/api/knowledge/nonexistent-id")

    assert response.status_code == 404


# =============================================================================
# POST /api/knowledge
# =============================================================================


@patch("backend.api.knowledge.generate_embedding", new_callable=AsyncMock)
@patch("backend.api.knowledge._get_supabase")
def test_create_knowledge(mock_get_sb, mock_embed):
    """テキスト入力でナレッジ作成 + embedding生成"""
    mock_embed.return_value = FAKE_EMBEDDING
    mock_sb = _mock_supabase()
    mock_get_sb.return_value = mock_sb

    # 重複チェック → 空
    mock_sb.table.return_value.select.return_value.eq.return_value.execute.return_value = (
        _mock_table_result([])
    )
    # insert結果
    mock_sb.table.return_value.insert.return_value.execute.return_value = _mock_table_result(
        [SAMPLE_ROW]
    )

    response = client.post(
        "/api/knowledge",
        json={
            "title": "テスト記事",
            "content": "テスト内容です",
            "category": "general",
            "language": "ja",
        },
    )

    assert response.status_code == 201
    body = response.json()
    assert body["success"] is True
    assert body["data"]["title"] == "テスト記事"
    mock_embed.assert_called_once()


@patch("backend.api.knowledge.generate_embedding", new_callable=AsyncMock)
@patch("backend.api.knowledge._get_supabase")
def test_create_knowledge_validation_error(mock_get_sb, mock_embed):
    """title未指定でバリデーションエラー"""
    response = client.post(
        "/api/knowledge",
        json={
            "content": "テスト内容です",
            "category": "general",
        },
    )

    assert response.status_code == 422


@patch("backend.api.knowledge.generate_embedding", new_callable=AsyncMock)
@patch("backend.api.knowledge._get_supabase")
def test_create_knowledge_duplicate_title(mock_get_sb, mock_embed):
    """重複titleで409エラー"""
    mock_sb = _mock_supabase()
    mock_get_sb.return_value = mock_sb

    # 重複チェック → 既存あり
    mock_sb.table.return_value.select.return_value.eq.return_value.execute.return_value = (
        _mock_table_result([SAMPLE_ROW])
    )

    response = client.post(
        "/api/knowledge",
        json={
            "title": "テスト記事",
            "content": "テスト内容です",
            "category": "general",
        },
    )

    assert response.status_code == 409
    assert response.json()["detail"] == {
        "message": "duplicate titles",
        "conflicts": [{"title": "テスト記事", "chunk_index": None}],
    }


@patch("backend.api.knowledge.generate_embedding", new_callable=AsyncMock)
@patch("backend.api.knowledge._get_supabase")
def test_create_knowledge_unique_violation_returns_structured_detail(mock_get_sb, mock_embed):
    """insert時のユニーク制約違反も構造化された409 detailを返す"""
    mock_embed.return_value = FAKE_EMBEDDING
    mock_sb = _mock_supabase()
    mock_get_sb.return_value = mock_sb

    mock_sb.table.return_value.select.return_value.eq.return_value.execute.return_value = (
        _mock_table_result([])
    )
    mock_sb.table.return_value.insert.return_value.execute.side_effect = APIError(
        {
            "message": 'duplicate key value violates unique constraint for "テスト記事"',
            "code": "23505",
            "hint": "",
            "details": "",
        }
    )

    response = client.post(
        "/api/knowledge",
        json={
            "title": "テスト記事",
            "content": "テスト内容です",
            "category": "general",
        },
    )

    assert response.status_code == 409
    assert response.json()["detail"] == {
        "message": "duplicate titles",
        "conflicts": [{"title": "テスト記事", "chunk_index": None}],
    }


# =============================================================================
# PUT /api/knowledge/{id}
# =============================================================================


@patch("backend.api.knowledge.generate_embedding", new_callable=AsyncMock)
@patch("backend.api.knowledge._get_supabase")
def test_update_knowledge(mock_get_sb, mock_embed):
    """更新 + embedding再生成"""
    mock_embed.return_value = FAKE_EMBEDDING
    mock_sb = _mock_supabase()
    mock_get_sb.return_value = mock_sb

    # 存在確認
    mock_sb.table.return_value.select.return_value.eq.return_value.execute.return_value = (
        _mock_table_result([SAMPLE_ROW])
    )
    # update結果
    updated_row = {**SAMPLE_ROW, "content": "更新された内容"}
    mock_sb.table.return_value.update.return_value.eq.return_value.execute.return_value = (
        _mock_table_result([updated_row])
    )

    response = client.put(
        f"/api/knowledge/{SAMPLE_ROW['id']}",
        json={"content": "更新された内容"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    mock_embed.assert_called_once()


@patch("backend.api.knowledge.generate_embedding", new_callable=AsyncMock)
@patch("backend.api.knowledge._get_supabase")
def test_update_knowledge_unique_violation_returns_structured_detail(mock_get_sb, mock_embed):
    """update時のユニーク制約違反も構造化された409 detailを返す"""
    mock_embed.return_value = FAKE_EMBEDDING
    mock_sb = _mock_supabase()
    mock_get_sb.return_value = mock_sb

    mock_sb.table.return_value.select.return_value.eq.return_value.execute.return_value = (
        _mock_table_result([SAMPLE_ROW])
    )
    mock_sb.table.return_value.update.return_value.eq.return_value.execute.side_effect = APIError(
        {
            "message": 'duplicate key value violates unique constraint for "更新後タイトル"',
            "code": "23505",
            "hint": "",
            "details": "",
        }
    )

    response = client.put(
        f"/api/knowledge/{SAMPLE_ROW['id']}",
        json={"title": "更新後タイトル", "content": "更新された内容"},
    )

    assert response.status_code == 409
    assert response.json()["detail"] == {
        "message": "duplicate titles",
        "conflicts": [{"title": "更新後タイトル", "chunk_index": None}],
    }


# =============================================================================
# DELETE /api/knowledge/{id}
# =============================================================================


@patch("backend.api.knowledge._get_supabase")
def test_delete_knowledge(mock_get_sb):
    """削除"""
    mock_sb = _mock_supabase()
    mock_get_sb.return_value = mock_sb

    # 存在確認
    mock_sb.table.return_value.select.return_value.eq.return_value.execute.return_value = (
        _mock_table_result([SAMPLE_ROW])
    )
    # delete
    mock_sb.table.return_value.delete.return_value.eq.return_value.execute.return_value = (
        _mock_table_result([])
    )

    response = client.delete(f"/api/knowledge/{SAMPLE_ROW['id']}")

    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True


# =============================================================================
# POST /api/knowledge/upload
# =============================================================================


def _pricing_upload_content(paragraph_count: int = 3) -> str:
    sentence = "これはアップロード文書のチャンク分割テストです。"
    return "\n\n".join(sentence * 8 for _ in range(paragraph_count))


@patch("backend.api.knowledge.parse_markdown")
@patch("backend.api.knowledge.generate_embedding", new_callable=AsyncMock)
@patch("backend.api.knowledge._get_supabase")
def test_upload_markdown(mock_get_sb, mock_embed, mock_parse_md):
    """.mdアップロード → パース → 保存"""
    mock_embed.return_value = FAKE_EMBEDDING
    mock_parse_md.return_value = "Parsed markdown content"
    mock_sb = _mock_supabase()
    mock_get_sb.return_value = mock_sb

    mock_sb.table.return_value.select.return_value.in_.return_value.execute.return_value = (
        _mock_table_result([])
    )
    # insert結果
    uploaded_row = {
        **SAMPLE_ROW,
        "title": "test_doc",
        "content": "Parsed markdown content",
        "source": "file:test_doc.md",
        "metadata": {
            "original_filename": "test_doc.md",
            "file_type": "markdown",
            "chunk_index": 0,
            "total_chunks": 1,
        },
    }
    mock_sb.table.return_value.insert.return_value.execute.return_value = _mock_table_result(
        [uploaded_row]
    )

    md_content = b"# Test\n\nHello world"
    response = client.post(
        "/api/knowledge/upload",
        data={"category": "general", "language": "ja"},
        files={"file": ("test_doc.md", io.BytesIO(md_content), "text/markdown")},
    )

    assert response.status_code == 201
    body = response.json()
    assert body["success"] is True
    assert body["data"]["metadata"]["chunk_index"] == 0
    assert body["data"]["metadata"]["total_chunks"] == 1
    assert body["data"]["metadata"]["chunks_created"] == 1
    mock_parse_md.assert_called_once()
    mock_embed.assert_called_once()
    assert mock_embed.await_args.args == ("test_doc\nParsed markdown content",)
    inserted = mock_sb.table.return_value.insert.call_args.args[0]
    assert inserted["metadata"]["language"] == "ja"
    assert inserted["metadata"]["chunk_level"] == "document"
    assert inserted["metadata"]["entry_id"].startswith("upload-test_doc-")
    assert inserted["metadata"]["document_id"] == inserted["metadata"]["entry_id"]
    assert inserted["chunk_level"] == "document"
    assert inserted["chunk_index"] == 0
    assert inserted["token_count"] > 0


@patch("backend.api.knowledge.parse_pdf")
@patch("backend.api.knowledge.generate_embedding", new_callable=AsyncMock)
@patch("backend.api.knowledge._get_supabase")
def test_upload_pdf(mock_get_sb, mock_embed, mock_parse_pdf):
    """.pdfアップロード → パース → 保存"""
    mock_embed.return_value = FAKE_EMBEDDING
    mock_parse_pdf.return_value = "Parsed PDF content"
    mock_sb = _mock_supabase()
    mock_get_sb.return_value = mock_sb

    mock_sb.table.return_value.select.return_value.in_.return_value.execute.return_value = (
        _mock_table_result([])
    )
    # insert結果
    uploaded_row = {
        **SAMPLE_ROW,
        "title": "document",
        "content": "Parsed PDF content",
        "source": "file:document.pdf",
        "metadata": {
            "original_filename": "document.pdf",
            "file_type": "pdf",
            "chunk_index": 0,
            "total_chunks": 1,
        },
    }
    mock_sb.table.return_value.insert.return_value.execute.return_value = _mock_table_result(
        [uploaded_row]
    )

    pdf_content = b"%PDF-1.4 fake content"
    response = client.post(
        "/api/knowledge/upload",
        data={"category": "general", "language": "ja"},
        files={"file": ("document.pdf", io.BytesIO(pdf_content), "application/pdf")},
    )

    assert response.status_code == 201
    body = response.json()
    assert body["success"] is True
    assert body["data"]["metadata"]["chunk_index"] == 0
    assert body["data"]["metadata"]["total_chunks"] == 1
    assert body["data"]["metadata"]["chunks_created"] == 1
    mock_parse_pdf.assert_called_once()
    mock_embed.assert_called_once()


@patch("backend.api.knowledge.parse_markdown")
@patch("backend.api.knowledge.generate_embedding", new_callable=AsyncMock)
@patch("backend.api.knowledge._get_supabase")
def test_upload_markdown_splits_into_chunks(mock_get_sb, mock_embed, mock_parse_md):
    """長い.mdは複数チャンクに分割して保存する"""
    parsed_content = _pricing_upload_content(paragraph_count=4)
    mock_parse_md.return_value = parsed_content
    mock_embed.return_value = FAKE_EMBEDDING
    mock_sb = _mock_supabase()
    mock_get_sb.return_value = mock_sb

    mock_sb.table.return_value.select.return_value.in_.return_value.execute.return_value = (
        _mock_table_result([])
    )
    first_row = {
        **SAMPLE_ROW,
        "title": "multi_doc",
        "content": parsed_content[:200].rstrip() + "...",
        "source": "file:multi_doc.md",
        "metadata": {
            "original_filename": "multi_doc.md",
            "file_type": "markdown",
            "chunk_index": 0,
            "total_chunks": 3,
        },
    }
    second_row = {
        **SAMPLE_ROW,
        "title": "multi_doc [chunk 1]",
        "content": "Chunk two",
        "source": "file:multi_doc.md",
        "metadata": {
            "original_filename": "multi_doc.md",
            "file_type": "markdown",
            "chunk_index": 1,
            "total_chunks": 3,
        },
    }
    mock_sb.table.return_value.insert.return_value.execute.side_effect = [
        _mock_table_result([first_row]),
        _mock_table_result([second_row]),
        _mock_table_result(
            [
                {
                    **SAMPLE_ROW,
                    "title": "multi_doc [chunk 2]",
                    "content": "Chunk three",
                }
            ]
        ),
    ]

    response = client.post(
        "/api/knowledge/upload",
        data={"category": "pricing", "language": "ja"},
        files={"file": ("multi_doc.md", io.BytesIO(b"# Test"), "text/markdown")},
    )

    assert response.status_code == 201
    body = response.json()
    assert body["success"] is True
    assert body["data"]["title"] == "multi_doc"
    assert body["data"]["metadata"]["chunk_index"] == 0
    assert body["data"]["metadata"]["total_chunks"] == 3
    assert body["data"]["metadata"]["chunks_created"] == 3
    assert mock_embed.await_args_list[0].args == (parsed_content[:200].rstrip() + "...",)

    insert_calls = mock_sb.table.return_value.insert.call_args_list
    assert len(insert_calls) == 3
    assert insert_calls[0].args[0]["title"] == "multi_doc"
    assert insert_calls[1].args[0]["title"] == "multi_doc [chunk 1]"
    assert insert_calls[2].args[0]["title"] == "multi_doc [chunk 2]"
    assert insert_calls[0].args[0]["metadata"]["chunk_index"] == 0
    assert insert_calls[1].args[0]["metadata"]["chunk_index"] == 1
    assert insert_calls[0].args[0]["metadata"]["chunk_level"] == "document"
    assert insert_calls[1].args[0]["metadata"]["chunk_level"] == "chunk"
    assert insert_calls[2].args[0]["metadata"]["chunk_level"] == "chunk"
    assert insert_calls[0].args[0]["chunk_level"] == "document"
    assert insert_calls[1].args[0]["chunk_level"] == "chunk"
    assert insert_calls[2].args[0]["chunk_level"] == "chunk"
    assert insert_calls[1].args[0]["chunk_index"] == 1
    assert insert_calls[1].args[0]["token_count"] > 0
    assert insert_calls[1].args[0]["metadata"]["total_chunks"] == 3
    entry_ids = {call.args[0]["metadata"]["entry_id"] for call in insert_calls}
    assert len(entry_ids) == 1
    for insert_call in insert_calls:
        metadata = insert_call.args[0]["metadata"]
        assert metadata["document_id"] == metadata["entry_id"]
        assert metadata["language"] == "ja"


@patch("backend.api.knowledge.parse_markdown")
@patch("backend.api.knowledge._get_supabase")
def test_upload_rejects_duplicate_chunk_title_from_batch_check(mock_get_sb, mock_parse_md):
    """チャンクタイトル衝突時は全conflictを含む409を返す"""
    mock_parse_md.return_value = _pricing_upload_content(paragraph_count=4)
    mock_sb = _mock_supabase()
    mock_get_sb.return_value = mock_sb

    mock_sb.table.return_value.select.return_value.in_.return_value.execute.return_value = (
        _mock_table_result([{"title": "duplicate_doc"}, {"title": "duplicate_doc [chunk 2]"}])
    )

    response = client.post(
        "/api/knowledge/upload",
        data={"category": "pricing", "language": "ja"},
        files={"file": ("duplicate_doc.md", io.BytesIO(b"# Test"), "text/markdown")},
    )

    assert response.status_code == 409
    detail = response.json()["detail"]
    assert detail["message"] == "duplicate titles"
    assert len(detail["conflicts"]) == 2
    conflict_titles = {c["title"] for c in detail["conflicts"]}
    assert "duplicate_doc" in conflict_titles
    assert "duplicate_doc [chunk 2]" in conflict_titles
    mock_sb.table.return_value.select.return_value.in_.assert_called_once_with(
        "title",
        ["duplicate_doc", "duplicate_doc [chunk 1]", "duplicate_doc [chunk 2]"],
    )
    mock_sb.table.return_value.insert.assert_not_called()


@patch("backend.api.knowledge.parse_markdown")
@patch("backend.api.knowledge.generate_embedding", new_callable=AsyncMock)
@patch("backend.api.knowledge._get_supabase")
def test_upload_continues_when_embedding_times_out(mock_get_sb, mock_embed, mock_parse_md):
    """Single chunk with embedding timeout → 503 (all chunks failed)"""
    mock_embed.side_effect = httpx.TimeoutException("Request timed out")
    mock_parse_md.return_value = "Parsed markdown content"
    mock_sb = _mock_supabase()
    mock_get_sb.return_value = mock_sb

    mock_sb.table.return_value.select.return_value.in_.return_value.execute.return_value = (
        _mock_table_result([])
    )

    response = client.post(
        "/api/knowledge/upload",
        data={"category": "general", "language": "ja"},
        files={"file": ("timeout_doc.md", io.BytesIO(b"# Test"), "text/markdown")},
    )

    assert response.status_code == 503
    assert "unavailable" in response.json()["detail"].lower()
    mock_sb.table.return_value.insert.assert_not_called()


@patch("backend.api.knowledge.parse_markdown")
@patch("backend.api.knowledge.generate_embedding", new_callable=AsyncMock)
@patch("backend.api.knowledge._get_supabase")
def test_upload_rejects_when_document_exceeds_max_chunks(mock_get_sb, mock_embed, mock_parse_md):
    """チャンク数上限超過時は400を返す"""
    mock_embed.return_value = FAKE_EMBEDDING
    mock_parse_md.return_value = _pricing_upload_content(paragraph_count=160)
    mock_sb = _mock_supabase()
    mock_get_sb.return_value = mock_sb

    response = client.post(
        "/api/knowledge/upload",
        data={"category": "pricing", "language": "ja"},
        files={"file": ("too_many_chunks.md", io.BytesIO(b"# Test"), "text/markdown")},
    )

    assert response.status_code == 400
    assert "chunks exceeds limit of 50" in response.json()["detail"]
    mock_sb.table.return_value.select.assert_not_called()
    mock_sb.table.return_value.insert.assert_not_called()


@patch("backend.api.knowledge.parse_markdown")
@patch("backend.api.knowledge.generate_embedding", new_callable=AsyncMock)
@patch("backend.api.knowledge._get_supabase")
def test_upload_rolls_back_inserted_chunks_on_unique_violation(
    mock_get_sb, mock_embed, mock_parse_md
):
    """途中チャンクの一意制約違反時は既存挿入分をロールバックする"""
    mock_embed.side_effect = [FAKE_EMBEDDING, FAKE_EMBEDDING]
    mock_parse_md.return_value = _pricing_upload_content(paragraph_count=4)
    mock_sb = _mock_supabase()
    mock_get_sb.return_value = mock_sb

    mock_sb.table.return_value.select.return_value.in_.return_value.execute.return_value = (
        _mock_table_result([])
    )
    mock_sb.table.return_value.insert.return_value.execute.side_effect = [
        _mock_table_result(
            [
                {
                    **SAMPLE_ROW,
                    "id": "first-chunk-id",
                    "title": "race_doc (part 1)",
                    "content": "Chunk one",
                }
            ]
        ),
        APIError(
            {
                "message": (
                    'duplicate key value violates unique constraint for "race_doc [chunk 1]"'
                ),
                "code": "23505",
                "hint": "",
                "details": "",
            }
        ),
    ]
    mock_sb.table.return_value.delete.return_value.eq.return_value.execute.return_value = (
        _mock_table_result([])
    )

    response = client.post(
        "/api/knowledge/upload",
        data={"category": "pricing", "language": "ja"},
        files={"file": ("race_doc.md", io.BytesIO(b"# Test"), "text/markdown")},
    )

    assert response.status_code == 409
    detail = response.json()["detail"]
    assert detail["message"] == "duplicate titles"
    assert len(detail["conflicts"]) == 1
    assert detail["conflicts"][0]["title"] == "race_doc [chunk 1]"
    assert detail["conflicts"][0]["chunk_index"] == 1
    assert mock_sb.table.return_value.delete.return_value.eq.call_args_list == [
        call("id", "first-chunk-id")
    ]


@patch("backend.api.knowledge.parse_markdown")
@patch("backend.api.knowledge.generate_embedding", new_callable=AsyncMock)
@patch("backend.api.knowledge._get_supabase")
def test_upload_returns_503_when_supabase_insert_fails(mock_get_sb, mock_embed, mock_parse_md):
    """Supabase insert失敗時は503を返す"""
    mock_embed.return_value = FAKE_EMBEDDING
    mock_parse_md.return_value = "Parsed markdown content"
    mock_sb = _mock_supabase()
    mock_get_sb.return_value = mock_sb

    mock_sb.table.return_value.select.return_value.in_.return_value.execute.return_value = (
        _mock_table_result([])
    )
    mock_sb.table.return_value.insert.return_value.execute.side_effect = APIError(
        {
            "message": "Supabase unavailable",
            "code": "08006",
            "hint": "",
            "details": "",
        }
    )

    response = client.post(
        "/api/knowledge/upload",
        data={"category": "general", "language": "ja"},
        files={"file": ("failed_doc.md", io.BytesIO(b"# Test"), "text/markdown")},
    )

    assert response.status_code == 503
    assert response.json()["detail"] == "Knowledge storage unavailable"


@patch("backend.api.knowledge.asyncio.wait_for", new_callable=AsyncMock)
def test_upload_returns_504_on_overall_timeout(mock_wait_for):
    """全体のアップロード処理がタイムアウトした場合は504を返す"""

    async def _raise_timeout(awaitable, timeout):
        awaitable.close()
        raise asyncio.TimeoutError()

    mock_wait_for.side_effect = _raise_timeout

    response = client.post(
        "/api/knowledge/upload",
        data={"category": "general", "language": "ja"},
        files={"file": ("timeout_guard.md", io.BytesIO(b"# Test"), "text/markdown")},
    )

    assert response.status_code == 504
    assert response.json()["detail"] == "Knowledge upload timed out"


# =============================================================================
# #541: Embedding null-safe + upload fault tolerance
# =============================================================================


@patch("backend.api.knowledge.parse_markdown")
@patch("backend.api.knowledge.generate_embedding", new_callable=AsyncMock)
@patch("backend.api.knowledge._get_supabase")
def test_upload_all_chunks_timeout_returns_503(mock_get_sb, mock_embed, mock_parse_md):
    """All chunk embeddings timeout → 503 Service Unavailable"""
    mock_embed.side_effect = httpx.TimeoutException("Request timed out")
    mock_parse_md.return_value = "Parsed markdown content"
    mock_sb = _mock_supabase()
    mock_get_sb.return_value = mock_sb

    mock_sb.table.return_value.select.return_value.in_.return_value.execute.return_value = (
        _mock_table_result([])
    )

    response = client.post(
        "/api/knowledge/upload",
        data={"category": "general", "language": "ja"},
        files={"file": ("all_timeout.md", io.BytesIO(b"# Test"), "text/markdown")},
    )

    assert response.status_code == 503
    assert "unavailable" in response.json()["detail"].lower()
    mock_sb.table.return_value.insert.assert_not_called()


@patch("backend.api.knowledge.parse_markdown")
@patch("backend.api.knowledge.generate_embedding", new_callable=AsyncMock)
@patch("backend.api.knowledge._get_supabase")
def test_upload_partial_timeout_returns_200_with_failed_chunks(
    mock_get_sb, mock_embed, mock_parse_md
):
    """Some chunk embeddings timeout → 200 with failed_chunks metadata"""
    mock_parse_md.return_value = _pricing_upload_content(paragraph_count=4)
    mock_embed.side_effect = [FAKE_EMBEDDING, httpx.TimeoutException("timeout"), FAKE_EMBEDDING]
    mock_sb = _mock_supabase()
    mock_get_sb.return_value = mock_sb

    mock_sb.table.return_value.select.return_value.in_.return_value.execute.return_value = (
        _mock_table_result([])
    )
    first_row = {**SAMPLE_ROW, "title": "partial_doc (part 1)", "content": "Chunk A"}
    third_row = {**SAMPLE_ROW, "title": "partial_doc (part 3)", "content": "Chunk C"}
    mock_sb.table.return_value.insert.return_value.execute.side_effect = [
        _mock_table_result([first_row]),
        _mock_table_result([third_row]),
    ]

    response = client.post(
        "/api/knowledge/upload",
        data={"category": "pricing", "language": "ja"},
        files={"file": ("partial_doc.md", io.BytesIO(b"# Test"), "text/markdown")},
    )

    assert response.status_code == 201
    body = response.json()
    assert body["success"] is True
    assert body["data"]["metadata"]["failed_chunks"] == [1]
    assert body["data"]["metadata"]["chunks_created"] == 3
    assert mock_sb.table.return_value.insert.call_count == 2


@patch("backend.api.knowledge.parse_markdown")
@patch("backend.api.knowledge.generate_embedding", new_callable=AsyncMock)
@patch("backend.api.knowledge._get_supabase")
def test_upload_all_chunks_succeed_returns_200(mock_get_sb, mock_embed, mock_parse_md):
    """All chunks succeed → 200, failed_chunks is empty"""
    mock_embed.return_value = FAKE_EMBEDDING
    mock_parse_md.return_value = "Parsed markdown content"
    mock_sb = _mock_supabase()
    mock_get_sb.return_value = mock_sb

    mock_sb.table.return_value.select.return_value.in_.return_value.execute.return_value = (
        _mock_table_result([])
    )
    uploaded_row = {
        **SAMPLE_ROW,
        "title": "success_doc",
        "content": "Parsed markdown content",
        "source": "file:success_doc.md",
        "metadata": {
            "original_filename": "success_doc.md",
            "file_type": "markdown",
            "chunk_index": 0,
            "total_chunks": 1,
        },
    }
    mock_sb.table.return_value.insert.return_value.execute.return_value = _mock_table_result(
        [uploaded_row]
    )

    response = client.post(
        "/api/knowledge/upload",
        data={"category": "general", "language": "ja"},
        files={"file": ("success_doc.md", io.BytesIO(b"# Test"), "text/markdown")},
    )

    assert response.status_code == 201
    body = response.json()
    assert body["success"] is True
    assert body["data"]["metadata"].get("failed_chunks", []) == []


# =============================================================================
# POST /api/knowledge/preview
# =============================================================================


@patch("backend.api.knowledge._get_supabase")
@patch("backend.api.knowledge.parse_markdown")
def test_preview_markdown(mock_parse_md, mock_get_sb):
    """Markdown ファイルのプレビュー"""
    parsed_content = _pricing_upload_content(paragraph_count=4)
    mock_parse_md.return_value = parsed_content
    mock_sb = _mock_supabase()
    mock_get_sb.return_value = mock_sb

    response = client.post(
        "/api/knowledge/preview",
        data={"language": "ja", "category": "pricing"},
        files={"file": ("test_doc.md", io.BytesIO(b"# Test"), "text/markdown")},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["file_type"] == "markdown"
    assert body["extracted_preview"] == parsed_content[:1500]
    assert body["estimated_chunks"] == 3
    assert body["chunk_titles"] == ["test_doc", "test_doc [chunk 1]", "test_doc [chunk 2]"]
    assert body["total_chars"] == len(parsed_content)
    mock_sb.table.return_value.insert.assert_not_called()


@patch("backend.api.knowledge._get_supabase")
@patch("backend.api.knowledge.parse_pdf")
def test_preview_pdf(mock_parse_pdf, mock_get_sb):
    """PDF ファイルのプレビュー"""
    mock_parse_pdf.return_value = "Parsed PDF content for preview"
    mock_sb = _mock_supabase()
    mock_get_sb.return_value = mock_sb

    response = client.post(
        "/api/knowledge/preview",
        data={"language": "ja"},
        files={"file": ("document.pdf", io.BytesIO(b"%PDF-1.4"), "application/pdf")},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["file_type"] == "pdf"
    assert body["estimated_chunks"] == 1
    assert body["chunk_titles"] == ["document"]
    mock_sb.table.return_value.insert.assert_not_called()


@patch("backend.api.knowledge._get_supabase")
def test_preview_rejects_unsupported_file_type(mock_get_sb):
    """プレビューでサポート外のファイル形式は400"""
    mock_sb = _mock_supabase()
    mock_get_sb.return_value = mock_sb

    response = client.post(
        "/api/knowledge/preview",
        data={"language": "ja"},
        files={"file": ("image.png", io.BytesIO(b"fake"), "image/png")},
    )

    assert response.status_code == 400
    assert "Unsupported file type" in response.json()["detail"]


@patch("backend.api.knowledge.parse_markdown")
def test_preview_rejects_too_many_chunks(mock_parse_md):
    """プレビューでチャンク上限を超えるファイルは400"""
    mock_parse_md.return_value = _pricing_upload_content(paragraph_count=160)

    response = client.post(
        "/api/knowledge/preview",
        data={"language": "ja", "category": "pricing"},
        files={"file": ("large_doc.md", io.BytesIO(b"# Test"), "text/markdown")},
    )

    assert response.status_code == 400
    assert response.json()["detail"].startswith("Document too large:")
    assert response.json()["detail"].endswith("chunks exceeds limit of 50")


def test_preview_rejects_file_larger_than_10mb():
    """プレビューで10MBを超えるファイルは400"""
    response = client.post(
        "/api/knowledge/preview",
        data={"language": "ja"},
        files={
            "file": (
                "too_large.md",
                io.BytesIO(b"a" * (10 * 1024 * 1024 + 1)),
                "text/markdown",
            )
        },
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "File too large. Maximum size is 10MB."


@patch("backend.api.knowledge.asyncio.wait_for", new_callable=AsyncMock)
def test_preview_returns_504_on_timeout(mock_wait_for):
    """プレビュー処理がタイムアウトした場合は504を返す"""

    async def _raise_timeout(awaitable, timeout):
        awaitable.close()
        raise asyncio.TimeoutError()

    mock_wait_for.side_effect = _raise_timeout

    response = client.post(
        "/api/knowledge/preview",
        data={"language": "ja"},
        files={"file": ("timeout_guard.md", io.BytesIO(b"# Test"), "text/markdown")},
    )

    assert response.status_code == 504
    assert response.json()["detail"] == "Knowledge preview timed out"
    assert mock_wait_for.call_args.kwargs["timeout"] == 30
