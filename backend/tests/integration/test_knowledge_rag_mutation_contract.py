"""Admin knowledge mutation contracts that affect RAG retrieval.

These tests intentionally share an in-memory Supabase fake between the admin
knowledge API and EnhancedRAGSearch. They prove the API row mutations create the
retrieval-visible state that RAG actually consumes, without requiring live
Supabase or OpenRouter credentials.
"""

from __future__ import annotations

import copy
import io
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import backend.api.knowledge as knowledge_api
from backend.api.knowledge import router as knowledge_router
from backend.tools.enhanced_rag import EnhancedRAGSearch
from backend.utils.rate_limit import limiter

EMBEDDING_DIMENSIONS = 1536
OLD_VECTOR = [0.11] * EMBEDDING_DIMENSIONS
NEW_VECTOR = [0.22] * EMBEDDING_DIMENSIONS
UPLOAD_VECTOR_A = [0.33] * EMBEDDING_DIMENSIONS
UPLOAD_VECTOR_B = [0.44] * EMBEDDING_DIMENSIONS


@pytest.fixture(autouse=True)
def _reset_rate_limiter():
    if limiter is not None:
        try:
            limiter.reset()
        except Exception:
            pass


@pytest.fixture
def client() -> TestClient:
    app = FastAPI()
    app.include_router(knowledge_router, prefix="/api")
    return TestClient(app)


class _Result:
    def __init__(self, data: list[dict[str, Any]] | None = None, count: int | None = None):
        self.data = data
        self.count = count


class InMemorySupabase:
    def __init__(self):
        self.rows: list[dict[str, Any]] = []
        self.calls: list[tuple[Any, ...]] = []
        self.insert_payloads: list[dict[str, Any]] = []
        self.update_payloads: list[dict[str, Any]] = []
        self._next_id = 1

    def table(self, table_name: str):
        assert table_name == "knowledge_base"
        return _TableQuery(self)

    def rpc(self, rpc_name: str, params: dict[str, Any]):
        assert rpc_name == "search_knowledge_base"
        return _RpcQuery(self, params)

    def _allocate_id(self) -> str:
        row_id = f"rag-proof-{self._next_id}"
        self._next_id += 1
        return row_id


class _NotQuery:
    def __init__(self, query: "_TableQuery"):
        self.query = query

    def is_(self, field: str, value: Any):
        self.query.store.calls.append(("not_is", field, value))
        if value == "null":
            self.query.not_null_fields.append(field)
        return self.query


class _TableQuery:
    def __init__(self, store: InMemorySupabase):
        self.store = store
        self.operation = "select"
        self.payload: dict[str, Any] | None = None
        self.eq_filters: list[tuple[str, Any]] = []
        self.neq_filters: list[tuple[str, Any]] = []
        self.in_filters: list[tuple[str, list[Any]]] = []
        self.not_null_fields: list[str] = []
        self.limit_count: int | None = None

    @property
    def not_(self):
        return _NotQuery(self)

    def select(self, *_args, **_kwargs):
        self.operation = "select"
        return self

    def insert(self, payload: dict[str, Any]):
        self.operation = "insert"
        self.payload = copy.deepcopy(payload)
        self.store.insert_payloads.append(copy.deepcopy(payload))
        return self

    def update(self, payload: dict[str, Any]):
        self.operation = "update"
        self.payload = copy.deepcopy(payload)
        self.store.update_payloads.append(copy.deepcopy(payload))
        return self

    def delete(self):
        self.operation = "delete"
        return self

    def eq(self, field: str, value: Any):
        self.eq_filters.append((field, value))
        return self

    def neq(self, field: str, value: Any):
        self.neq_filters.append((field, value))
        return self

    def in_(self, field: str, values: list[Any]):
        self.in_filters.append((field, values))
        return self

    def order(self, *_args, **_kwargs):
        return self

    def range(self, *_args, **_kwargs):
        return self

    def limit(self, count: int):
        self.limit_count = count
        return self

    def execute(self):
        if self.operation == "insert":
            assert self.payload is not None
            row = {
                **self.payload,
                "id": self.store._allocate_id(),
                "created_at": "2026-05-09T00:00:00+00:00",
                "updated_at": "2026-05-09T00:00:00+00:00",
            }
            self.store.rows.append(row)
            return _Result([copy.deepcopy(row)])

        matches = self._matches()

        if self.operation == "update":
            assert self.payload is not None
            updated: list[dict[str, Any]] = []
            for row in self.store.rows:
                if any(row is match for match in matches):
                    row.update(copy.deepcopy(self.payload))
                    row["updated_at"] = "2026-05-09T00:00:01+00:00"
                    updated.append(copy.deepcopy(row))
            return _Result(updated)

        if self.operation == "delete":
            match_ids = {id(row) for row in matches}
            self.store.rows = [row for row in self.store.rows if id(row) not in match_ids]
            return _Result([])

        data = [copy.deepcopy(row) for row in matches]
        if self.limit_count is not None:
            data = data[: self.limit_count]
        return _Result(data, count=len(data))

    def _matches(self) -> list[dict[str, Any]]:
        rows = self.store.rows
        for field, value in self.eq_filters:
            rows = [row for row in rows if self._field_value(row, field) == value]
        for field, value in self.neq_filters:
            rows = [row for row in rows if self._field_value(row, field) != value]
        for field, values in self.in_filters:
            rows = [row for row in rows if self._field_value(row, field) in values]
        for field in self.not_null_fields:
            rows = [row for row in rows if self._field_value(row, field) is not None]
        return rows

    @staticmethod
    def _field_value(row: dict[str, Any], field: str) -> Any:
        if field.startswith("metadata->>"):
            metadata = row.get("metadata") or {}
            return metadata.get(field.removeprefix("metadata->>"))
        return row.get(field)


