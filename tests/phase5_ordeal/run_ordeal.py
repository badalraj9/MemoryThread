import os
import subprocess
import time
import json
import logging

logging.basicConfig(level=logging.INFO, filename="logs/full_ordeal.log", filemode="w")
console = logging.StreamHandler()
console.setLevel(logging.INFO)
logging.getLogger("").addHandler(console)

log = logging.getLogger("ORDEAL_RUNNER")

STAGES = [
    ("Stage 0: Data Gen", "tests/phase5_ordeal/stage0_data.py"),
    ("Stage 1: Identity", "tests/phase5_ordeal/stage1_identity.py"),
    ("Stage 2: Assimilation", "tests/phase5_ordeal/stage2_assimilation.py"),
    ("Stage 3: Pruner", "tests/phase5_ordeal/stage3_pruner.py"),
    ("Stage 4: Decay", "tests/phase5_ordeal/stage4_decay.py"),
    ("Stage 5: Orchestrator", "tests/phase5_ordeal/stage5_orchestrator.py"),
    ("Stage 6: Replay", "tests/phase5_ordeal/stage6_replay.py"),
    ("Stage 7: Exploit", "tests/phase5_ordeal/stage7_exploit.py"),
]

def run_ordeal():
    log.info("STARTING PHASE 5 ORDEAL...")
    start_total = time.time()
    results = {}

    for name, script in STAGES:
        log.info(f"--- Running {name} ---")
        start = time.time()
        try:
            # Run with PYTHONPATH=. to ensure imports work
            env = os.environ.copy()
            env["PYTHONPATH"] = "."
            subprocess.run(["python", script], check=True, env=env)
            status = "PASS"
        except subprocess.CalledProcessError:
            log.error(f"FAILED: {name}")
            status = "FAIL"
        except Exception as e:
            log.error(f"ERROR in {name}: {e}")
            status = "ERROR"

        duration = time.time() - start
        results[name] = {"status": status, "duration": duration}
        log.info(f"Finished {name} in {duration:.2f}s [{status}]")

    total_duration = time.time() - start_total

    # Generate Summary Report
    with open("reports/PHASE_5_ORDEAL_SUMMARY.md", "w") as f:
        f.write("# PHASE 5 ORDEAL SUMMARY\n\n")
        f.write(f"**Total Duration:** {total_duration:.2f}s\n\n")
        f.write("| Stage | Status | Duration |\n")
        f.write("|-------|--------|----------|\n")
        for name, data in results.items():
            f.write(f"| {name} | {data['status']} | {data['duration']:.2f}s |\n")

    log.info("PHASE 5 ORDEAL COMPLETED — REVIEW FAILURES.")
    print("\nPHASE 5 ORDEAL COMPLETED — REVIEW FAILURES.")

if __name__ == "__main__":
    run_ordeal()
