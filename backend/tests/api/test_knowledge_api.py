"""Knowledge CRUD API Tests"""

import asyncio
import io
from unittest.mock import AsyncMock, MagicMock, call, patch

import httpx
import pytest
from postgrest import APIError

pytest.importorskip("fastapi", reason="fastapi not installed")

from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.api.knowledge import router as knowledge_router

# main.pyの全体インポートを避け、knowledge routerのみテスト用appに登録
_test_app = FastAPI()
_test_app.include_router(knowledge_router, prefix="/api")
client = TestClient(_test_app)

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

    category_query = MagicMock()
    category_query.execute.return_value = _mock_table_result(
        [
            {"category": "facility-info"},
            {"category": "hours"},
            {"category": "hours"},
            {"category": None},
        ]
    )

    subcategory_query = MagicMock()
    subcategory_query.execute.return_value = _mock_table_result(
        [
            {"category": "hours", "subcategory": "holiday"},
            {"category": "hours", "subcategory": "weekday"},
            {"category": "hours", "subcategory": "holiday"},
            {"category": "facility-info", "subcategory": "equipment"},
            {"category": "facility-info", "subcategory": None},
        ]
    )

    source_query = MagicMock()
    source_query.execute.return_value = _mock_table_result(
        [
            {"source": "manual"},
            {"source": "web"},
            {"source": "manual"},
            {"source": None},
        ]
    )

    language_query = MagicMock()
    language_query.execute.return_value = _mock_table_result(
        [
            {"language": "ja"},
            {"language": "en"},
            {"language": "ja"},
            {"language": None},
        ]
    )

    table_mock.select.side_effect = [
        category_query,
        subcategory_query,
        source_query,
        language_query,
    ]

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


@patch("backend.api.knowledge.chunk_text")
@patch("backend.api.knowledge.parse_markdown")
@patch("backend.api.knowledge.generate_embedding", new_callable=AsyncMock)
@patch("backend.api.knowledge._get_supabase")
def test_upload_markdown_splits_into_chunks(
    mock_get_sb, mock_embed, mock_parse_md, mock_chunk_text
):
    """長い.mdは複数チャンクに分割して保存する"""
    mock_parse_md.return_value = "Parsed markdown content"
    mock_chunk_text.return_value = ["Chunk one", "Chunk two"]
    mock_embed.side_effect = [FAKE_EMBEDDING, FAKE_EMBEDDING]
    mock_sb = _mock_supabase()
    mock_get_sb.return_value = mock_sb

    mock_sb.table.return_value.select.return_value.in_.return_value.execute.return_value = (
        _mock_table_result([])
    )
    first_row = {
        **SAMPLE_ROW,
        "title": "multi_doc (part 1)",
        "content": "Chunk one",
        "source": "file:multi_doc.md",
        "metadata": {
            "original_filename": "multi_doc.md",
            "file_type": "markdown",
            "chunk_index": 0,
            "total_chunks": 2,
        },
    }
    second_row = {
        **SAMPLE_ROW,
        "title": "multi_doc (part 2)",
        "content": "Chunk two",
        "source": "file:multi_doc.md",
        "metadata": {
            "original_filename": "multi_doc.md",
            "file_type": "markdown",
            "chunk_index": 1,
            "total_chunks": 2,
        },
    }
    mock_sb.table.return_value.insert.return_value.execute.side_effect = [
        _mock_table_result([first_row]),
        _mock_table_result([second_row]),
    ]

    response = client.post(
        "/api/knowledge/upload",
        data={"category": "general", "language": "ja"},
        files={"file": ("multi_doc.md", io.BytesIO(b"# Test"), "text/markdown")},
    )

    assert response.status_code == 201
    body = response.json()
    assert body["success"] is True
    assert body["data"]["title"] == "multi_doc (part 1)"
    assert body["data"]["metadata"]["chunk_index"] == 0
    assert body["data"]["metadata"]["total_chunks"] == 2
    assert body["data"]["metadata"]["chunks_created"] == 2
    assert mock_embed.await_args_list[0].args == ("Chunk one",)
    assert mock_embed.await_args_list[1].args == ("Chunk two",)

    insert_calls = mock_sb.table.return_value.insert.call_args_list
    assert len(insert_calls) == 2
    assert insert_calls[0].args[0]["title"] == "multi_doc (part 1)"
    assert insert_calls[1].args[0]["title"] == "multi_doc (part 2)"
    assert insert_calls[0].args[0]["metadata"]["chunk_index"] == 0
    assert insert_calls[1].args[0]["metadata"]["chunk_index"] == 1
    assert insert_calls[1].args[0]["metadata"]["total_chunks"] == 2


