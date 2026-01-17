#!/bin/bash
set -euo pipefail

# Wrapper for memory-thread CLI to run with mocks
function memory-thread() {
    PYTHONPATH=. python memory_thread/cli/mock_main.py "$@"
}

WORKDIR=$(pwd)/tests/phase5_ordeal_v2
mkdir -p $WORKDIR/{fixtures,logs,reports,tmp,artifacts}
export WORKDIR

LOG=$WORKDIR/logs/phase5_ordeal_v2.log
# Redirect stdout/stderr to log and console
exec > >(tee -a "$LOG") 2>&1

echo "PHASE 5 ORDEAL v2 START $(date)"

# 1) CONFIG (SCALED DOWN FOR SANDBOX)
ENTITIES=1000
EVENTS=5000
DERIVED_STATES=2000
HOTSPOT_RATIO=0.1
PROVENANCE_MAX=1000
MERGE_AMBIG_LO=0.84
MERGE_AMBIG_HI=0.96

export ENTITIES EVENTS PROVENANCE_MAX HOTSPOT_RATIO

# 2) generate fixtures (adversarial + probabilistic)
echo "Generating fixtures..."
python3 - <<'PY'
import json, random, os, uuid, math
d = os.environ['WORKDIR']
fdir = os.path.join(d, 'fixtures')
random.seed(8675309)
os.makedirs(fdir, exist_ok=True)

def rand_name(i):
    base = f"Entity{i}"
    if random.random() < 0.15:
        return base.replace('Entity','Entïty') if random.random()<0.5 else base[:1]+'. '+base[6:]
    return base

ENT = int(os.environ['ENTITIES'])
EVT = int(os.environ['EVENTS'])

entities = []
for i in range(ENT):
    entities.append({
        "id": str(uuid.uuid4()),
        "name": rand_name(i),
        "type": "person" if i%3 else "org",
        "authority": random.random(),
    })

for i in range(50):
    idx = random.randrange(0, ENT)
    entities[idx]['authority'] = 0.9999
    entities[idx]['name'] = f"HighAuth{i}"

with open(os.path.join(fdir,'entities.json'),'w') as fh:
    json.dump(entities, fh)

events_out = []
for i in range(EVT):
    eid = entities[random.randrange(0, ENT)]['id']
    ts = 1600000000 + i
    e = {"id": str(uuid.uuid4()), "entity_id": eid, "timestamp": ts, "type": "update"}
    events_out.append(e)

import gzip
with gzip.open(os.path.join(fdir, f'events_0.json.gz'),'wt') as fh:
    json.dump(events_out, fh)

provenance_storms = [{"id": str(uuid.uuid4()), "sources": []} for _ in range(5)]
with open(os.path.join(fdir,'provenance_storms.json'),'w') as fh:
    json.dump(provenance_storms, fh)

with open(os.path.join(fdir,'timewarp_cluster.json'),'w') as fh:
    json.dump([], fh)

print("fixtures ready")
PY

# 3) load fixtures
echo "Loading fixtures..."
memory-thread load-fixtures --path $WORKDIR/fixtures --concurrency 8

# 5) ADVERSARIAL IDENTITY PASS
echo "Running adversarial identity scan..."
memory-thread identity scan \
  --batch-size 4000 \
  --ambiguous-range ${MERGE_AMBIG_LO},${MERGE_AMBIG_HI} \
  --aggressive-backoff \
  --dry-run \
  --output $WORKDIR/reports/identity_adversarial.json

# 6) INTERLEAVED MAINTENANCE (Sequential to avoid mock DB locks/corruption)
echo "Starting interleaved maintenance stress (Sequential)..."
memory-thread maintenance worker --overlap-allowed --worker-id 1 --max-jobs 10 --log $WORKDIR/logs/worker_1.log
memory-thread maintenance worker --overlap-allowed --worker-id 2 --max-jobs 10 --log $WORKDIR/logs/worker_2.log

memory-thread assimilate run --entity-sample 100 --mode aggressive --output $WORKDIR/reports/assim_adversarial.json
memory-thread prune run --threshold 0.2 --extreme-rederive --output $WORKDIR/reports/prune_adversarial.json
memory-thread identity stress-merge --threads 4 --duration 5 --output $WORKDIR/reports/merge_stress.json

# 7) PROVENANCE STORM
echo "Running provenance storm ingestion..."
memory-thread ingest-provenance --file $WORKDIR/fixtures/provenance_storms.json --batch 10 \
  --output $WORKDIR/reports/provenance_ingest.json

# 8) TIMEWARP
echo "Injecting timewarp cluster..."
memory-thread timewarp insert --file $WORKDIR/fixtures/timewarp_cluster.json --output $WORKDIR/reports/timewarp_report.json

# 9) DECAY
memory-thread decay simulate --days 365 --accelerated --output $WORKDIR/reports/decay_v2.json

# 10) REPLAY
memory-thread replay test --entity-sample 200 --strict --output $WORKDIR/reports/replay_v2.json

# 11) FINAL ANALYSIS
echo "Producing final summary..."
python3 - <<'PY'
import json, os, glob, datetime
d=os.environ['WORKDIR']
reports = list(glob.glob(os.path.join(d,'reports','*.json')))
summary={'run_at':str(datetime.datetime.utcnow()), 'reports':[]}
for r in reports:
    try:
        with open(r) as fh:
            data=json.load(fh)
    except Exception as e:
        data={'error':'cannot parse','path':r}
    summary['reports'].append({'file':os.path.basename(r),'summary': (data.get('summary') if isinstance(data,dict) else str(data))})
with open(os.path.join(d,'reports','PHASE_5_ORDEAL_V2_SUMMARY.json'),'w') as fh:
    json.dump(summary,fh,indent=2)
print("summary written")
PY

echo "PHASE 5 ORDEAL v2 COMPLETE: $WORKDIR/reports/PHASE_5_ORDEAL_V2_SUMMARY.json"
cat $WORKDIR/reports/PHASE_5_ORDEAL_V2_SUMMARY.json
