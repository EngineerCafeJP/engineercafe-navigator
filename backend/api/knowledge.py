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
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, File, Form, HTTPException, Query, UploadFile
from starlette.requests import Request
from pydantic import BaseModel, Field
from supabase import create_client

from backend.utils.embedding_service import generate_embedding
from backend.utils.file_parser import detect_file_type, parse_markdown, parse_pdf
from backend.utils.rate_limit import rate_limit

logger = logging.getLogger(__name__)

router = APIRouter(tags=["knowledge"])

# 10MB upload size limit
MAX_UPLOAD_SIZE = 10 * 1024 * 1024


# =============================================================================
# Pydantic Models
# =============================================================================


class KnowledgeCreateRequest(BaseModel):
    title: str = Field(..., max_length=200)
    content: str = Field(..., max_length=50000)
    category: str
    language: str = Field(default="ja", pattern=r"^(ja|en)$")
    subcategory: Optional[str] = None
    source: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None


class KnowledgeUpdateRequest(BaseModel):
    title: Optional[str] = Field(None, max_length=200)
    content: Optional[str] = Field(None, max_length=50000)
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


class KnowledgeEditorConfig(BaseModel):
    categories: List[str]
    subcategories: Dict[str, List[str]]
    sources: List[str]
    languages: List[str]
    stats: Dict[str, int]
    templates: Dict[str, Dict[str, Any]]
    available_categories: List[str]


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


def _build_metadata_templates() -> Dict[str, Dict[str, Any]]:
    """メタデータテンプレートを構築

    エディタ起動時に使用される各カテゴリのデフォルト値を定義。
    """
    now = datetime.now(timezone.utc).isoformat()

    return {
        "設備": {
            "title": "",
            "importance": "high",
            "tags": [],
            "last_updated": now,
        },
        "Facilities": {
            "title": "",
            "importance": "high",
            "tags": [],
            "last_updated": now,
        },
        "基本情報": {
            "title": "",
            "importance": "critical",
            "tags": [],
            "last_updated": now,
        },
        "General": {
            "title": "",
            "importance": "critical",
            "tags": [],
            "last_updated": now,
        },
        "料金": {
            "title": "",
            "importance": "high",
            "tags": [],
            "last_updated": now,
        },
        "Pricing": {
            "title": "",
            "importance": "high",
            "tags": [],
            "last_updated": now,
        },
        "イベント": {
            "title": "",
            "importance": "medium",
            "tags": [],
            "last_updated": now,
        },
        "Events": {
            "title": "",
            "importance": "medium",
            "tags": [],
            "last_updated": now,
        },
        "アクセス": {
            "title": "",
            "importance": "high",
            "tags": [],
            "last_updated": now,
        },
        "Access": {
            "title": "",
            "importance": "high",
            "tags": [],
            "last_updated": now,
        },
        "slides": {
            "title": "",
            "importance": "critical",
            "slideNumber": 1,
            "last_updated": now,
        },
        "engineer-cafe": {
            "title": "",
            "importance": "high",
            "tags": [],
            "last_updated": now,
            "category": "engineer-cafe",
            "source": "engineercafe-structured-data",
        },
        "meeting-rooms": {
            "title": "",
            "importance": "high",
            "tags": [],
            "last_updated": now,
        },
        "saino-cafe": {
            "title": "",
            "importance": "medium",
            "tags": [],
            "last_updated": now,
        },
        "default": {
            "title": "",
            "importance": "medium",
            "tags": [],
            "last_updated": now,
        },
    }


# =============================================================================
# Endpoints
# =============================================================================