class _RpcQuery:
    def __init__(self, store: InMemorySupabase, params: dict[str, Any]):
        self.store = store
        self.params = params

    def execute(self):
        query_embedding = self.params["query_embedding"]
        match_count = self.params.get("match_count", 10)
        data = []
        for row in self.store.rows:
            if row.get("content_embedding") == query_embedding:
                data.append(
                    {
                        "id": row["id"],
                        "title": row["title"],
                        "content": row["content"],
                        "category": row.get("category"),
                        "subcategory": row.get("subcategory"),
                        "language": row.get("language"),
                        "source": row.get("source"),
                        "metadata": copy.deepcopy(row.get("metadata") or {}),
                        "similarity": 0.95,
                    }
                )
        return _Result(data[:match_count])


def _vector_for_text(text: str) -> list[float]:
    if "rag-updated-token-540" in text:
        return NEW_VECTOR
    if "rag-original-token-540" in text:
        return OLD_VECTOR
    if "Chunk A token 540" in text:
        return UPLOAD_VECTOR_A
    if "Chunk B token 540" in text:
        return UPLOAD_VECTOR_B
    return [0.99] * EMBEDDING_DIMENSIONS


async def _fake_generate_embedding(text: str) -> list[float]:
    return _vector_for_text(text)


async def _fake_missing_embedding(_text: str) -> list[float]:
    return []


def _rpc_contents_for_vector(store: InMemorySupabase, vector: list[float]) -> list[str]:
    result = store.rpc(
        "search_knowledge_base",
        {"query_embedding": vector, "match_count": 10},
    ).execute()
    return [row["content"] for row in result.data]


def _upload_contract_markdown() -> str:
    chunk_a = "Chunk A token 540 " + ("アップロード検索確認です。" * 30)
    chunk_b = "Chunk B token 540 " + ("別チャンク検索確認です。" * 30)
    return f"## Chunk A\n{chunk_a}\n\n## Chunk B\n{chunk_b}"


@pytest.mark.asyncio
async def test_admin_create_update_delete_mutates_rag_retrieval(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
):
    store = InMemorySupabase()
    monkeypatch.setattr(knowledge_api, "_get_supabase", lambda: store)
    monkeypatch.setattr(knowledge_api, "generate_embedding", _fake_generate_embedding)

    create_response = client.post(
        "/api/knowledge",
        json={
            "title": "RAG mutation proof",
            "content": "rag-original-token-540 content",
            "category": "general",
            "language": "ja",
        },
    )

    assert create_response.status_code == 201
    assert store.insert_payloads[0]["content_embedding"] == OLD_VECTOR

    rag = EnhancedRAGSearch(supabase_client=store)
    rag._generate_embedding = _fake_generate_embedding  # type: ignore[method-assign]

    original_result = await rag.search(
        "rag-original-token-540", category="general", language="ja", include_advice=False
    )
    assert "rag-original-token-540 content" in original_result["data"]["context"]

    knowledge_id = create_response.json()["data"]["id"]
    update_response = client.put(
        f"/api/knowledge/{knowledge_id}",
        json={"content": "rag-updated-token-540 content"},
    )

    assert update_response.status_code == 200
    assert store.update_payloads[-1]["content_embedding"] == NEW_VECTOR

    stale_result = await rag.search(
        "rag-original-token-540", category="general", language="ja", include_advice=False
    )
    assert stale_result["data"]["results"] == []

    updated_result = await rag.search(
        "rag-updated-token-540", category="general", language="ja", include_advice=False
    )
    assert "rag-updated-token-540 content" in updated_result["data"]["context"]

    delete_response = client.delete(f"/api/knowledge/{knowledge_id}")

    assert delete_response.status_code == 200
    deleted_result = await rag.search(
        "rag-updated-token-540", category="general", language="ja", include_advice=False
    )
    assert deleted_result["data"]["results"] == []


