-- Migration: Add title column and restore 1536d embedding dimensions
-- Issue #71: Knowledge Base CRUD API support

-- =============================================================================
-- 1. Add title column to knowledge_base
-- =============================================================================
ALTER TABLE knowledge_base ADD COLUMN IF NOT EXISTS title varchar(200);

-- Populate title for existing rows, handling duplicate prefixes with row_number
-- Each row gets a unique title based on first 50 chars + optional suffix
WITH numbered AS (
  SELECT id, LEFT(content, 50) AS base_title,
         ROW_NUMBER() OVER (PARTITION BY LEFT(content, 50) ORDER BY created_at) AS rn
  FROM knowledge_base
  WHERE title IS NULL
)
UPDATE knowledge_base kb
SET title = CASE
  WHEN n.rn = 1 THEN n.base_title
  ELSE n.base_title || ' (' || n.rn || ')'
END
FROM numbered n
WHERE kb.id = n.id;

-- Make title NOT NULL after populating
ALTER TABLE knowledge_base ALTER COLUMN title SET NOT NULL;

-- Add UNIQUE constraint for title (used by seed_knowledge.py upsert)
ALTER TABLE knowledge_base ADD CONSTRAINT knowledge_base_title_unique UNIQUE (title);

-- =============================================================================
-- 2. Restore content_embedding to vector(1536)
--    Previous migration (20250613000001) changed it to 768d,
--    but code uses openai/text-embedding-3-small which outputs 1536d
-- =============================================================================
ALTER TABLE knowledge_base DROP COLUMN IF EXISTS content_embedding;
ALTER TABLE knowledge_base ADD COLUMN content_embedding vector(1536);

-- Recreate ivfflat index for 1536d vectors
DROP INDEX IF EXISTS idx_knowledge_base_embedding;
DROP INDEX IF EXISTS idx_knowledge_base_embedding_cosine;
CREATE INDEX idx_knowledge_base_embedding ON knowledge_base
  USING ivfflat (content_embedding vector_cosine_ops);

-- =============================================================================
-- 3. Update search_knowledge_base() RPC to include title in results
--    DROP first because OR REPLACE cannot change return type
-- =============================================================================
DROP FUNCTION IF EXISTS search_knowledge_base(vector, float, int);

CREATE FUNCTION search_knowledge_base(
  query_embedding vector(1536),
  similarity_threshold float DEFAULT 0.7,
  match_count int DEFAULT 5
)
RETURNS TABLE (
  id uuid,
  title varchar(200),
  content text,
  category varchar(50),
  subcategory varchar(50),
  language varchar(2),
  source varchar(255),
  metadata jsonb,
  similarity float
)
LANGUAGE plpgsql
AS $$
BEGIN
  RETURN QUERY
  SELECT
    kb.id,
    kb.title,
    kb.content,
    kb.category,
    kb.subcategory,
    kb.language,
    kb.source,
    kb.metadata,
    1 - (kb.content_embedding <=> query_embedding) AS similarity
  FROM knowledge_base kb
  WHERE
    kb.content_embedding IS NOT NULL
    AND 1 - (kb.content_embedding <=> query_embedding) >= similarity_threshold
  ORDER BY kb.content_embedding <=> query_embedding
  LIMIT match_count;
END;
$$;

-- =============================================================================
-- 4. Update add_knowledge_base_entry() RPC to accept title
--    DROP old signature first to avoid overload ambiguity
-- =============================================================================
DROP FUNCTION IF EXISTS add_knowledge_base_entry(text, varchar, varchar, varchar, varchar, jsonb);

CREATE OR REPLACE FUNCTION add_knowledge_base_entry(
  p_title varchar(200),
  p_content text,
  p_category varchar(50) DEFAULT NULL,
  p_subcategory varchar(50) DEFAULT NULL,
  p_language varchar(2) DEFAULT 'ja',
  p_source varchar(255) DEFAULT NULL,
  p_metadata jsonb DEFAULT '{}'::jsonb
)
RETURNS uuid
LANGUAGE plpgsql
AS $$
DECLARE
  new_id uuid;
BEGIN
  INSERT INTO knowledge_base (
    title,
    content,
    category,
    subcategory,
    language,
    source,
    metadata
  ) VALUES (
    p_title,
    p_content,
    p_category,
    p_subcategory,
    p_language,
    p_source,
    p_metadata
  ) RETURNING id INTO new_id;

  RETURN new_id;
END;
$$;

-- Grant execute permissions
GRANT EXECUTE ON FUNCTION search_knowledge_base TO service_role;
GRANT EXECUTE ON FUNCTION add_knowledge_base_entry(varchar, text, varchar, varchar, varchar, varchar, jsonb) TO service_role;
