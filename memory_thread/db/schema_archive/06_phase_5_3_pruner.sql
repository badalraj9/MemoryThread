-- Phase 5.3: Pruner Schema Updates

-- Add status and last_accessed to entity_state for pruning logic
ALTER TABLE entity_state
ADD COLUMN IF NOT EXISTS status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'inactive', 'archived')),
ADD COLUMN IF NOT EXISTS last_accessed TIMESTAMPTZ DEFAULT NOW(),
ADD COLUMN IF NOT EXISTS access_count INTEGER DEFAULT 0;

CREATE INDEX IF NOT EXISTS idx_entity_state_status ON entity_state(status);
CREATE INDEX IF NOT EXISTS idx_entity_state_last_accessed ON entity_state(last_accessed);
