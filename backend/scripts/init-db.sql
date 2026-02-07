-- Engineer Cafe Navigator - Database Initialization
-- PostgreSQL initialization script for local development
-- Used by Docker Compose for LangGraph Checkpointer testing

-- Create extension for UUID support
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- LangGraph Checkpointer Tables
-- These tables are created by langgraph-checkpoint-postgres
-- This script ensures the database is ready for the checkpointer

-- Note: The actual checkpoint tables are created by PostgresSaver.setup()
-- This script provides the base schema and any custom tables

-- Custom tables for Engineer Cafe Navigator

-- Session metadata (optional, for debugging)
CREATE TABLE IF NOT EXISTS session_metadata (
    session_id TEXT PRIMARY KEY,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    metadata JSONB DEFAULT '{}'::jsonb
);

-- Create index for faster session lookups
CREATE INDEX IF NOT EXISTS idx_session_metadata_created_at
    ON session_metadata(created_at);

-- Grant permissions
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO postgres;
GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO postgres;

-- Log successful initialization
DO $$
BEGIN
    RAISE NOTICE 'Engineer Cafe Navigator database initialized successfully';
END $$;
