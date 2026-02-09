-- ============================================================================
-- Memory Thread Database Migrations
-- ============================================================================
-- Migration: 001_add_gin_indices.sql
-- Purpose: Add GIN indices for JSONB fields to improve query performance
-- Run with: psql -d memory_thread_db -f migrations/001_add_gin_indices.sql
-- ============================================================================

-- ============================================================================
-- TRUTH VECTOR INDICES
-- ============================================================================

-- Index for querying by confidence level
-- Example: WHERE truth_vector->>'confidence' > '0.8'
CREATE INDEX IF NOT EXISTS idx_entity_state_confidence 
    ON entity_state USING GIN ((truth_vector->'confidence'));

-- Index for querying by authority level
CREATE INDEX IF NOT EXISTS idx_entity_state_authority 
    ON entity_state USING GIN ((truth_vector->'authority'));

-- Full truth_vector JSON index for complex queries
CREATE INDEX IF NOT EXISTS idx_entity_state_truth_vector 
    ON entity_state USING GIN (truth_vector);

-- ============================================================================
-- BELIEF STORE INDICES
-- ============================================================================

-- Index for belief confidence queries
CREATE INDEX IF NOT EXISTS idx_beliefs_confidence 
    ON beliefs USING BTREE (confidence);

-- Index for belief authority queries  
CREATE INDEX IF NOT EXISTS idx_beliefs_authority 
    ON beliefs USING BTREE (authority);

-- Full-text search on belief content
CREATE INDEX IF NOT EXISTS idx_beliefs_content_fts 
    ON beliefs USING GIN (to_tsvector('english', content));

-- Agent-specific queries
CREATE INDEX IF NOT EXISTS idx_beliefs_agent 
    ON beliefs USING BTREE (agent_id);

-- ============================================================================
-- FACT STORE INDICES
-- ============================================================================

-- Source URI lookups
CREATE INDEX IF NOT EXISTS idx_facts_source_uri 
    ON facts USING BTREE (source_uri);

-- Content type filtering
CREATE INDEX IF NOT EXISTS idx_facts_content_type 
    ON facts USING BTREE (content_type);

-- Metadata JSONB index
CREATE INDEX IF NOT EXISTS idx_facts_metadata 
    ON facts USING GIN (metadata);

-- ============================================================================
-- EVENT LOG INDICES
-- ============================================================================

-- Timestamp-based queries (for replay/timewarp)
CREATE INDEX IF NOT EXISTS idx_events_timestamp 
    ON events USING BTREE (timestamp);

-- Object-based queries (for entity history)
CREATE INDEX IF NOT EXISTS idx_events_object_id 
    ON events USING BTREE (object_id);

-- Namespace filtering
CREATE INDEX IF NOT EXISTS idx_events_namespace 
    ON events USING BTREE (namespace);

-- ============================================================================
-- VERIFY INDICES
-- ============================================================================

-- Run this to verify all indices are created:
-- SELECT indexname, tablename FROM pg_indexes 
-- WHERE schemaname = 'public' 
-- AND indexname LIKE 'idx_%'
-- ORDER BY tablename, indexname;
