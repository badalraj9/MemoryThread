-- Phase 5.2: Assimilation Engine Schema Updates

-- Add consolidated_into column to events table to mark events that have been summarized
ALTER TABLE events
ADD COLUMN IF NOT EXISTS consolidated_into UUID REFERENCES events(id);

CREATE INDEX IF NOT EXISTS idx_events_consolidated_into ON events(consolidated_into);

-- We might also want to store provenance in the new event.
-- The roadmap says "Provenance: list of source event IDs".
-- The 'antecedents' column in 'events' table (UUID[]) already exists and fits this purpose perfectly.
-- So no new column needed for provenance.
