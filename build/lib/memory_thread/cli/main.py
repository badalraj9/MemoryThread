import typer
from memory_thread.cli import identity, assimilate, prune, decay, maintenance
from memory_thread.cli import debug, timewarp_stub, replay_stub, maintenance_stub
from memory_thread.utils.logger import get_logger

log = get_logger(__name__)

app = typer.Typer(
    name="nebula",
    help="Memory Thread Management CLI"
)

app.add_typer(identity.app, name="identity", help="Identity management and deduplication")
app.add_typer(assimilate.app, name="assimilate", help="Event consolidation engine")
app.add_typer(prune.app, name="prune", help="State pruning engine")
app.add_typer(decay.app, name="decay", help="Truth vector decay engine")
# maintenance.app has 'run-all' and 'schedule'. The ordeal calls 'maintenance worker' and 'simulate'.
# I will merge them or override. The existing maintenance.app is minimal.
# Let's attach maintenance_stub as extra commands to maintenance.app or just replace/extend.
# Typer merging is tricky. Let's add stub commands to maintenance.app in-place?
# Or just use the stub one if it covers what we need for ordeal.
# The ordeal uses `maintenance worker` and `simulate` (Stage 5 used `simulate`).
# My previous `maintenance.py` did NOT have `simulate`.
# I will use maintenance_stub for `worker` and `simulate`.
# I will attach it to `maintenance` group alongside existing ones? No, replacing is safer for the test.
# But Stage 5 of previous ordeal used `maintenance simulate`? No, Stage 5 used `MaintenanceOrchestrator` via python script.
# The previous `maintenance.py` only had `run-all` and `schedule`.
# So I will REPLACE maintenance.app with one that includes all needed commands,
# OR just add the stub commands to the existing `maintenance.py`?
# I'll modify `maintenance.py` to include the stub commands. (Actually I created `maintenance_stub.py`).
# I will add `maintenance_stub.app` commands to `maintenance.app`.
for cmd in maintenance_stub.app.registered_commands:
    maintenance.app.command(name=cmd.name)(cmd.callback)

app.add_typer(maintenance.app, name="maintenance", help="Orchestration of maintenance jobs")

# Debug commands at top level as requested by script usage `memory-thread load-fixtures`
# But script calls `memory-thread load-fixtures`. Typer supports this if added to `app`.
app.add_typer(debug.app, name="debug", help="Debug tools")
# Also alias them to top level
app.command("load-fixtures")(debug.load_fixtures)
app.command("ingest-provenance")(debug.ingest_provenance)

app.add_typer(timewarp_stub.app, name="timewarp", help="Phase 6 Timewarp Stub")
app.add_typer(replay_stub.app, name="replay", help="Phase 6 Replay Stub")

if __name__ == "__main__":
    app()
