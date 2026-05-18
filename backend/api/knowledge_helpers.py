"""Helper functions for the knowledge API router."""

import logging
import os
import re
from typing import Any, Dict, List, Optional

from fastapi import HTTPException
from supabase import create_client

from backend.api.knowledge_models import (
    KnowledgeCategoriesResponse,
    KnowledgeCategoriesStats,
    KnowledgeItem,
)
from backend.knowledge.metadata import (
    MetadataReservedPolicy,
    MetadataValidationError,
    normalize_user_metadata,
)

logger = logging.getLogger(__name__)


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


def _rollback_uploaded_chunks(supabase: Any, inserted_ids: List[str]) -> None:
    """アップロード途中で失敗したチャンクを削除する"""
    for row_id in inserted_ids:
        try:
            supabase.table("knowledge_base").delete().eq("id", row_id).execute()
        except Exception:
            logger.error("Failed to rollback chunk %s", row_id)


def _metadata_document_id(row: Dict[str, Any]) -> Optional[str]:
    metadata = row.get("metadata")
    if not isinstance(metadata, dict):
        return None
    document_id = metadata.get("document_id")
    return str(document_id) if document_id else None


def _select_document_rows(supabase: Any, current: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Return all upload rows that share the current row's document identity."""

    document_id = _metadata_document_id(current)
    source = current.get("source")
    if not document_id or not source:
        return [current]

    try:
        result = supabase.table("knowledge_base").select("*").eq("source", source).execute()
    except Exception:
        logger.exception("Failed to load uploaded document rows for document_id=%s", document_id)
        raise HTTPException(status_code=503, detail="Knowledge storage unavailable")

    rows = [
        row
        for row in (result.data or [])
        if isinstance(row, dict) and _metadata_document_id(row) == document_id
    ]
    return rows or [current]


def _delete_rows_by_ids(supabase: Any, row_ids: List[str]) -> None:
    if not row_ids:
        return
    query = supabase.table("knowledge_base").delete()
    if len(row_ids) == 1:
        query.eq("id", row_ids[0]).execute()
    else:
        query.in_("id", row_ids).execute()


def _collapse_upload_metadata(
    current: Dict[str, Any],
    body_metadata: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    """Build metadata for an uploaded document collapsed back to one CRUD row."""

    metadata = dict(current.get("metadata") or {})
    if body_metadata is not None:
        metadata.update(body_metadata)
    document_id = metadata.get("document_id") or metadata.get("entry_id")
    if document_id:
        metadata["document_id"] = document_id
        metadata["entry_id"] = metadata.get("entry_id") or document_id
    metadata["chunk_level"] = "document"
    metadata["chunk_index"] = 0
    metadata["total_chunks"] = 1
    metadata["failed_chunks"] = []
    return metadata


def _build_duplicate_conflict(title: str, chunk_index: Optional[int] = None) -> Dict[str, Any]:
    """重複conflictオブジェクトを構築"""
    return {"title": title, "chunk_index": chunk_index}


def _build_duplicate_conflict_detail(
    conflicts: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """重複エラーの構造化detailを構築"""
    return {"message": "duplicate titles", "conflicts": conflicts}


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


def _normalize_api_metadata(
    metadata: Dict[str, Any] | None,
    *,
    reserved_policy: MetadataReservedPolicy = "reject",
) -> Dict[str, Any]:
    try:
        return normalize_user_metadata(metadata, reserved_policy=reserved_policy)
    except MetadataValidationError as exc:
        raise HTTPException(status_code=400, detail=f"Invalid metadata: {exc}") from exc


def build_knowledge_preview(
    *,
    file_type: str,
    filename: str,
    content_bytes: bytes,
    category: str,
    language: str,
    title: Optional[str] = None,
    max_chunks: int = 50,
    parse_markdown_fn=None,
    parse_pdf_fn=None,
    plan_upload_chunks_fn=None,
    upload_chunk_record_title_fn=None,
) -> Dict[str, Any]:
    """ファイルを解析して登録予定情報を返す（DBへは書き込まない）"""
    try:
        if file_type == "markdown":
            parsed_content = parse_markdown_fn(content_bytes, preserve_headings=True)
        else:
            parsed_content = parse_pdf_fn(content_bytes)
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))

    if not parsed_content.strip():
        raise HTTPException(status_code=400, detail="No text content extracted from file")

    chunk_plan = plan_upload_chunks_fn(
        parsed_content,
        filename=filename,
        category=category or "general",
        language=language,
        title=title,
    )
    chunks = list(chunk_plan.chunks)
    if not chunks:
        raise HTTPException(status_code=400, detail="No text content extracted from file")
    if len(chunks) > max_chunks:
        raise HTTPException(
            status_code=400,
            detail=f"Document too large: {len(chunks)} chunks exceeds limit of {max_chunks}",
        )

    chunk_titles = [upload_chunk_record_title_fn(chunk) for chunk in chunks]

    return {
        "file_type": file_type,
        "extracted_preview": parsed_content[:1500],
        "estimated_chunks": chunk_plan.total_chunks,
        "chunk_titles": chunk_titles,
        "total_chars": len(parsed_content),
    }
