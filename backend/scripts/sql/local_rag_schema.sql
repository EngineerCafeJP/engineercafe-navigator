-- =============================================================================
-- ローカルpgvector RAGスキーマ（COSCUPデモ用・完全オフライン）
-- =============================================================================
--
-- 注意: knowledge_embeddings.embedding の次元数は EMBEDDING_DIMENSIONS
--       環境変数（デフォルト1536）と一致させること。
--       seed_local_knowledge.py が --dims / EMBEDDING_DIMENSIONS に応じて
--       vector(1536) を差し替えるため、別次元で使う場合はシード時に合わせる。
-- 注意: 同一YAMLエントリを言語別（ja/en）に2行格納するため、主キーは
--       (id, language) の複合キーとしている（id単独ではja/enの両行を保持できない）。

-- pgvector拡張（docker-compose の postgres は pgvector/pgvector:pg16 イメージを使用）
CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS knowledge_embeddings (
    id text NOT NULL,
    title text NOT NULL,
    content text NOT NULL,
    category text NOT NULL DEFAULT 'general',
    subcategory text,
    language text NOT NULL,
    metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
    embedding vector(1536) NOT NULL,
    PRIMARY KEY (id, language)
);

-- HNSWインデックス（小規模データで追加構築不要・近似最近傍検索を高速化）
CREATE INDEX IF NOT EXISTS knowledge_embeddings_embedding_hnsw_idx
    ON knowledge_embeddings USING hnsw (embedding vector_cosine_ops);

-- コサイン類似度によるローカルベクトル検索関数（Supabase RPC互換の行コントラクト）
CREATE OR REPLACE FUNCTION search_knowledge_base_local(
    p_query_embedding vector,
    p_similarity_threshold float,
    p_match_count int
)
RETURNS TABLE (
    id text,
    title text,
    content text,
    category text,
    subcategory text,
    language text,
    metadata jsonb,
    similarity float
)
LANGUAGE sql
STABLE
AS $$
    SELECT
        ke.id,
        ke.title,
        ke.content,
        ke.category,
        ke.subcategory,
        ke.language,
        ke.metadata,
        1 - (ke.embedding <=> p_query_embedding) AS similarity
    FROM knowledge_embeddings ke
    WHERE 1 - (ke.embedding <=> p_query_embedding) > p_similarity_threshold
    ORDER BY ke.embedding <=> p_query_embedding ASC
    LIMIT p_match_count;
$$;
