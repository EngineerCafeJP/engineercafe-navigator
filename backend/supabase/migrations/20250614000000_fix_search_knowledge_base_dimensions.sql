-- Fix search_knowledge_base function to accept configurable embedding dimensions
-- The previous function hardcoded vector(1536) but the column was migrated to vector(768)
-- This version removes the dimension constraint from the parameter type

-- Drop the old function first (parameter type change requires drop+recreate)
DROP FUNCTION IF EXISTS search_knowledge_base(vector, float, int);

-- Recreate with dimension-agnostic vector type
CREATE OR REPLACE FUNCTION search_knowledge_base(
  query_embedding vector,
  similarity_threshold float DEFAULT 0.5,
  match_count int DEFAULT 10
)
RETURNS TABLE (
  id uuid,
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

-- Grant execute permissions
GRANT EXECUTE ON FUNCTION search_knowledge_base TO service_role;
