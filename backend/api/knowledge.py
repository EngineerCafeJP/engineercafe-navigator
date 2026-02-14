"""
Knowledge Base CRUD API Router

ナレッジベースのCRUD操作とファイルアップロードを提供する。
テキスト入力に加え、.mdと.pdfファイルのアップロードにも対応。
embedding生成は自動で行われる。

NOTE: 認証は別Issueで対応予定。現時点ではCORS制限のみ。
"""

import logging
import os
import re
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, File, Form, HTTPException, Query, UploadFile
from pydantic import BaseModel, Field
from supabase import create_client

from utils.embedding_service import generate_embedding
from utils.file_parser import detect_file_type, parse_markdown, parse_pdf

logger = logging.getLogger(__name__)

router = APIRouter(tags=["knowledge"])

# 10MB upload size limit
MAX_UPLOAD_SIZE = 10 * 1024 * 1024


# =============================================================================
# Pydantic Models
# =============================================================================


class KnowledgeCreateRequest(BaseModel):
    title: str = Field(..., max_length=200)
    content: str = Field(..., max_length=5000)
    category: str
    language: str = Field(default="ja", pattern=r"^(ja|en)$")
    subcategory: Optional[str] = None
    source: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None


class KnowledgeUpdateRequest(BaseModel):
    title: Optional[str] = Field(None, max_length=200)
    content: Optional[str] = Field(None, max_length=5000)
    category: Optional[str] = None
    language: Optional[str] = Field(None, pattern=r"^(ja|en)$")
    subcategory: Optional[str] = None
    source: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None


class KnowledgeItem(BaseModel):
    id: str
    title: str
    content: str
    category: Optional[str] = None
    subcategory: Optional[str] = None
    language: Optional[str] = None
    source: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


class KnowledgeListResponse(BaseModel):
    success: bool
    data: List[KnowledgeItem]
    total: int
    page: int
    limit: int


class KnowledgeResponse(BaseModel):
    success: bool
    data: Optional[KnowledgeItem] = None
    error: Optional[str] = None


# =============================================================================
# Helper
# =============================================================================


def _get_supabase():
    """Supabaseクライアントを取得"""
    url = os.getenv("SUPABASE_URL", "")
    key = os.getenv("SUPABASE_KEY", "")
    if not url or not key:
        raise HTTPException(status_code=500, detail="Supabase configuration missing")
    return create_client(url, key)


def _row_to_item(row: Dict[str, Any]) -> KnowledgeItem:
    """DBレコードをKnowledgeItemに変換"""
    return KnowledgeItem(
        id=str(row["id"]),
        title=row.get("title", ""),
        content=row.get("content", ""),
        category=row.get("category"),
        subcategory=row.get("subcategory"),
        language=row.get("language"),
        source=row.get("source"),
        metadata=row.get("metadata"),
        created_at=str(row["created_at"]) if row.get("created_at") else None,
        updated_at=str(row["updated_at"]) if row.get("updated_at") else None,
    )


def _sanitize_keyword(keyword: str) -> str:
    """PostgRESTフィルタに渡すキーワードをサニタイズ

    PostgRESTのilike構文で特殊文字を安全にエスケープする。
    """
    # PostgREST filter DSLの特殊文字をエスケープ
    # カンマ、ドット、括弧はフィルタ構文で意味を持つ
    sanitized = re.sub(r"[,.()\[\]{}]", "", keyword)
    # 先頭・末尾の空白除去、連続空白を1つに
    sanitized = re.sub(r"\s+", " ", sanitized).strip()
    return sanitized


def _is_unique_violation(error: Exception) -> bool:
    """Supabaseエラーがユニーク制約違反かを判定"""
    error_str = str(error).lower()
    return "unique" in error_str or "duplicate" in error_str or "23505" in error_str


# =============================================================================
# Endpoints
# =============================================================================


