"""Knowledge CRUD API Tests"""

import io
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

pytest.importorskip("fastapi", reason="fastapi not installed")

from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.knowledge import router as knowledge_router

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
# GET /api/knowledge
# =============================================================================


@patch("api.knowledge.generate_embedding", new_callable=AsyncMock)
@patch("api.knowledge._get_supabase")
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


@patch("api.knowledge.generate_embedding", new_callable=AsyncMock)
@patch("api.knowledge._get_supabase")
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


@patch("api.knowledge.generate_embedding", new_callable=AsyncMock)
@patch("api.knowledge._get_supabase")
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


@patch("api.knowledge._get_supabase")
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


@patch("api.knowledge._get_supabase")
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


@patch("api.knowledge.generate_embedding", new_callable=AsyncMock)
@patch("api.knowledge._get_supabase")
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


@patch("api.knowledge.generate_embedding", new_callable=AsyncMock)
@patch("api.knowledge._get_supabase")
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


@patch("api.knowledge.generate_embedding", new_callable=AsyncMock)
@patch("api.knowledge._get_supabase")
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


@patch("api.knowledge.generate_embedding", new_callable=AsyncMock)
@patch("api.knowledge._get_supabase")
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


@patch("api.knowledge._get_supabase")
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


@patch("api.knowledge.parse_markdown")
@patch("api.knowledge.generate_embedding", new_callable=AsyncMock)
@patch("api.knowledge._get_supabase")
def test_upload_markdown(mock_get_sb, mock_embed, mock_parse_md):
    """.mdアップロード → パース → 保存"""
    mock_embed.return_value = FAKE_EMBEDDING
    mock_parse_md.return_value = "Parsed markdown content"
    mock_sb = _mock_supabase()
    mock_get_sb.return_value = mock_sb

    # 重複チェック → 空
    mock_sb.table.return_value.select.return_value.eq.return_value.execute.return_value = (
        _mock_table_result([])
    )
    # insert結果
    uploaded_row = {
        **SAMPLE_ROW,
        "title": "test_doc",
        "content": "Parsed markdown content",
        "source": "file:test_doc.md",
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
    mock_parse_md.assert_called_once()
    mock_embed.assert_called_once()


@patch("api.knowledge.parse_pdf")
@patch("api.knowledge.generate_embedding", new_callable=AsyncMock)
@patch("api.knowledge._get_supabase")
def test_upload_pdf(mock_get_sb, mock_embed, mock_parse_pdf):
    """.pdfアップロード → パース → 保存"""
    mock_embed.return_value = FAKE_EMBEDDING
    mock_parse_pdf.return_value = "Parsed PDF content"
    mock_sb = _mock_supabase()
    mock_get_sb.return_value = mock_sb

    # 重複チェック → 空
    mock_sb.table.return_value.select.return_value.eq.return_value.execute.return_value = (
        _mock_table_result([])
    )
    # insert結果
    uploaded_row = {
        **SAMPLE_ROW,
        "title": "document",
        "content": "Parsed PDF content",
        "source": "file:document.pdf",
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
    mock_parse_pdf.assert_called_once()
    mock_embed.assert_called_once()