@pytest.mark.asyncio
async def test_text_fallback_search_excludes_rows_with_null_embeddings():
    store = InMemorySupabase()
    store.rows = [
        {
            "id": "null-row",
            "title": "Null row",
            "content": "wifi proof null embedding",
            "category": "general",
            "language": "ja",
            "metadata": {},
            "content_embedding": None,
        },
        {
            "id": "embedded-row",
            "title": "Embedded row",
            "content": "wifi proof embedded row",
            "category": "general",
            "language": "ja",
            "metadata": {},
            "content_embedding": OLD_VECTOR,
        },
    ]
    rag = EnhancedRAGSearch(supabase_client=store)

    results = await rag._text_fallback_search(
        "wifi proof", category="general", language="ja", max_results=10
    )

    assert [row["id"] for row in results] == ["embedded-row"]
    assert ("not_is", "content_embedding", "null") in store.calls


@pytest.mark.asyncio
async def test_upload_inserts_embedding_for_every_retrieval_visible_chunk(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
):
    store = InMemorySupabase()
    monkeypatch.setattr(knowledge_api, "_get_supabase", lambda: store)
    monkeypatch.setattr(knowledge_api, "generate_embedding", _fake_generate_embedding)
    monkeypatch.setattr(
        knowledge_api, "parse_markdown", lambda *_args, **_kwargs: _upload_contract_markdown()
    )

    response = client.post(
        "/api/knowledge/upload",
        data={"category": "pricing", "language": "ja"},
        files={"file": ("rag_upload.md", io.BytesIO(b"# Test"), "text/markdown")},
    )

    assert response.status_code == 201
    assert response.json()["data"]["metadata"]["failed_chunks"] == []
    assert [payload["content_embedding"] for payload in store.insert_payloads] == [
        UPLOAD_VECTOR_A,
        UPLOAD_VECTOR_A,
        UPLOAD_VECTOR_B,
    ]


def test_create_rejects_or_avoids_retrieval_invisible_null_embedding(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
):
    store = InMemorySupabase()
    monkeypatch.setattr(knowledge_api, "_get_supabase", lambda: store)
    monkeypatch.setattr(knowledge_api, "generate_embedding", _fake_missing_embedding)

    response = client.post(
        "/api/knowledge",
        json={
            "title": "Null embedding proof",
            "content": "rag-null-token-540 content",
            "category": "general",
            "language": "ja",
        },
    )

    assert response.status_code == 503
    assert response.json()["detail"] == "Embedding service unavailable"
    assert store.rows == []
    assert store.insert_payloads == []


def test_update_rejects_or_avoids_stale_embedding_when_reembedding_fails(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
):
    store = InMemorySupabase()
    store.rows = [
        {
            "id": "existing-row",
            "title": "Existing proof",
            "content": "rag-original-token-540 content",
            "category": "general",
            "language": "ja",
            "metadata": {},
            "content_embedding": OLD_VECTOR,
            "created_at": "2026-05-09T00:00:00+00:00",
            "updated_at": "2026-05-09T00:00:00+00:00",
        }
    ]
    monkeypatch.setattr(knowledge_api, "_get_supabase", lambda: store)
    monkeypatch.setattr(knowledge_api, "generate_embedding", _fake_missing_embedding)

    response = client.put(
        "/api/knowledge/existing-row",
        json={"content": "rag-updated-token-540 content"},
    )

    assert response.status_code == 503
    assert response.json()["detail"] == "Embedding service unavailable"
    assert store.rows[0]["content"] == "rag-original-token-540 content"
    assert store.rows[0]["content_embedding"] == OLD_VECTOR
    assert store.update_payloads == []


