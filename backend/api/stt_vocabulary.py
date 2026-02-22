"""
STT Custom Vocabulary API Router

Vosk STT の認識精度向上のためのカスタム語彙管理 API。
語彙は backend/data/stt_vocabulary.json に保存される。
"""

import asyncio
import base64
import json
import logging
import os
import uuid
from datetime import datetime, timezone
from typing import Dict, List, Literal, Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from backend.agents.stt_agent import LocalSTTClient

logger = logging.getLogger(__name__)

router = APIRouter(tags=["stt-vocabulary"])

# JSONファイルのパス（このファイルから見た相対パスで解決）
_DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")
VOCABULARY_FILE = os.path.join(_DATA_DIR, "stt_vocabulary.json")

# ファイル読み書きの排他制御
_file_lock = asyncio.Lock()

VocabularyCategory = Literal[
    "facility",
    "location",
    "service",
    "event",
    "person",
    "tech",
    "organization",
]


# =============================================================================
# Pydantic Models
# =============================================================================


class VocabularyItem(BaseModel):
    id: str
    word: str
    reading: str
    category: VocabularyCategory
    priority: int = Field(default=5, ge=1, le=10)
    created_at: str
    updated_at: str


class VocabularyCreateRequest(BaseModel):
    word: str = Field(..., min_length=1, max_length=100)
    reading: str = Field(..., min_length=1, max_length=100)
    category: VocabularyCategory
    priority: int = Field(default=5, ge=1, le=10)


class VocabularyUpdateRequest(BaseModel):
    word: Optional[str] = Field(None, min_length=1, max_length=100)
    reading: Optional[str] = Field(None, min_length=1, max_length=100)
    category: Optional[VocabularyCategory] = None
    priority: Optional[int] = Field(None, ge=1, le=10)


class VocabularyStats(BaseModel):
    total: int
    byCategory: Dict[str, int]


class VocabularyListResponse(BaseModel):
    success: bool
    data: List[VocabularyItem]
    total: int
    page: int
    limit: int
    stats: VocabularyStats


class VocabularyResponse(BaseModel):
    success: bool
    data: Optional[VocabularyItem] = None
    error: Optional[str] = None


class VocabularyTestRequest(BaseModel):
    audio_base64: str = Field(..., description="base64エンコードされたWAV音声データ")
    language: str = Field(default="ja", pattern=r"^(ja|en)$")
    category: Optional[VocabularyCategory] = Field(
        None, description="テスト対象カテゴリ（未指定時は全語彙）"
    )


class VocabularyTestResponse(BaseModel):
    success: bool
    transcript: Optional[str] = None
    grammar_words: List[str] = []
    error: Optional[str] = None


# =============================================================================
# File I/O helpers
# =============================================================================


def _load_vocabulary_sync() -> List[dict]:
    """JSONファイルから語彙一覧を同期的に読み込む"""
    if not os.path.exists(VOCABULARY_FILE):
        return []
    with open(VOCABULARY_FILE, encoding="utf-8") as f:
        data = json.load(f)
    return data.get("vocabulary", [])


def _save_vocabulary_sync(vocabulary: List[dict]) -> None:
    """語彙一覧をJSONファイルに同期的に書き出す"""
    os.makedirs(os.path.dirname(VOCABULARY_FILE), exist_ok=True)
    with open(VOCABULARY_FILE, "w", encoding="utf-8") as f:
        json.dump({"vocabulary": vocabulary}, f, ensure_ascii=False, indent=2)


async def _load_vocabulary() -> List[dict]:
    async with _file_lock:
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, _load_vocabulary_sync)


async def _save_vocabulary(vocabulary: List[dict]) -> None:
    async with _file_lock:
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, _save_vocabulary_sync, vocabulary)


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# =============================================================================
# Grammar helpers
# =============================================================================


def build_grammar_words(vocabulary: List[dict], category: Optional[str] = None) -> List[str]:
    """語彙リストをVosk Grammar用の単語リストに変換する。

    Args:
        vocabulary: 語彙レコードのリスト
        category: カテゴリフィルタ（未指定時は全語彙）

    Returns:
        ["word1", "word2", "[unk]"] 形式のリスト（[unk]で未知語も認識可能）
    """
    filtered = (
        vocabulary if category is None else [v for v in vocabulary if v["category"] == category]
    )
    # priority降順でソート
    filtered = sorted(filtered, key=lambda v: v.get("priority", 5), reverse=True)
    words = [v["word"] for v in filtered]
    words.append("[unk]")
    return words


# =============================================================================
# Endpoints
# =============================================================================


