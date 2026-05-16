-- Phase 4: Cognitive State Upgrades

-- 4. Snapshots Table (Optimization & Replay)
CREATE TABLE IF NOT EXISTS snapshots (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    entity_id UUID NOT NULL REFERENCES entity_state(entity_id),
    last_event_id UUID NOT NULL REFERENCES events(id),
    state_data JSONB NOT NULL,
    truth_vector JSONB NOT NULL,
    timestamp TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    state_hash TEXT NOT NULL -- Merkle hash for integrity
);

CREATE INDEX IF NOT EXISTS idx_snapshots_entity_event ON snapshots(entity_id, last_event_id);

-- 5. Transactions Table (Multi-Entity Consistency)
CREATE TABLE IF NOT EXISTS transactions (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    root_event_id UUID NOT NULL REFERENCES events(id),
    status TEXT NOT NULL CHECK (status IN ('PENDING', 'COMMITTED', 'FAILED')),
    involved_entities UUID[] NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
