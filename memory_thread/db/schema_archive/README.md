# Schema Archive

These files document the historical evolution of the database schema across development phases.

**DO NOT use these files to create or migrate a database.** The canonical schema lives in `memory_thread/db/migrations/runner.py`, which consolidates all phases into numbered, idempotent migrations with a `schema_version` tracking table.

| File | Phase | Content |
|------|-------|---------|
| `01_original_memories.sql` | Pre-phase | Original `memories` + `memory_edges` tables |
| `02_phase_3_4_events.sql` | 3.4 | Event sourcing core: `events`, `entity_state`, `tms_health` |
| `03_phase_4_snapshots.sql` | 4 | `snapshots`, `transactions` tables |
| `04_phase_5_entities.sql` | 5 | `entities`, `entity_merges` tables |
| `05_phase_5_2_assimilation.sql` | 5.2 | `consolidated_into` column on events |
| `06_phase_5_3_pruner.sql` | 5.3 | `status`, `last_accessed`, `access_count` on entity_state |
| `07_phase_7_relations.sql` | 7 | `relations` edge table |

Use `python -m memory_thread.db.migrations.runner` to apply migrations.
