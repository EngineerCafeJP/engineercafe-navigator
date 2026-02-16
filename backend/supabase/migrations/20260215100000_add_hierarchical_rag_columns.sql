-- Migration: Add hierarchical RAG support columns to knowledge_base
-- Architecture reference: docs/architecture/HIERARCHICAL-RAG-ARCHITECTURE.md
-- DO NOT apply directly - PM will review and apply

-- =============================================================================
-- 1. Add hierarchical structure columns
-- =============================================================================
ALTER TABLE knowledge_base ADD COLUMN IF NOT EXISTS parent_id UUID REFERENCES knowledge_base(id);
ALTER TABLE knowledge_base ADD COLUMN IF NOT EXISTS chunk_level VARCHAR(20) DEFAULT 'document';
ALTER TABLE knowledge_base ADD COLUMN IF NOT EXISTS chunk_index INT DEFAULT 0;
ALTER TABLE knowledge_base ADD COLUMN IF NOT EXISTS token_count INT;

-- Documentation comments
COMMENT ON COLUMN knowledge_base.parent_id IS 'Parent entry ID for hierarchical structure (document -> section -> chunk)';
COMMENT ON COLUMN knowledge_base.chunk_level IS 'Hierarchy level: document, section, or chunk';
COMMENT ON COLUMN knowledge_base.chunk_index IS 'Order index within parent';
COMMENT ON COLUMN knowledge_base.token_count IS 'Token count for this entry';

-- =============================================================================
-- 2. Indexes for hierarchical lookups
-- =============================================================================
CREATE INDEX IF NOT EXISTS idx_knowledge_base_parent_id ON knowledge_base(parent_id);
CREATE INDEX IF NOT EXISTS idx_knowledge_base_chunk_level ON knowledge_base(chunk_level);

-- =============================================================================
-- 3. Hierarchical search RPC function
-- =============================================================================
CREATE OR REPLACE FUNCTION search_knowledge_base_hierarchical(
  query_embedding vector(1536),
  match_count int DEFAULT 5,
  match_threshold float DEFAULT 0.35,
  filter_chunk_level varchar DEFAULT NULL
)
RETURNS TABLE (
  id uuid,
  title text,
  content text,
  category varchar,
  chunk_level varchar,
  parent_id uuid,
  chunk_index int,
  similarity float
)
LANGUAGE plpgsql
AS $$
BEGIN
  RETURN QUERY
  SELECT
    kb.id,
    kb.title::text,
    kb.content,
    kb.category,
    kb.chunk_level,
    kb.parent_id,
    kb.chunk_index,
    1 - (kb.content_embedding <=> query_embedding) AS similarity
  FROM knowledge_base kb
  WHERE
    kb.content_embedding IS NOT NULL
    AND 1 - (kb.content_embedding <=> query_embedding) > match_threshold
    AND (filter_chunk_level IS NULL OR kb.chunk_level = filter_chunk_level)
  ORDER BY kb.content_embedding <=> query_embedding
  LIMIT match_count;
END;
$$;

-- Grant execute permission
GRANT EXECUTE ON FUNCTION search_knowledge_base_hierarchical TO service_role;
