"""
Knowledge Base CRUD API Router

ナレッジベースのCRUD操作とファイルアップロードを提供する。
テキスト入力に加え、.mdと.pdfファイルのアップロードにも対応。
embedding生成は自動で行われる。
"""

import asyncio
import json
import logging
import os
import re
from typing import Any, Dict, List, Optional

import httpx
from fastapi import APIRouter, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse
from postgrest import APIError
from starlette.requests import Request
from pydantic import BaseModel, Field
from supabase import create_client

from backend.utils.embedding_service import generate_embedding
from backend.utils.file_parser import chunk_text, detect_file_type, parse_markdown, parse_pdf
from backend.utils.rate_limit import rate_limit

logger = logging.getLogger(__name__)

router = APIRouter(tags=["knowledge"])

# 10MB upload size limit
MAX_UPLOAD_SIZE = 10 * 1024 * 1024
MAX_CHUNKS = 50


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


class KnowledgeCategoriesStats(BaseModel):
    totalCategories: int
    totalSubcategories: int
    totalSources: int
    totalLanguages: int


class KnowledgeCategoriesResponse(BaseModel):
    categories: List[str]
    subcategories: Dict[str, List[str]]
    sources: List[str]
    languages: List[str]
    stats: KnowledgeCategoriesStats


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


def _chunk_title(base_title: str, index: int, total_chunks: int) -> str:
    """チャンク数に応じた保存タイトルを返す"""
    if total_chunks <= 1:
        return base_title
    return f"{base_title} (part {index + 1})"


def _rollback_uploaded_chunks(supabase: Any, inserted_ids: List[str]) -> None:
    """アップロード途中で失敗したチャンクを削除する"""
    for row_id in inserted_ids:
        try:
            supabase.table("knowledge_base").delete().eq("id", row_id).execute()
        except Exception:
            logger.error("Failed to rollback chunk %s", row_id)


def _build_knowledge_categories_response(supabase: Any) -> KnowledgeCategoriesResponse:
    """カテゴリ関連の編集設定データを構築する

    単一クエリで必要な4カラムのみ取得し、Python側で重複排除する。
    Supabase REST APIはSELECT DISTINCTを直接サポートしないため、
    カラム指定 + Python setで代替する。
    """
    result = (
        supabase.table("knowledge_base").select("category, subcategory, source, language").execute()
    )
    rows = result.data or []

    categories: set[str] = set()
    subcategory_sets: Dict[str, set[str]] = {}
    sources: set[str] = set()
    languages: set[str] = set()

    for row in rows:
        cat = row.get("category")
        sub = row.get("subcategory")
        src = row.get("source")
        lang = row.get("language")

        if cat:
            categories.add(cat)
            if sub:
                subcategory_sets.setdefault(cat, set()).add(sub)
        if src:
            sources.add(src)
        if lang:
            languages.add(lang)

    sorted_categories = sorted(categories)
    sorted_subcategories = {
        category: sorted(values) for category, values in sorted(subcategory_sets.items())
    }
    sorted_sources = sorted(sources)
    sorted_languages = sorted(languages)

    return KnowledgeCategoriesResponse(
        categories=sorted_categories,
        subcategories=sorted_subcategories,
        sources=sorted_sources,
        languages=sorted_languages,
        stats=KnowledgeCategoriesStats(
            totalCategories=len(sorted_categories),
            totalSubcategories=sum(len(values) for values in sorted_subcategories.values()),
            totalSources=len(sorted_sources),
            totalLanguages=len(sorted_languages),
        ),
    )


# =============================================================================
# Endpoints
# =============================================================================


@router.get("/knowledge/categories", response_model=KnowledgeCategoriesResponse)
@rate_limit("60/minute")
async def get_knowledge_categories(request: Request):
    """ナレッジカテゴリ一覧取得"""
    try:
        return await asyncio.to_thread(_build_knowledge_categories_response, _get_supabase())
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to get knowledge categories: %s", e)
        raise HTTPException(status_code=500, detail="Failed to get knowledge categories")