@router.get("/stt/vocabulary", response_model=VocabularyListResponse)
async def list_vocabulary(
    category: Optional[VocabularyCategory] = None,
    search: Optional[str] = Query(None, max_length=100),
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
):
    """登録済みカスタム語彙一覧取得"""
    all_items = await _load_vocabulary()

    # 統計情報（フィルタ前に全件ベースで算出）
    all_categories = ["facility", "location", "service", "event", "person", "tech", "organization"]
    by_category = {cat: sum(1 for v in all_items if v.get("category") == cat) for cat in all_categories}
    stats = VocabularyStats(total=len(all_items), byCategory=by_category)

    # フィルタリング
    items = all_items
    if category:
        items = [v for v in items if v["category"] == category]
    if search:
        lower_search = search.lower()
        items = [
            v for v in items
            if lower_search in v.get("word", "").lower()
            or lower_search in v.get("reading", "").lower()
        ]

    total = len(items)

    # ページネーション
    start = (page - 1) * limit
    paginated = items[start : start + limit]

    return VocabularyListResponse(
        success=True,
        data=[VocabularyItem(**v) for v in paginated],
        total=total,
        page=page,
        limit=limit,
        stats=stats,
    )


@router.post("/stt/vocabulary/test", response_model=VocabularyTestResponse)
async def test_vocabulary(request: VocabularyTestRequest):
    """テスト音声で認識精度確認

    base64エンコードされたWAVを受け取り、カスタム語彙Grammarを使って
    Voskで認識し結果を返す。
    """
    try:
        audio_bytes = base64.b64decode(request.audio_base64)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid base64 audio data")

    vocabulary = await _load_vocabulary()
    grammar_words = build_grammar_words(vocabulary, category=request.category)

    try:
        client = LocalSTTClient()
        result = await client.transcribe(
            audio_bytes, language=request.language, grammar=grammar_words
        )
        return VocabularyTestResponse(
            success=True,
            transcript=result.text,
            grammar_words=grammar_words,
        )
    except Exception as e:
        logger.error("STT test failed: %s", e)
        return VocabularyTestResponse(
            success=False,
            grammar_words=grammar_words,
            error=str(e),
        )


@router.post("/stt/vocabulary", response_model=VocabularyResponse, status_code=201)
async def create_vocabulary(request: VocabularyCreateRequest):
    """語彙追加"""
    vocabulary = await _load_vocabulary()

    # 重複チェック
    if any(v["word"] == request.word for v in vocabulary):
        raise HTTPException(status_code=409, detail=f"Word '{request.word}' already exists")

    now = _now_iso()
    new_item = {
        "id": str(uuid.uuid4()),
        "word": request.word,
        "reading": request.reading,
        "category": request.category,
        "priority": request.priority,
        "created_at": now,
        "updated_at": now,
    }
    vocabulary.append(new_item)
    await _save_vocabulary(vocabulary)

    return VocabularyResponse(success=True, data=VocabularyItem(**new_item))


@router.put("/stt/vocabulary/{vocabulary_id}", response_model=VocabularyResponse)
async def update_vocabulary(vocabulary_id: str, request: VocabularyUpdateRequest):
    """語彙編集"""
    vocabulary = await _load_vocabulary()

    idx = next((i for i, v in enumerate(vocabulary) if v["id"] == vocabulary_id), None)
    if idx is None:
        raise HTTPException(status_code=404, detail="Vocabulary entry not found")

    # word変更時の重複チェック
    if request.word and request.word != vocabulary[idx]["word"]:
        if any(v["word"] == request.word for v in vocabulary):
            raise HTTPException(status_code=409, detail=f"Word '{request.word}' already exists")

    item = vocabulary[idx]
    if request.word is not None:
        item["word"] = request.word
    if request.reading is not None:
        item["reading"] = request.reading
    if request.category is not None:
        item["category"] = request.category
    if request.priority is not None:
        item["priority"] = request.priority
    item["updated_at"] = _now_iso()

    vocabulary[idx] = item
    await _save_vocabulary(vocabulary)

    return VocabularyResponse(success=True, data=VocabularyItem(**item))


@router.delete("/stt/vocabulary/{vocabulary_id}", response_model=VocabularyResponse)
async def delete_vocabulary(vocabulary_id: str):
    """語彙削除"""
    vocabulary = await _load_vocabulary()

    idx = next((i for i, v in enumerate(vocabulary) if v["id"] == vocabulary_id), None)
    if idx is None:
        raise HTTPException(status_code=404, detail="Vocabulary entry not found")

    removed = vocabulary.pop(idx)
    await _save_vocabulary(vocabulary)

    return VocabularyResponse(success=True, data=VocabularyItem(**removed))
