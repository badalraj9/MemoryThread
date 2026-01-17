-- Main table for storing individual memory nodes
CREATE TABLE IF NOT EXISTS memories (
    id UUID PRIMARY KEY,
    content TEXT NOT NULL,
    memory_type TEXT,
    importance FLOAT,
    entities TEXT[],
    topics TEXT[],
    created_at TIMESTAMP,
    last_accessed TIMESTAMP,
    relations UUID[],
    metadata JSONB,
    domain TEXT,
    current_value TEXT,
    history JSONB
);

-- Table for storing relationships (edges) between memories
CREATE TABLE IF NOT EXISTS memory_edges (
    id UUID PRIMARY KEY,
    from_id UUID REFERENCES memories(id) ON DELETE CASCADE,
    to_id UUID REFERENCES memories(id) ON DELETE CASCADE,
    relation TEXT,
    weight FLOAT,
    last_activated TIMESTAMP
);

-- Enable trigram support for efficient keyword search
CREATE EXTENSION IF NOT EXISTS pg_trgm;

-- Index for fast keyword searching on memory content
CREATE INDEX IF NOT EXISTS memories_content_trgm_idx ON memories USING gin (content gin_trgm_ops);
