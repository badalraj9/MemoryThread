-- Phase 5: Cognitive Maintenance Layer Schema

-- Enable UUID extension if not exists
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- 1. Entities Table (Canonical Identity)
CREATE TABLE IF NOT EXISTS entities (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    namespace TEXT NOT NULL DEFAULT 'user',
    entity_type TEXT NOT NULL, -- 'person', 'place', 'concept', etc.
    name TEXT NOT NULL, -- Canonical name
    attributes JSONB DEFAULT '{}', -- Static/Slowly changing attributes
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    merged_into UUID REFERENCES entities(id) -- Null if active, points to new entity if merged
);

CREATE INDEX IF NOT EXISTS idx_entities_type ON entities(entity_type);
CREATE INDEX IF NOT EXISTS idx_entities_name ON entities(name);
CREATE INDEX IF NOT EXISTS idx_entities_merged_into ON entities(merged_into);

-- 2. Merge Log (Audit Trail)
CREATE TABLE IF NOT EXISTS entity_merges (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    source_entity_id UUID NOT NULL REFERENCES entities(id),
    target_entity_id UUID NOT NULL REFERENCES entities(id),
    confidence FLOAT NOT NULL,
    reason TEXT,
    timestamp TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_entity_merges_source ON entity_merges(source_entity_id);
CREATE INDEX IF NOT EXISTS idx_entity_merges_target ON entity_merges(target_entity_id);

-- Note: entity_state table from Phase 3.4 will link to these entities via entity_id.
-- Since entity_state.entity_id is a primary key, we can add a foreign key constraint if needed,
-- but for now we treat it as a logical link to allow flexibility during migration.
