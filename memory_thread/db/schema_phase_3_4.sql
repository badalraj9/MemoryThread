-- Phase 3.4: The Brain (Truth Maintenance System) Schema

-- Enable UUID extension if not exists
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- 1. Events Table (Layer 1: Narrative Events)
CREATE TABLE IF NOT EXISTS events (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    namespace TEXT NOT NULL DEFAULT 'user',
    timestamp TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    actor TEXT NOT NULL CHECK (actor IN ('USER', 'AGENT', 'SYSTEM')),
    action TEXT NOT NULL CHECK (action IN ('PLANT', 'ADD', 'REMOVE', 'UPDATE', 'OBSERVE', 'INFER')),
    object_id UUID NOT NULL, -- Logical reference to an entity (even if not in entity_state yet)
    delta JSONB NOT NULL DEFAULT '{}', -- The change itself (e.g. {tree_count: 5})
    antecedents UUID[] DEFAULT '{}', -- Causal parents (Event IDs)
    truth_vector JSONB NOT NULL DEFAULT '{}' -- {confidence, authority, freshness, corroboration}
);

CREATE INDEX IF NOT EXISTS idx_events_object_id ON events(object_id);
CREATE INDEX IF NOT EXISTS idx_events_timestamp ON events(timestamp);
CREATE INDEX IF NOT EXISTS idx_events_namespace ON events(namespace);

-- 2. Entity State Table (Layer 2: Derived Reality Cache)
CREATE TABLE IF NOT EXISTS entity_state (
    entity_id UUID PRIMARY KEY,
    namespace TEXT NOT NULL,
    current_value JSONB NOT NULL, -- The derived state
    truth_vector JSONB NOT NULL, -- {confidence, authority, freshness, corroboration}
    version INTEGER NOT NULL DEFAULT 0, -- Optimistic locking
    last_event_id UUID NOT NULL REFERENCES events(id), -- Provenance watermark
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_entity_state_namespace ON entity_state(namespace);

-- 3. TMS Health Table (Layer 0: Meta-Stability)
CREATE TABLE IF NOT EXISTS tms_health (
    id INTEGER PRIMARY KEY DEFAULT 1 CHECK (id = 1), -- Singleton
    drift_score FLOAT NOT NULL DEFAULT 0.0,
    contradiction_count INTEGER NOT NULL DEFAULT 0,
    last_updated TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Insert initial health record if missing
INSERT INTO tms_health (id, drift_score, contradiction_count)
VALUES (1, 0.0, 0)
ON CONFLICT (id) DO NOTHING;