@router.get("/knowledge", response_model=KnowledgeListResponse)
async def list_knowledge(
    category: Optional[str] = Query(None, description="カテゴリフィルタ"),
    keyword: Optional[str] = Query(None, max_length=200, description="キーワード検索"),
    language: Optional[str] = Query(None, pattern=r"^(ja|en)$", description="言語フィルタ"),
    page: int = Query(1, ge=1, description="ページ番号"),
    limit: int = Query(20, ge=1, le=100, description="1ページあたりの件数"),
):
    """ナレッジ一覧取得（フィルタ・ページネーション対応）"""
    try:
        supabase = _get_supabase()
        query = supabase.table("knowledge_base").select("*", count="exact")

        if category:
            query = query.eq("category", category)
        if language:
            query = query.eq("language", language)
        if keyword:
            safe_keyword = _sanitize_keyword(keyword)
            if safe_keyword:
                query = query.or_(f"title.ilike.%{safe_keyword}%,content.ilike.%{safe_keyword}%")

        offset = (page - 1) * limit
        query = query.order("created_at", desc=True).range(offset, offset + limit - 1)

        result = query.execute()

        items = [_row_to_item(row) for row in (result.data or [])]
        total = result.count if result.count is not None else len(items)

        return KnowledgeListResponse(
            success=True,
            data=items,
            total=total,
            page=page,
            limit=limit,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to list knowledge: {e}")
        raise HTTPException(status_code=500, detail="Failed to list knowledge entries")


@router.get("/knowledge/{knowledge_id}", response_model=KnowledgeResponse)
async def get_knowledge(knowledge_id: str):
    """ナレッジ単一取得"""
    try:
        supabase = _get_supabase()
        result = supabase.table("knowledge_base").select("*").eq("id", knowledge_id).execute()

        if not result.data:
            raise HTTPException(status_code=404, detail="Knowledge entry not found")

        return KnowledgeResponse(
            success=True,
            data=_row_to_item(result.data[0]),
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get knowledge {knowledge_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to get knowledge entry")


@router.post("/knowledge", response_model=KnowledgeResponse, status_code=201)
async def create_knowledge(request: KnowledgeCreateRequest):
    """テキスト入力でナレッジ新規登録（embedding自動生成）"""
    try:
        supabase = _get_supabase()

        # 重複titleチェック
        existing = (
            supabase.table("knowledge_base").select("id").eq("title", request.title).execute()
        )
        if existing.data:
            raise HTTPException(
                status_code=409, detail=f"Knowledge with title '{request.title}' already exists"
            )

        # Embedding生成
        embedding_text = f"{request.title}\n{request.content}"
        embedding = await generate_embedding(embedding_text)

        # DB挿入
        insert_data: Dict[str, Any] = {
            "title": request.title,
            "content": request.content,
            "category": request.category,
            "language": request.language,
            "subcategory": request.subcategory,
            "source": request.source,
            "metadata": request.metadata or {},
        }
        if embedding:
            insert_data["content_embedding"] = embedding

        result = supabase.table("knowledge_base").insert(insert_data).execute()

        if not result.data:
            raise HTTPException(status_code=500, detail="Failed to insert knowledge entry")

        return KnowledgeResponse(
            success=True,
            data=_row_to_item(result.data[0]),
        )

    except HTTPException:
        raise
    except Exception as e:
        if _is_unique_violation(e):
            raise HTTPException(
                status_code=409,
                detail=f"Knowledge with title '{request.title}' already exists",
            )
        logger.error(f"Failed to create knowledge: {e}")
        raise HTTPException(status_code=500, detail="Failed to create knowledge entry")


@router.post("/knowledge/upload", response_model=KnowledgeResponse, status_code=201)
async def upload_knowledge(
    file: UploadFile = File(...),
    category: str = Form(...),
    language: str = Form(default="ja"),
    title: Optional[str] = Form(default=None),
):
    """ファイルアップロードでナレッジ登録（.md/.pdf → パース → embedding生成）"""
    try:
        if not file.filename:
            raise HTTPException(status_code=400, detail="Filename is required")

        # language バリデーション
        if language not in ("ja", "en"):
            raise HTTPException(status_code=400, detail="language must be 'ja' or 'en'")

        # title長さバリデーション
        if title and len(title) > 200:
            raise HTTPException(status_code=400, detail="title must be 200 characters or less")

        file_type = detect_file_type(file.filename)
        if file_type not in ("markdown", "pdf"):
            raise HTTPException(
                status_code=400,
                detail=f"Unsupported file type: {file.filename}. Only .md and .pdf are supported.",
            )

        # ファイルサイズ制限チェック
        content_bytes = await file.read()
        if not content_bytes:
            raise HTTPException(status_code=400, detail="File is empty")
        if len(content_bytes) > MAX_UPLOAD_SIZE:
            raise HTTPException(
                status_code=400,
                detail=f"File too large. Maximum size is {MAX_UPLOAD_SIZE // (1024 * 1024)}MB.",
            )

        # パース（ValueErrorは400として処理）
        try:
            if file_type == "markdown":
                parsed_content = parse_markdown(content_bytes)
            else:
                parsed_content = parse_pdf(content_bytes)
        except ValueError as ve:
            raise HTTPException(status_code=400, detail=str(ve))

        if not parsed_content.strip():
            raise HTTPException(status_code=400, detail="No text content extracted from file")

        # 5000文字制限
        if len(parsed_content) > 5000:
            parsed_content = parsed_content[:5000]

        # titleが未指定の場合はファイル名から生成
        effective_title = title or file.filename.rsplit(".", 1)[0]

        supabase = _get_supabase()

        # 重複titleチェック
        existing = (
            supabase.table("knowledge_base").select("id").eq("title", effective_title).execute()
        )
        if existing.data:
            raise HTTPException(
                status_code=409,
                detail=f"Knowledge with title '{effective_title}' already exists",
            )

        # Embedding生成
        embedding_text = f"{effective_title}\n{parsed_content}"
        embedding = await generate_embedding(embedding_text)

        # DB挿入
        insert_data: Dict[str, Any] = {
            "title": effective_title,
            "content": parsed_content,
            "category": category,
            "language": language,
            "source": f"file:{file.filename}",
            "metadata": {"original_filename": file.filename, "file_type": file_type},
        }
        if embedding:
            insert_data["content_embedding"] = embedding

        result = supabase.table("knowledge_base").insert(insert_data).execute()

        if not result.data:
            raise HTTPException(status_code=500, detail="Failed to insert knowledge entry")

        return KnowledgeResponse(
            success=True,
            data=_row_to_item(result.data[0]),
        )

    except HTTPException:
        raise
    except Exception as e:
        if _is_unique_violation(e):
            raise HTTPException(
                status_code=409,
                detail=f"Knowledge with title '{effective_title}' already exists",
            )
        logger.error(f"Failed to upload knowledge: {e}")
        raise HTTPException(status_code=500, detail="Failed to upload knowledge entry")


@router.put("/knowledge/{knowledge_id}", response_model=KnowledgeResponse)
async def update_knowledge(knowledge_id: str, request: KnowledgeUpdateRequest):
    """ナレッジ更新（content変更時はembedding再生成）"""
    try:
        supabase = _get_supabase()

        # 存在確認
        existing = supabase.table("knowledge_base").select("*").eq("id", knowledge_id).execute()
        if not existing.data:
            raise HTTPException(status_code=404, detail="Knowledge entry not found")

        current = existing.data[0]

        # 重複titleチェック（titleが変更される場合）
        if request.title and request.title != current.get("title"):
            dup_check = (
                supabase.table("knowledge_base").select("id").eq("title", request.title).execute()
            )
            if dup_check.data:
                raise HTTPException(
                    status_code=409,
                    detail=f"Knowledge with title '{request.title}' already exists",
                )

        # 更新データ構築（Noneでない項目のみ）
        update_data: Dict[str, Any] = {}
        if request.title is not None:
            update_data["title"] = request.title
        if request.content is not None:
            update_data["content"] = request.content
        if request.category is not None:
            update_data["category"] = request.category
        if request.language is not None:
            update_data["language"] = request.language
        if request.subcategory is not None:
            update_data["subcategory"] = request.subcategory
        if request.source is not None:
            update_data["source"] = request.source
        if request.metadata is not None:
            update_data["metadata"] = request.metadata

        if not update_data:
            return KnowledgeResponse(success=True, data=_row_to_item(current))

        # content or titleが変更された場合はembedding再生成
        new_title = update_data.get("title", current.get("title", ""))
        new_content = update_data.get("content", current.get("content", ""))
        if "content" in update_data or "title" in update_data:
            embedding = await generate_embedding(f"{new_title}\n{new_content}")
            if embedding:
                update_data["content_embedding"] = embedding

        result = (
            supabase.table("knowledge_base").update(update_data).eq("id", knowledge_id).execute()
        )

        if not result.data:
            raise HTTPException(status_code=500, detail="Failed to update knowledge entry")

        return KnowledgeResponse(
            success=True,
            data=_row_to_item(result.data[0]),
        )

    except HTTPException:
        raise
    except Exception as e:
        if _is_unique_violation(e):
            raise HTTPException(
                status_code=409,
                detail=f"Knowledge with title '{request.title}' already exists",
            )
        logger.error(f"Failed to update knowledge {knowledge_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to update knowledge entry")


@router.delete("/knowledge/{knowledge_id}", response_model=KnowledgeResponse)
async def delete_knowledge(knowledge_id: str):
    """ナレッジ削除"""
    try:
        supabase = _get_supabase()

        # 存在確認
        existing = supabase.table("knowledge_base").select("*").eq("id", knowledge_id).execute()
        if not existing.data:
            raise HTTPException(status_code=404, detail="Knowledge entry not found")

        supabase.table("knowledge_base").delete().eq("id", knowledge_id).execute()

        return KnowledgeResponse(
            success=True,
            data=_row_to_item(existing.data[0]),
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to delete knowledge {knowledge_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to delete knowledge entry")