@patch("backend.api.knowledge.chunk_text")
@patch("backend.api.knowledge.parse_markdown")
@patch("backend.api.knowledge._get_supabase")
def test_upload_rejects_duplicate_chunk_title_from_batch_check(
    mock_get_sb, mock_parse_md, mock_chunk_text
):
    """チャンクタイトル衝突時は単一INクエリで409を返す"""
    mock_parse_md.return_value = "Parsed markdown content"
    mock_chunk_text.return_value = ["Chunk one", "Chunk two"]
    mock_sb = _mock_supabase()
    mock_get_sb.return_value = mock_sb

    mock_sb.table.return_value.select.return_value.in_.return_value.execute.return_value = (
        _mock_table_result([{"title": "duplicate_doc (part 2)"}])
    )

    response = client.post(
        "/api/knowledge/upload",
        data={"category": "general", "language": "ja"},
        files={"file": ("duplicate_doc.md", io.BytesIO(b"# Test"), "text/markdown")},
    )

    assert response.status_code == 409
    assert (
        response.json()["detail"] == "Knowledge with title 'duplicate_doc (part 2)' already exists"
    )
    mock_sb.table.return_value.select.return_value.in_.assert_called_once_with(
        "title",
        ["duplicate_doc (part 1)", "duplicate_doc (part 2)"],
    )
    mock_sb.table.return_value.insert.assert_not_called()


@patch("backend.api.knowledge.parse_markdown")
@patch("backend.api.knowledge.generate_embedding", new_callable=AsyncMock)
@patch("backend.api.knowledge._get_supabase")
def test_upload_continues_when_embedding_times_out(mock_get_sb, mock_embed, mock_parse_md):
    """embedding timeout時も保存は継続し、embeddingなしで登録する"""
    mock_embed.side_effect = httpx.TimeoutException("Request timed out")
    mock_parse_md.return_value = "Parsed markdown content"
    mock_sb = _mock_supabase()
    mock_get_sb.return_value = mock_sb

    mock_sb.table.return_value.select.return_value.in_.return_value.execute.return_value = (
        _mock_table_result([])
    )
    uploaded_row = {
        **SAMPLE_ROW,
        "title": "timeout_doc",
        "content": "Parsed markdown content",
        "source": "file:timeout_doc.md",
    }
    mock_sb.table.return_value.insert.return_value.execute.return_value = _mock_table_result(
        [uploaded_row]
    )

    response = client.post(
        "/api/knowledge/upload",
        data={"category": "general", "language": "ja"},
        files={"file": ("timeout_doc.md", io.BytesIO(b"# Test"), "text/markdown")},
    )

    assert response.status_code == 201
    insert_data = mock_sb.table.return_value.insert.call_args.args[0]
    assert "content_embedding" not in insert_data


@patch("backend.api.knowledge.parse_markdown")
@patch("backend.api.knowledge.generate_embedding", new_callable=AsyncMock)
@patch("backend.api.knowledge._get_supabase")
@patch("backend.api.knowledge.chunk_text")
def test_upload_rejects_when_document_exceeds_max_chunks(
    mock_chunk_text, mock_get_sb, mock_embed, mock_parse_md
):
    """チャンク数上限超過時は400を返す"""
    mock_embed.return_value = FAKE_EMBEDDING
    mock_parse_md.return_value = "Parsed markdown content"
    mock_chunk_text.return_value = [f"Chunk {index}" for index in range(51)]
    mock_sb = _mock_supabase()
    mock_get_sb.return_value = mock_sb

    response = client.post(
        "/api/knowledge/upload",
        data={"category": "general", "language": "ja"},
        files={"file": ("too_many_chunks.md", io.BytesIO(b"# Test"), "text/markdown")},
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "Document too large: 51 chunks exceeds limit of 50"
    mock_sb.table.return_value.select.assert_not_called()
    mock_sb.table.return_value.insert.assert_not_called()


@patch("backend.api.knowledge.chunk_text")
@patch("backend.api.knowledge.parse_markdown")
@patch("backend.api.knowledge.generate_embedding", new_callable=AsyncMock)
@patch("backend.api.knowledge._get_supabase")
def test_upload_rolls_back_inserted_chunks_on_unique_violation(
    mock_get_sb, mock_embed, mock_parse_md, mock_chunk_text
):
    """途中チャンクの一意制約違反時は既存挿入分をロールバックする"""
    mock_embed.side_effect = [FAKE_EMBEDDING, FAKE_EMBEDDING]
    mock_parse_md.return_value = "Parsed markdown content"
    mock_chunk_text.return_value = ["Chunk one", "Chunk two"]
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
                "message": 'duplicate key value violates unique constraint for "race_doc (part 2)"',
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
        data={"category": "general", "language": "ja"},
        files={"file": ("race_doc.md", io.BytesIO(b"# Test"), "text/markdown")},
    )

    assert response.status_code == 409
    assert response.json()["detail"] == "Knowledge with title 'race_doc (part 2)' already exists"
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
