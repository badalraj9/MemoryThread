-- Phase 7: Knowledge Graph & Reasoning

-- 1. Relations Table (Edges)
-- Connects two entities with a typed, weighted relationship
CREATE TABLE IF NOT EXISTS relations (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    source_entity_id UUID NOT NULL REFERENCES entities(id),
    target_entity_id UUID NOT NULL REFERENCES entities(id),
    relation_type TEXT NOT NULL, -- e.g., "works_at", "friend_of", "located_in"
    confidence FLOAT NOT NULL DEFAULT 1.0,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    last_confirmed TIMESTAMPTZ DEFAULT NOW(),
    metadata JSONB DEFAULT '{}', -- Source of info, context
    is_inferred BOOLEAN DEFAULT FALSE, -- True if created by inference engine

    -- Constraint: Prevent duplicate edges of same type between same entities
    UNIQUE(source_entity_id, target_entity_id, relation_type)
);

-- Indices for fast traversal
CREATE INDEX IF NOT EXISTS idx_relations_source ON relations(source_entity_id);
CREATE INDEX IF NOT EXISTS idx_relations_target ON relations(target_entity_id);
CREATE INDEX IF NOT EXISTS idx_relations_type ON relations(relation_type);