@router.get("/knowledge/editor-config", response_model=KnowledgeCategoriesResponse)
@rate_limit("60/minute")
async def get_editor_config(request: Request):
    """エディタ起動時の設定データを取得"""
    try:
        return await asyncio.to_thread(_build_knowledge_categories_response, _get_supabase())
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to get knowledge editor config: %s", e)
        raise HTTPException(status_code=500, detail="Failed to get knowledge editor config")


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
    subcategory: Optional[str] = Form(default=None),
    metadata: Optional[str] = Form(default=None),
):
    """ファイルアップロードでナレッジ登録（.md/.pdf → パース → embedding生成）"""
    effective_title = title or (file.filename.rsplit(".", 1)[0] if file.filename else "unknown")
    file_type = "unknown"
    content_size = 0

    async def _perform_upload() -> KnowledgeResponse:
        nonlocal effective_title, file_type, content_size

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

        metadata_payload: Dict[str, Any] = {}
        if metadata:
            try:
                parsed_metadata = json.loads(metadata)
            except json.JSONDecodeError as exc:
                raise HTTPException(status_code=400, detail="metadata must be valid JSON") from exc

            if not isinstance(parsed_metadata, dict):
                raise HTTPException(status_code=400, detail="metadata must be a JSON object")

            metadata_payload = parsed_metadata

        file_type = detect_file_type(file.filename)
        if file_type not in ("markdown", "pdf"):
            raise HTTPException(
                status_code=400,
                detail=f"Unsupported file type: {file.filename}. Only .md and .pdf are supported.",
            )

        # ファイルサイズ制限チェック
        content_bytes = await file.read()
        content_size = len(content_bytes)
        if not content_bytes:
            raise HTTPException(status_code=400, detail="File is empty")
        if content_size > MAX_UPLOAD_SIZE:
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

        # titleが未指定の場合はファイル名から生成
        effective_title = title or file.filename.rsplit(".", 1)[0]

        supabase = _get_supabase()
        chunks = chunk_text(parsed_content)
        if not chunks:
            raise HTTPException(status_code=400, detail="No text content extracted from file")
        if len(chunks) > MAX_CHUNKS:
            raise HTTPException(
                status_code=400,
                detail=f"Document too large: {len(chunks)} chunks exceeds limit of {MAX_CHUNKS}",
            )

        chunk_titles = [
            _chunk_title(effective_title, index, len(chunks)) for index in range(len(chunks))
        ]
        if any(len(chunk_title) > 200 for chunk_title in chunk_titles):
            raise HTTPException(
                status_code=400,
                detail="title must be 200 characters or less after chunk suffixes are applied",
            )

        existing = (
            supabase.table("knowledge_base").select("title").in_("title", chunk_titles).execute()
        )
        if existing.data:
            existing_titles = {row["title"] for row in existing.data}
            conflicts = [
                {"chunk_index": i, "title": chunk_titles[i]}
                for i in range(len(chunk_titles))
                if chunk_titles[i] in existing_titles
            ]
            raise HTTPException(
                status_code=409,
                detail={"message": "duplicate titles", "conflicts": conflicts},
            )

        inserted_rows: List[Dict[str, Any]] = []
        inserted_ids: List[str] = []
        total_chunks = len(chunks)

        try:
            for index, chunk_content in enumerate(chunks):
                chunk_title = chunk_titles[index]
                embedding: List[float] = []
                embedding_input = (
                    f"{chunk_title}\n{chunk_content}" if total_chunks == 1 else chunk_content
                )
                try:
                    embedding = await generate_embedding(embedding_input)
                    if not embedding:
                        logger.warning(
                            "Embedding unavailable for upload: filename=%s title=%s "
                            "file_type=%s content_size=%s chunk=%s/%s",
                            file.filename,
                            chunk_title,
                            file_type,
                            content_size,
                            index + 1,
                            total_chunks,
                        )
                except httpx.TimeoutException as exc:
                    logger.warning(
                        "Embedding generation timed out for upload: filename=%s title=%s "
                        "file_type=%s content_size=%s chunk=%s/%s error=%s",
                        file.filename,
                        chunk_title,
                        file_type,
                        content_size,
                        index + 1,
                        total_chunks,
                        exc,
                    )
                    embedding = []
                except Exception as exc:
                    logger.warning(
                        "Embedding generation failed for upload (%s): filename=%s title=%s "
                        "file_type=%s content_size=%s chunk=%s/%s error=%s",
                        type(exc).__name__,
                        file.filename,
                        chunk_title,
                        file_type,
                        content_size,
                        index + 1,
                        total_chunks,
                        exc,
                    )
                    embedding = []

                insert_data: Dict[str, Any] = {
                    "title": chunk_title,
                    "content": chunk_content,
                    "category": category,
                    "subcategory": subcategory,
                    "language": language,
                    "source": f"file:{file.filename}",
                    "metadata": {
                        "original_filename": file.filename,
                        "file_type": file_type,
                        "chunk_index": index,
                        "total_chunks": total_chunks,
                        **metadata_payload,
                    },
                }
                if embedding:
                    insert_data["content_embedding"] = embedding

                result = supabase.table("knowledge_base").insert(insert_data).execute()
                if not result.data:
                    raise HTTPException(status_code=500, detail="Failed to insert knowledge entry")

                inserted_rows.append(result.data[0])
                inserted_ids.append(str(result.data[0]["id"]))
        except APIError as exc:
            _rollback_uploaded_chunks(supabase, inserted_ids)
            if _is_unique_violation(exc):
                exc_str = str(exc)
                conflict_title = next(
                    (ct for ct in chunk_titles if ct in exc_str),
                    effective_title,
                )
                conflict_index = next(
                    (i for i, ct in enumerate(chunk_titles) if ct == conflict_title),
                    None,
                )
                raise HTTPException(
                    status_code=409,
                    detail={
                        "message": "duplicate titles",
                        "conflicts": [{"chunk_index": conflict_index, "title": conflict_title}],
                    },
                )
            logger.error(
                "Supabase insert failed: table=knowledge_base title=%s filename=%s error=%s",
                effective_title,
                file.filename,
                exc,
            )
            raise HTTPException(status_code=503, detail="Knowledge storage unavailable")
        except httpx.HTTPError as exc:
            _rollback_uploaded_chunks(supabase, inserted_ids)
            logger.error(
                "Supabase insert failed: table=knowledge_base title=%s filename=%s error=%s",
                effective_title,
                file.filename,
                exc,
            )
            raise HTTPException(status_code=503, detail="Knowledge storage unavailable")
        except Exception:
            _rollback_uploaded_chunks(supabase, inserted_ids)
            raise

        response_row = dict(inserted_rows[0])
        response_metadata = dict(response_row.get("metadata") or {})
        response_metadata["chunks_created"] = total_chunks
        response_row["metadata"] = response_metadata

        return KnowledgeResponse(
            success=True,
            data=_row_to_item(response_row),
        )

    try:
        return await asyncio.wait_for(_perform_upload(), timeout=60)
    except HTTPException:
        raise
    except asyncio.TimeoutError:
        logger.error(
            "Knowledge upload timed out after 60 seconds: filename=%s file_type=%s content_size=%s",
            file.filename,
            file_type,
            content_size,
        )
        raise HTTPException(status_code=504, detail="Knowledge upload timed out")
    except Exception as e:
        if _is_unique_violation(e):
            raise HTTPException(
                status_code=409,
                detail={
                    "message": "duplicate titles",
                    "conflicts": [{"chunk_index": None, "title": effective_title}],
                },
            )
        logger.error(
            "Failed to upload knowledge (%s): %s; filename=%s file_type=%s content_size=%s",
            type(e).__name__,
            e,
            file.filename,
            file_type,
            content_size,
        )
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


@router.get("/knowledge/templates/{filename}")
@rate_limit("30/minute")
async def download_template(request: Request, filename: str):
    """テンプレートファイルをダウンロードする"""
    allowed_files = {"knowledge-template.md", "knowledge-pdf-template-guide.md"}

    if filename not in allowed_files:
        raise HTTPException(status_code=404, detail="Template not found")

    templates_dir = os.path.join(os.path.dirname(__file__), "..", "static", "templates")
    file_path = os.path.join(templates_dir, filename)

    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="File not found")

    return FileResponse(
        path=file_path,
        media_type="application/octet-stream",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