def test_uploaded_chunks_have_stable_document_identity_for_document_level_mutation(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
):
    store = InMemorySupabase()
    monkeypatch.setattr(knowledge_api, "_get_supabase", lambda: store)
    monkeypatch.setattr(knowledge_api, "generate_embedding", _fake_generate_embedding)
    monkeypatch.setattr(
        knowledge_api, "parse_markdown", lambda *_args, **_kwargs: _upload_contract_markdown()
    )

    response = client.post(
        "/api/knowledge/upload",
        data={"category": "pricing", "language": "ja"},
        files={"file": ("document_identity.md", io.BytesIO(b"# Test"), "text/markdown")},
    )

    assert response.status_code == 201
    document_ids = {payload["metadata"].get("document_id") for payload in store.insert_payloads}
    assert len(document_ids) == 1
    assert None not in document_ids


@pytest.mark.asyncio
async def test_delete_uploaded_document_removes_all_retrieval_visible_chunks(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
):
    store = InMemorySupabase()
    monkeypatch.setattr(knowledge_api, "_get_supabase", lambda: store)
    monkeypatch.setattr(knowledge_api, "generate_embedding", _fake_generate_embedding)
    monkeypatch.setattr(
        knowledge_api, "parse_markdown", lambda *_args, **_kwargs: _upload_contract_markdown()
    )

    response = client.post(
        "/api/knowledge/upload",
        data={"category": "pricing", "language": "ja"},
        files={"file": ("delete_document.md", io.BytesIO(b"# Test"), "text/markdown")},
    )

    assert response.status_code == 201
    assert len(store.rows) == 3
    knowledge_id = response.json()["data"]["id"]

    assert any(
        "Chunk B token 540" in content
        for content in _rpc_contents_for_vector(store, UPLOAD_VECTOR_B)
    )

    delete_response = client.delete(f"/api/knowledge/{knowledge_id}")

    assert delete_response.status_code == 200
    assert store.rows == []
    assert _rpc_contents_for_vector(store, UPLOAD_VECTOR_B) == []


@pytest.mark.asyncio
async def test_update_uploaded_document_collapses_stale_sibling_chunks(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
):
    store = InMemorySupabase()
    monkeypatch.setattr(knowledge_api, "_get_supabase", lambda: store)
    monkeypatch.setattr(knowledge_api, "generate_embedding", _fake_generate_embedding)
    monkeypatch.setattr(
        knowledge_api, "parse_markdown", lambda *_args, **_kwargs: _upload_contract_markdown()
    )

    response = client.post(
        "/api/knowledge/upload",
        data={"category": "pricing", "language": "ja"},
        files={"file": ("update_document.md", io.BytesIO(b"# Test"), "text/markdown")},
    )

    assert response.status_code == 201
    knowledge_id = response.json()["data"]["id"]
    assert len(store.rows) == 3

    update_response = client.put(
        f"/api/knowledge/{knowledge_id}",
        json={
            "title": "Updated upload proof",
            "content": "rag-updated-token-540 content",
        },
    )

    assert update_response.status_code == 200
    assert len(store.rows) == 1
    row = store.rows[0]
    assert row["title"] == "Updated upload proof"
    assert row["content"] == "rag-updated-token-540 content"
    assert row["content_embedding"] == NEW_VECTOR
    assert row["chunk_level"] == "document"
    assert row["chunk_index"] == 0
    assert row["metadata"]["total_chunks"] == 1

    assert _rpc_contents_for_vector(store, UPLOAD_VECTOR_B) == []
    assert "rag-updated-token-540 content" in _rpc_contents_for_vector(store, NEW_VECTOR)


def test_markdown_upload_preserves_section_chunks_through_real_parser_path(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
):
    store = InMemorySupabase()
    monkeypatch.setattr(knowledge_api, "_get_supabase", lambda: store)
    monkeypatch.setattr(knowledge_api, "generate_embedding", _fake_generate_embedding)

    response = client.post(
        "/api/knowledge/upload",
        data={"category": "pricing", "language": "ja"},
        files={
            "file": (
                "real_parser_sections.md",
                io.BytesIO(_upload_contract_markdown().encode("utf-8")),
                "text/markdown",
            )
        },
    )

    assert response.status_code == 201
    assert [payload["chunk_level"] for payload in store.insert_payloads] == [
        "document",
        "section",
        "section",
    ]
    assert [payload["chunk_index"] for payload in store.insert_payloads] == [0, 1, 2]
    assert all(isinstance(payload["token_count"], int) for payload in store.insert_payloads)
    assert store.insert_payloads[1]["metadata"]["section"] == "Chunk A"
    assert store.insert_payloads[2]["metadata"]["section"] == "Chunk B"
