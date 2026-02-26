"""E2E tests for memory promotion using a real AsyncPostgresStore."""

import os
import uuid

import pytest

from langgraph.store.postgres.aio import AsyncPostgresStore

from backend.services.memory_promoter import MemoryPromoter


@pytest.mark.e2e
class TestMemoryPromotionStoreE2E:
    async def test_promotes_repeated_candidates_to_long_term_memory(self):
        db_uri = os.getenv("SUPABASE_DB_URI")
        if not db_uri:
            pytest.skip("SUPABASE_DB_URI not set")

        user_id = f"promoter-e2e-{uuid.uuid4().hex[:8]}"
        candidate_ns = ("visitor_memory_candidates", user_id)
        long_term_ns = ("visitor_memories", user_id)

        async with AsyncPostgresStore.from_conn_string(db_uri) as store:
            await store.setup()
            promoter = MemoryPromoter()

            keys_to_cleanup: list[tuple[tuple[str, str], str]] = []
            try:
                # Repeat the same candidate twice so the promotion rule passes.
                for i in range(2):
                    key = str(uuid.uuid4())
                    keys_to_cleanup.append((candidate_ns, key))
                    await store.aput(
                        candidate_ns,
                        key,
                        {
                            "status": "candidate",
                            "candidate_type": "visitor_name",
                            "content": "田中",
                            "confidence": 0.95,
                            "repeat_count": 1,
                            "extracted_at": 1_700_000_000 + i,
                        },
                    )

                stats = await promoter.promote_for_user(store, user_id)
                assert stats["promoted"] >= 1

                items = await store.asearch(long_term_ns, query="田中", limit=20)
                found = [it for it in items if it.value.get("data") == "田中"]
                assert found, "promoted long-term memory not found"
                assert found[0].value.get("source") in {"promoter", None}
            finally:
                # Cleanup both candidate and long-term namespaces
                for ns in (candidate_ns, long_term_ns):
                    try:
                        items = await store.asearch(ns, query="", limit=200)
                        for it in items:
                            await store.adelete(ns, it.key)
                    except Exception:
                        pass

