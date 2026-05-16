-- Speed up session-scoped short-term memory lookups in agent_memory.value.
CREATE INDEX IF NOT EXISTS idx_agent_memory_session
ON agent_memory (agent_name, (value->>'sessionId'), created_at DESC)
WHERE key LIKE 'message_%';