@router.get("/knowledge/editor-config", response_model=KnowledgeEditorConfig)
@rate_limit("60/minute")
async def get_editor_config(request: Request):
    """エディタ起動時の設定データを取得

    カテゴリ、サブカテゴリ、ソース、言語、メタデータテンプレートを
    単一のリクエストで返す。
    """
    try:
        supabase = _get_supabase()

        # Get all knowledge entries to extract distinct values
        all_entries_result = (
            supabase.table("knowledge_base")
            .select("category,subcategory,source,language")
            .execute()
        )

        entries = all_entries_result.data or []

        # Extract unique categories
        categories = list(dict.fromkeys([e["category"] for e in entries if e.get("category")]))

        # Extract subcategories grouped by category
        subcategories_dict: Dict[str, List[str]] = {}
        for entry in entries:
            if entry.get("category") and entry.get("subcategory"):
                cat = entry["category"]
                subcat = entry["subcategory"]
                if cat not in subcategories_dict:
                    subcategories_dict[cat] = []
                if subcat not in subcategories_dict[cat]:
                    subcategories_dict[cat].append(subcat)

        # Extract unique sources
        sources = list(dict.fromkeys([e["source"] for e in entries if e.get("source")]))

        # Extract unique languages
        languages = list(dict.fromkeys([e["language"] for e in entries if e.get("language")]))

        # Build metadata templates
        templates = _build_metadata_templates()

        # Calculate stats
        total_subcategories = sum(len(subs) for subs in subcategories_dict.values())
        stats = {
            "totalCategories": len(categories),
            "totalSubcategories": total_subcategories,
            "totalSources": len(sources),
            "totalLanguages": len(languages),
        }

        return KnowledgeEditorConfig(
            categories=categories,
            subcategories=subcategories_dict,
            sources=sources,
            languages=languages,
            stats=stats,
            templates=templates,
            available_categories=list(k for k in templates.keys() if k != "default"),
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to get editor config: %s", e)
        raise HTTPException(status_code=500, detail="Failed to get editor config")


@router.get("/knowledge", response_model=KnowledgeListResponse)
@rate_limit("60/minute")
async def list_knowledge(
    request: Request,
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
        logger.error("Failed to list knowledge: %s", e)
        raise HTTPException(status_code=500, detail="Failed to list knowledge entries")


@router.get("/knowledge/{knowledge_id}", response_model=KnowledgeResponse)
@rate_limit("60/minute")
async def get_knowledge(request: Request, knowledge_id: str):
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
        logger.error("Failed to get knowledge %s: %s", knowledge_id, e)
        raise HTTPException(status_code=500, detail="Failed to get knowledge entry")


@router.post("/knowledge", response_model=KnowledgeResponse, status_code=201)
@rate_limit("30/minute")
async def create_knowledge(request: Request, body: KnowledgeCreateRequest):
    """テキスト入力でナレッジ新規登録（embedding自動生成）"""
    try:
        supabase = _get_supabase()

        # 重複titleチェック
        existing = supabase.table("knowledge_base").select("id").eq("title", body.title).execute()
        if existing.data:
            raise HTTPException(
                status_code=409, detail=f"Knowledge with title '{body.title}' already exists"
            )

        # Embedding生成
        embedding_text = f"{body.title}\n{body.content}"
        embedding = await generate_embedding(embedding_text)

        # DB挿入
        insert_data: Dict[str, Any] = {
            "title": body.title,
            "content": body.content,
            "category": body.category,
            "language": body.language,
            "subcategory": body.subcategory,
            "source": body.source,
            "metadata": body.metadata or {},
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
                detail=f"Knowledge with title '{body.title}' already exists",
            )
        logger.error("Failed to create knowledge: %s", e)
        raise HTTPException(status_code=500, detail="Failed to create knowledge entry")


@router.post("/knowledge/upload", response_model=KnowledgeResponse, status_code=201)
@rate_limit("10/minute")
async def upload_knowledge(
    request: Request,
    file: UploadFile = File(...),
    category: str = Form(...),
    language: str = Form(default="ja"),
    title: Optional[str] = Form(default=None),
):
    """ファイルアップロードでナレッジ登録（.md/.pdf → パース → embedding生成）"""
    try:
        if not file.filename:
            raise HTTPException(status_code=400, detail="Filename is required")

        # Set default effective_title early so it's defined in all exception paths
        effective_title = title or (file.filename.rsplit(".", 1)[0] if file.filename else "unknown")

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

        # 50000文字制限（PDF数十ページ分に対応）
        if len(parsed_content) > 50000:
            parsed_content = parsed_content[:50000]

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
        logger.error("Failed to upload knowledge: %s", e)
        raise HTTPException(status_code=500, detail="Failed to upload knowledge entry")


@router.put("/knowledge/{knowledge_id}", response_model=KnowledgeResponse)
@rate_limit("30/minute")
async def update_knowledge(request: Request, knowledge_id: str, body: KnowledgeUpdateRequest):
    """ナレッジ更新（content変更時はembedding再生成）"""
    try:
        supabase = _get_supabase()

        # 存在確認
        existing = supabase.table("knowledge_base").select("*").eq("id", knowledge_id).execute()
        if not existing.data:
            raise HTTPException(status_code=404, detail="Knowledge entry not found")

        current = existing.data[0]

        # 重複titleチェック（titleが変更される場合）
        if body.title and body.title != current.get("title"):
            dup_check = (
                supabase.table("knowledge_base").select("id").eq("title", body.title).execute()
            )
            if dup_check.data:
                raise HTTPException(
                    status_code=409,
                    detail=f"Knowledge with title '{body.title}' already exists",
                )

        # 更新データ構築（Noneでない項目のみ）
        update_data: Dict[str, Any] = {}
        if body.title is not None:
            update_data["title"] = body.title
        if body.content is not None:
            update_data["content"] = body.content
        if body.category is not None:
            update_data["category"] = body.category
        if body.language is not None:
            update_data["language"] = body.language
        if body.subcategory is not None:
            update_data["subcategory"] = body.subcategory
        if body.source is not None:
            update_data["source"] = body.source
        if body.metadata is not None:
            update_data["metadata"] = body.metadata

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
                detail=f"Knowledge with title '{body.title}' already exists",
            )
        logger.error("Failed to update knowledge %s: %s", knowledge_id, e)
        raise HTTPException(status_code=500, detail="Failed to update knowledge entry")


@router.delete("/knowledge/{knowledge_id}", response_model=KnowledgeResponse)
@rate_limit("30/minute")
async def delete_knowledge(request: Request, knowledge_id: str):
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
        logger.error("Failed to delete knowledge %s: %s", knowledge_id, e)
        raise HTTPException(status_code=500, detail="Failed to delete knowledge entry")
