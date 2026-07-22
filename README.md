<p align="center">
  <pre align="center">
 __  __                                 _____ _                        _ 
|  \/  | ___ _ __ ___   ___  _ __ _   |_   _| |__  _ __ ___  __ _  __| |
| |\/| |/ _ \ '_ ` _ \ / _ \| '__| | | || | | '_ \| '__/ _ \/ _` |/ _` |
| |  | |  __/ | | | | | (_) | |  | |_| || | | | | | | |  __/ (_| | (_| |
|_|  |_|\___|_| |_| |_|\___/|_|   \__, ||_| |_| |_|_|  \___|\__,_|\__,_|
                                   |___/                                   
  </pre>
</p>

<p align="center">
  <a href="#"><img src="https://img.shields.io/badge/Python-3.11%2B-3776AB?logo=python&logoColor=white" /></a>
  <a href="#"><img src="https://img.shields.io/badge/License-MIT-9370DB?logo=opensourceinitiative&logoColor=white" /></a>
  <a href="#"><img src="https://img.shields.io/badge/Tests-20%20files-brightgreen?logo=pytest&logoColor=white" /></a>
  <a href="#"><img src="https://img.shields.io/badge/API-FastAPI-009688?logo=fastapi&logoColor=white" /></a>
  <a href="#"><img src="https://img.shields.io/badge/Graph-iGraph-5428A0?logo=graphql&logoColor=white" /></a>
  <a href="#"><img src="https://img.shields.io/badge/Frontend-Scaffolded-grey?logo=react&logoColor=white" /></a>
</p>

<p align="center">
  <b>A truth-preserving, graph-native cognitive memory layer for AI agents</b><br>
  <i>Not a vector database. Memory is a causal graph — retrieve by spreading activation, not cosine similarity.</i>
</p>

<br>

---

<h2>📋 Why Memory Thread?</h2>

Most memory systems treat memories as **bags of vectors** — store an embedding, retrieve by cosine similarity, call it a day. This works for *search*. It fails at *reasoning*.

Memory Thread is built on a different premise: **memory is a causal graph** of events, entities, beliefs, and their relationships. Every write is an event with provenance. Every retrieval traverses a truth-weighted graph. Every memory carries confidence, authority, freshness, and corroboration metadata.

| Instead of… | Memory Thread does… |
|---|---|
| Flat vector search | Graph spreading activation along truth-weighted edges |
| Storing state snapshots | Event sourcing — state is *derived* from events |
| Single monolithic SDK | Modular `sdk/` package with clean separation |
| Base64 "encryption" for keys | Fernet AES-CBC encryption at rest |
| Open CORS to everywhere | Restricted origins + bearer token auth |

<br>

<h2>✨ Capabilities</h2>

<table>
<tr>
  <td width="33%"><b>🧠 Truth Vectors</b><br><small>4D scoring: confidence, authority, freshness, corroboration. Weights configurable, normalized to sum to 1.0.</small></td>
  <td width="33%"><b>🔗 Graph-Native Recall</b><br><small>iGraph spreading activation along truth-weighted edges. Not vector similarity — <i>reasoning</i>.</small></td>
  <td width="33%"><b>🧵 Golden Thread</b><br><small>Complete causal chain for any entity. Every event, antecedent, and truth evolution. Zero Postgres queries.</small></td>
</tr>
<tr>
  <td width="33%"><b>📦 Memory Tiers</b><br><small>Core (LLM context) → Episodic (iGraph) → Semantic (PostgreSQL). Hot/warm/cold management.</small></td>
  <td width="33%"><b>👁️ Proactive Context</b><br><small>ContextMonitor injects relevant memories <i>without being queried</i>. Entity extraction, dedup, token budgeting.</small></td>
  <td width="33%"><b>🔄 Workflow Induction</b><br><small>AWM-style procedural memory. Extracts reusable workflows from successful agent trajectories.</small></td>
</tr>
<tr>
  <td width="33%"><b>🔐 Merkle Attestation</b><br><small>Tamper-proof checkpoint chain. Audit-proof: "at timestamp T, agent A knew fact F with confidence C."</small></td>
  <td width="33%"><b>🌌 Multi-Agent Galaxy</b><br><small>Per-agent belief spaces. Cross-agent contradiction detection. Belief bridges (supports / contradicts).</small></td>
  <td width="33%"><b>📝 WAL Durability</b><br><small>Write-ahead log: sync mode (~277 EPS) or batched mode (~4,780 EPS).</small></td>
</tr>
<tr>
  <td width="33%"><b>🚧 Namespace Isolation</b><br><small>Per-namespace memory spaces. Cross-namespace reads blocked at the SDK level.</small></td>
  <td width="33%"><b>🔑 Encrypted Vault</b><br><small>Provider API keys encrypted at rest with Fernet (AES-CBC, 256-bit). Not base64.</small></td>
  <td width="33%"><b>📡 SSE Event Stream</b><br><small>Real-time graph mutation events pushed to connected clients via Server-Sent Events.</small></td>
</tr>
<tr>
  <td width="33%"><b>🛡️ API Auth</b><br><small>Optional <code>MT_API_KEY</code> bearer token on all HTTP endpoints. CORS restricted to <code>MT_ALLOWED_ORIGINS</code>.</small></td>
  <td width="33%"><b>🔍 Postgres FTS + Graph</b><br><small>Hybrid recall: FTS for seed resolution + graph activation for reasoning. Qdrant removed.</small></td>
  <td width="33%"><b>🧪 20 Integration Tests</b><br><small>Golden thread, decay curves, WAL recovery, contradiction accuracy, namespace isolation, graceful degradation.</small></td>
</tr>
</table>

<br>

<h2>⚡ Quick Start</h2>

<pre>
<b># Install</b>
pip install -e ".[full]"

<b># CLI</b>
mt --help

<b># API server</b>
mt-api

<b># OpenAI-compatible proxy (Ollama by default)</b>
mt-serve
</pre>

<h3>Python SDK</h3>

```python
from memory_thread.sdk import MemoryClient

client = MemoryClient(namespace="demo", use_db=True)

eid = client.remember(
    "User prefers dark mode",
    source="user",
    confidence=0.95,
    authority=0.9,
)

results = client.recall("dark mode", min_truth_score=0.0)
print(results.format())
client.close()
```

<h3>Proxy Server</h3>

<pre>
mt-serve                                          # Ollama (default)
mt-serve --backend https://api.openai.com/v1      # OpenAI
mt-serve --backend https://api.openrouter.ai/v1   # OpenRouter
</pre>

Point any OpenAI-compatible app to <code>http://localhost:8000/v1</code>. Memory injection, context retrieval, and secret redaction happen automatically.

<br>

<h2>🏗️ Architecture</h2>

<h3>Backend Data Flow</h3>

<pre>
                        ┌──────────────────┐
                        │   MemoryClient    │
                        │  (public SDK)     │
                        │  remember/recall  │
                        └───────┬──────────┘
                                │
                    ┌───────────┼──────────────┐
                    ▼           ▼              ▼
             ┌──────────┐ ┌──────────┐ ┌──────────────┐
             │   WAL    │ │  Events  │ │ GraphEngine  │
             │(crash    │ │(in-mem)  │ │(iGraph)      │
             │ safety)  │ │          │ │  725 lines   │
             └──────────┘ └──────────┘ └──────┬───────┘
                    │              │          │
                    ▼              ▼          ▼
             ┌──────────────────────────────────────┐
             │         Persistence Layer             │
             │  ┌──────────────────────────────────┐ │
             │  │ PostgreSQL                       │ │
             │  │ events (tsvector + GIN for FTS)  │ │
             │  │ entity_state                     │ │
             │  │ relations / threads / beliefs    │ │
             │  └──────────────────────────────────┘ │
             └──────────────────────────────────────┘
                                │
                    ┌───────────┼──────────────────┐
                    ▼           ▼                  ▼
             ┌──────────┐ ┌──────────┐ ┌──────────────────┐
             │ Golden   │ │ Recall   │ │ SSE Event Bus    │
             │ Thread   │ │(graph    │ │(real-time pushes  │
             │(causal   │ │ primary) │ │ to frontend)      │
             │ chain)   │ │          │ │                  │
             └──────────┘ └──────────┘ └──────────────────┘
</pre>

The backend is fully built: FastAPI server (870 lines, 20+ endpoints), iGraph engine (725 lines), 35 service modules (9,595 total lines), SSE event bus, and 20 integration tests.

<h3>Write Path</h3>

<pre>
<b>remember(content, source, confidence, authority)</b>
  │
  ├─ normalize authority (USER→1.0, AGENT→0.5)
  ├─ WAL.append(event)                    ← crash-safe before processing
  ├─ create Event(TruthVector, action, actor, antecedents, thread_id)
  ├─ persist to PostgreSQL (events + entity_state)
  ├─ WAL.commit(event)
  ├─ GraphEngine.apply_event(event)       ← add node + edges to iGraph
  └─ schedule async enrichment            ← NER, relation inference
     └─ return entity_id
</pre>

<h3>Read Path</h3>

<pre>
<b>recall(query, mode="hybrid")</b>
  │
  ├─ resolve query to seed nodes:
  │    1. UUID match         → direct graph lookup
  │    2. name/content match → graph search
  │    3. Postgres FTS       → entity_ids → graph seeds
  │
  ├─ GraphEngine.activation(seeds, depth=3, decay=0.5, threshold=0.3)
  │    ┌────────────────────────────────────────────────────────┐
  │    │ BFS spreading activation along truth-weighted edges    │
  │    │ seed starts at 1.0, each hop: edge.confidence × decay  │
  │    │ multiple paths to same node → max activation wins      │
  │    └────────────────────────────────────────────────────────┘
  │
  ├─ score nodes: sqrt(activation × truth_score)
  ├─ fill from keyword search if too few results
  └─ return top-K scored results
</pre>

<h3>Graph Model</h3>

<table>
<tr><th>Node</th><th>Label</th><th>Key Attributes</th></tr>
<tr><td>Entity</td><td><code>entity</code></td><td><code>entity_id, namespace, content, truth_vector, importance</code></td></tr>
<tr><td>Event</td><td><code>event</code></td><td><code>event_id, action, actor, timestamp, truth_vector, delta</code></td></tr>
<tr><td>Belief</td><td><code>belief</code></td><td><code>belief_id, agent_id, content, confidence, authority</code></td></tr>
<tr><td>Agent</td><td><code>agent</code></td><td><code>agent_id, authority</code></td></tr>
<tr><td>Thread</td><td><code>thread</code></td><td><code>thread_id, title, created_by, status</code></td></tr>
<tr><td>Workflow</td><td><code>workflow</code></td><td><code>workflow_id, title, success_count</code></td></tr>
</table>

<br>

<table>
<tr><th>Edge</th><th>Direction</th><th>Purpose</th></tr>
<tr><td><code>modifies</code></td><td>Event → Entity</td><td>Entity state timeline</td></tr>
<tr><td><code>causes</code></td><td>Event → Event</td><td>Causal DAG</td></tr>
<tr><td><code>relates</code></td><td>Entity → Entity</td><td>Knowledge graph</td></tr>
<tr><td><code>about</code></td><td>Belief → Entity</td><td>Belief target</td></tr>
<tr><td><code>holds</code></td><td>Agent → Belief</td><td>Belief ownership</td></tr>
<tr><td><code>supports</code> / <code>contradicts</code></td><td>Belief → Belief</td><td>Cross-agent agreement</td></tr>
<tr><td><code>contains</code></td><td>Thread → Event/Entity</td><td>Thread membership</td></tr>
<tr><td><code>has_step</code></td><td>Workflow → Step</td><td>Procedural ordering</td></tr>
</table>

<br>

<h2>🧮 Truth Vector</h2>

<p>Every memory carries four dimensions, combined into a normalized score:</p>

<table>
<tr><th>Component</th><th>Range</th><th>Meaning</th></tr>
<tr><td><code>confidence</code></td><td>0.0 – 1.0</td><td>Certainty in the content itself</td></tr>
<tr><td><code>authority</code></td><td>0.0 – 1.0</td><td>Source trust level (USER=1.0, AGENT=0.5)</td></tr>
<tr><td><code>freshness</code></td><td>0.0 – 1.0</td><td>Temporal relevance (exponential decay)</td></tr>
<tr><td><code>corroboration</code></td><td>0+</td><td>Independent confirmations (logarithmic scale)</td></tr>
</table>

<pre>
score = (W₁·conf + W₂·auth + W₃·fresh + W₄·log(1+corr)) / (W₁+W₂+W₃+W₄)
</pre>

Default weights: <code>W=[1.0, 1.2, 0.8, 0.6]</code> — automatically normalized to sum to 1.0. Score capped at 1.0.

<h3>Freshness Decay</h3>

<pre>
freshness(t) = freshness₀ × e^(-λ × days_elapsed)
</pre>

<table>
<tr><th>Memory Type</th><th>λ (decay rate)</th><th>Half-life</th></tr>
<tr><td><code>fact</code></td><td>0.001</td><td>~693 days</td></tr>
<tr><td><code>preference</code></td><td>0.01</td><td>~69 days</td></tr>
<tr><td><code>event</code></td><td>0.1</td><td>~7 days</td></tr>
<tr><td><code>prediction</code></td><td>0.5</td><td>~1.4 days</td></tr>
<tr><td><code>identity</code></td><td>0.0</td><td>Never decays</td></tr>
</table>

<br>

<h2>🖥️ Frontend: Memory Space (In Development)</h2>

<p>The frontend is currently <b>scaffolded</b> — the project structure, dependencies, build config, and Tailwind theme are in place, but the Cognitive Renderer has not been implemented yet.</p>

<table>
<tr><th>Status</th><th>What's done</th></tr>
<tr><td>✅ Complete</td><td>Project structure, <code>package.json</code> (React 19, D3, Framer Motion, Zustand, TanStack Router, Tailwind v4), Vite config with API proxy, dark academic theme (<code>index.css</code>)</td></tr>
<tr><td>🔧 Planned</td><td><b>Cognitive Renderer</b> — Three.js GPU particle field with custom shaders, D3 force simulation (physics only, no DOM), visual BFS activation engine, animation director, camera controller with inertia, delta SSE integration, event-driven architecture via typed EventBus</td></tr>
<tr><td>🔧 Planned</td><td><b>Memory Space UI</b> — Minimal interface with search overlay and temporary Node Inspector. No sidebar, no chat, no dashboard, no permanent controls.</td></tr>
<tr><td>🔧 Planned</td><td><b>Delta SSE</b> — Incremental graph mutations pushed from backend instead of full re-fetches</td></tr>
</table>

<p>The full design philosophy and architecture is documented in <a href="frontend.md">frontend.md</a>.</p>

<h3>Target Architecture (To Be Built)</h3>

<pre>
Memory Space
  └── CognitiveCanvas
        └── CognitiveFieldEngine
              ├── ParticleRenderer     (Three.js GPU particles)
              ├── FlowField            (ambient drift)
              ├── ShaderPipeline       (custom GLSL)
              ├── ForceSimulation      (D3 physics only)
              ├── ActivationEngine     (visual BFS propagation)
              ├── AnimationDirector    (events → choreography)
              ├── CameraController     (inertia, overshoot)
              ├── SelectionManager     (raycaster picking)
              └── InspectorManager     (detail panel)

EventBus — decouples all subsystems via typed events
</pre>

<h3>Design Principles</h3>

<ul>
  <li><b>Single Responsibility</b> — Every component owns exactly one concern</li>
  <li><b>Event-Driven</b> — No component directly controls another. Everything communicates through typed events.</li>
  <li><b>Cognitive Logic ≠ Rendering Logic</b> — ActivationEngine and AnimationDirector understand cognition. ParticleRenderer and ShaderPipeline understand only particles and pixels.</li>
  <li><b>Dual Activation</b> — Frontend runs visual BFS (zero latency, 60 FPS). Backend runs truth-aware reasoning (golden thread, contradiction).</li>
  <li><b>Semantic Animation</b> — Every motion has meaning. Nothing moves "just because."</li>
</ul>

<br>

<h2>⌨️ CLI</h2>

<pre>
<b>mt</b>                              # Full CLI with sub-commands
<b>mt ask</b> "what is the meaning of life?"
<b>mt search</b> "quantum computing"
<b>mt whoami</b>
<b>mt provider list</b>
<b>mt provider create groq --key</b> &lt;key&gt;
<b>mt client-admin list</b>
<b>mt galaxy list --depth 2</b>
<b>mt galaxy diff --ns1 alpha --ns2 beta</b>
</pre>

<table>
<tr><th>Command</th><th>Purpose</th></tr>
<tr><td><code>mt ask</code></td><td>Chat with LLM + memory context injection</td></tr>
<tr><td><code>mt search</code></td><td>Semantic memory search</td></tr>
<tr><td><code>mt whoami</code></td><td>Show identity and role context</td></tr>
<tr><td><code>mt status</code></td><td>System health check</td></tr>
<tr><td><code>mt provider *</code></td><td>CRUD for LLM providers (Groq, OpenAI, OpenRouter…)</td></tr>
<tr><td><code>mt client-admin *</code></td><td>API key management (create, list, revoke)</td></tr>
<tr><td><code>mt galaxy *</code></td><td>Schema inspection and diff across namespaces</td></tr>
</table>

<br>

<h2>🔒 Security</h2>

<table>
<tr><th>Layer</th><th>Detail</th></tr>
<tr><td><b>Vault Encryption</b></td><td>Provider API keys encrypted at rest with Fernet (AES-CBC, 256-bit key derived from <code>MT_SECRET_KEY</code>). Not base64.</td></tr>
<tr><td><b>API Authentication</b></td><td>Optional <code>MT_API_KEY</code> bearer token verified via constant-time comparison on all routes.</td></tr>
<tr><td><b>CORS</b></td><td>Restricted to <code>MT_ALLOWED_ORIGINS</code> env var. Methods limited to GET, POST, DELETE, OPTIONS.</td></tr>
<tr><td><b>SQL Injection</b></td><td>All queries use parameterized <code>psycopg2.sql</code> identifiers — zero string interpolation.</td></tr>
<tr><td><b>WAL Integrity</b></td><td>Atomic compaction via <code>tempfile.mkstemp</code> + <code>os.replace</code>. No TOCTOU race.</td></tr>
<tr><td><b>Proxy Guardrails</b></td><td>Auto-redaction of API keys, private keys, SSNs, email, GitHub tokens, AWS keys.</td></tr>
<tr><td><b>Secure SDK</b></td><td><code>SecureMemoryClient</code> restricts passthrough to an explicit allowlist — no reflection bypass.</td></tr>
<tr><td><b>RBAC</b></td><td>Role-based access with clearance grades. Zero-auth <code>/su</code> escalation removed.</td></tr>
<tr><td><b>Client Provisioning</b></td><td><code>mt client-admin create/list/revoke</code> — API key management with hashed secrets. One-time key reveal on creation.</td></tr>
</table>

<br>

<h2>📦 Project Structure</h2>

<pre>
memory_thread/                          # Python backend (BUILT)
├── sdk/                    # Public SDK
│   ├── client.py           # MemoryClient — main API surface
│   ├── models.py           # RecallResult, Memory, etc.
│   └── enrichment.py       # Async enrichment pipeline
├── cli/                    # CLI commands (Typer)
├── api/                    # FastAPI server
│   ├── server.py           # 20+ endpoints + SSE event stream (870 lines)
│   └── routers/            # Maintenance routes
├── services/               # 35 service modules (9,595 total lines)
│   ├── graph_engine.py     # iGraph cognitive graph (725 lines)
│   ├── golden_thread.py    # Causal chain tracing
│   ├── tms_service.py      # Truth vector math (459 lines)
│   ├── event_bus.py        # SSE fan-out for real-time events
│   ├── wal.py              # Write-ahead log (525 lines)
│   ├── decay_engine.py     # Freshness decay curves
│   ├── context_monitor.py  # Proactive context injection
│   ├── contemplator.py     # Reflection/consolidation
│   ├── pruner.py           # Memory pruning
│   ├── workflow_induction.py
│   ├── fact_store.py / belief_store.py
│   ├── galaxy_query.py     # Multi-agent OLAP queries
│   ├── timewarp_engine.py  # Temporal graph queries
│   ├── file_ingest_service.py
│   └── ... (35 total)
├── nervous/                # Security & access control
│   ├── vault.py            # Fernet-encrypted credential store
│   ├── galaxy_core.py      # Multi-agent orchestration
│   ├── client_registry.py  # API key registry
│   └── audit_ledger.py     # Audit trail
├── models/                 # Pydantic schemas
│   ├── events.py           # Event, TruthVector, EntityState
│   ├── entity.py           # Entity, MergeProposal
│   └── provenance.py       # Actor, Origin, ProvenanceEnvelope
├── db/                     # Database clients + migrations
│   ├── postgres_client.py
│   └── sqlite_client.py
├── config/                 # Pydantic-settings
│   └── settings.py
└── utils/                  # Health check, logging

frontend/                               # TypeScript frontend (SCAFFOLDED)
├── src/
│   ├── api/                # (empty — to be built)
│   ├── event-bus/          # (empty — to be built)
│   ├── store/              # (empty — to be built)
│   ├── types/              # (empty — to be built)
│   ├── components/         # (empty directories — to be built)
│   │   ├── cognitive-renderer/
│   │   ├── graph/
│   │   └── layout/
│   ├── App.tsx             # Placeholder (7 lines)
│   ├── main.tsx            # Entry point
│   └── index.css           # Tailwind v4 dark academic theme
├── package.json            # React 19, D3, Framer Motion, Zustand, etc.
├── vite.config.ts          # Vite 8 + React + Tailwind + API proxy
├── tsconfig.json
├── DESIGN_SPEC.md          # Original design spec (448 lines, legacy)
└── index.html              # Entry HTML

docs/
├── API.md, ARCHITECTURE.md
├── GRAPH_CORE_ARCHITECTURE.md
├── THESIS.md, ROADMAP.md
├── DURABILITY_AND_PERFORMANCE.md
└── thesis/                 # Expanded thesis notes
</pre>

<br>

<h2>🧪 Tests</h2>

<pre>
pytest tests/ -q       # 20 test files
</pre>

<table>
<tr><th>Test</th><th>What it verifies</th></tr>
<tr><td><code>test_api_endpoints.py</code></td><td>All REST endpoints respond correctly</td></tr>
<tr><td><code>test_postgres_integration.py</code></td><td>PostgreSQL persistence layer</td></tr>
<tr><td><code>test_latency_profile.py</code></td><td>Write/read throughput benchmarks</td></tr>
<tr><td><code>test_golden_thread_reconstruction.py</code></td><td>Causal chain correctness via graph traversal</td></tr>
<tr><td><code>test_truth_retrieval_quality.py</code></td><td>Truth-weighted recall ranks high-truth memories higher</td></tr>
<tr><td><code>test_memory_client_durability_modes.py</code></td><td>Sync/batched durability boundaries, WAL flush, compaction</td></tr>
<tr><td><code>test_wal_recovery.py</code></td><td>Crash recovery at 5 sizes (10, 30, 50, 70, 90 entries)</td></tr>
<tr><td><code>test_qdrant_dimension_guard.py</code></td><td>Qdrant-free init + keyword recall fallback after removal</td></tr>
<tr><td><code>test_namespace_isolation.py</code></td><td>Cross-namespace reads blocked. Truth scores isolated.</td></tr>
<tr><td><code>test_contradiction_accuracy.py</code></td><td>Precision and recall of contradiction detection</td></tr>
<tr><td><code>test_contradiction_edge.py</code></td><td>Edge cases in contradiction detection</td></tr>
<tr><td><code>test_contradiction_classifier.py</code></td><td>Contradiction classifier</td></tr>
<tr><td><code>test_decay_curves.py</code></td><td>Freshness decay matches mathematical specification</td></tr>
<tr><td><code>test_graph_export.py</code></td><td>Graph JSON export correctness</td></tr>
<tr><td><code>test_graceful_degradation.py</code></td><td>Behavior under Postgres failures</td></tr>
<tr><td><code>test_scale_ceiling.py</code></td><td>Scale ceiling benchmarks</td></tr>
<tr><td><code>test_event_bus.py</code></td><td>SSE event bus pub/sub</td></tr>
</table>

<br>

<h2>📄 Documentation</h2>

<table>
<tr><th>File</th><th>Content</th></tr>
<tr><td><code>frontend.md</code></td><td>Frontend architecture, philosophy, event catalog, and implementation plan</td></tr>
<tr><td><code>docs/README.md</code></td><td>Documentation map</td></tr>
<tr><td><code>docs/GRAPH_CORE_ARCHITECTURE.md</code></td><td>Full graph-neural core architecture (2,252 lines)</td></tr>
<tr><td><code>docs/continuity.md</code></td><td>Session handover — what's built and what remains</td></tr>
<tr><td><code>docs/THESIS.md</code></td><td>Thesis-ready system description</td></tr>
<tr><td><code>docs/ARCHITECTURE.md</code></td><td>Architecture overview (pre-graph, historical)</td></tr>
<tr><td><code>docs/API.md</code></td><td>SDK usage and durability contract</td></tr>
<tr><td><code>docs/DURABILITY_AND_PERFORMANCE.md</code></td><td>WAL architecture and throughput benchmarks</td></tr>
<tr><td><code>docs/ROADMAP.md</code></td><td>Pre-graph roadmap (historical)</td></tr>
</table>

<br>

<h2>📜 License</h2>

<p>MIT — see <a href="LICENSE">LICENSE</a>.</p>

<hr>

<p align="center">
  <sub>Built with ❤️ for agents that need to <i>remember</i>, not just <i>search</i>.</sub>
</p>
