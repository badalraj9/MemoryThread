-- Migration 11: Add CHECK constraints on truth_vector JSONB components.
--
-- Ensures every truth_vector stored in the DB has valid component ranges:
--   confidence    [0.0, 1.0]
--   authority     [0.0, 1.0]
--   freshness     [0.0, 1.0]
--   corroboration >= 0.0
--
-- This makes it structurally impossible for any future code path
-- (bug, migration, manual SQL) to write an out-of-range value.

ALTER TABLE entity_state
  DROP CONSTRAINT IF EXISTS truth_vector_components_check;

ALTER TABLE entity_state
  ADD CONSTRAINT truth_vector_components_check
  CHECK (
    truth_vector IS NULL OR (
      (truth_vector->>'confidence')::numeric IS NOT NULL
      AND (truth_vector->>'confidence')::numeric BETWEEN 0.0 AND 1.0
      AND (truth_vector->>'authority')::numeric IS NOT NULL
      AND (truth_vector->>'authority')::numeric BETWEEN 0.0 AND 1.0
      AND (truth_vector->>'freshness')::numeric IS NOT NULL
      AND (truth_vector->>'freshness')::numeric BETWEEN 0.0 AND 1.0
      AND (truth_vector->>'corroboration')::numeric IS NOT NULL
      AND (truth_vector->>'corroboration')::numeric >= 0.0
    )
  );

ALTER TABLE events
  DROP CONSTRAINT IF EXISTS events_truth_vector_components_check;

ALTER TABLE events
  ADD CONSTRAINT events_truth_vector_components_check
  CHECK (
    truth_vector IS NULL OR (
      (truth_vector->>'confidence')::numeric IS NOT NULL
      AND (truth_vector->>'confidence')::numeric BETWEEN 0.0 AND 1.0
      AND (truth_vector->>'authority')::numeric IS NOT NULL
      AND (truth_vector->>'authority')::numeric BETWEEN 0.0 AND 1.0
      AND (truth_vector->>'freshness')::numeric IS NOT NULL
      AND (truth_vector->>'freshness')::numeric BETWEEN 0.0 AND 1.0
      AND (truth_vector->>'corroboration')::numeric IS NOT NULL
      AND (truth_vector->>'corroboration')::numeric >= 0.0
    )
  );

INSERT INTO schema_version (version_id, applied_at)
VALUES (11, NOW());
