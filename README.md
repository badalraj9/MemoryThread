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
  <a href="#"><img src="https://img.shields.io/badge/Tests-20%2F20-brightgreen?logo=pytest&logoColor=white" /></a>
  <a href="#"><img src="https://img.shields.io/badge/Security-Audited-CC2936?logo=trustpilot&logoColor=white" /></a>
  <a href="#"><img src="https://img.shields.io/badge/Status-Active-00ADD8?logo=quantum&logoColor=white" /></a>
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
  <td width="33%"><b>🛡️ API Auth</b><br><small>Optional <code>MT_API_KEY</code> bearer token on all HTTP endpoints. CORS restricted to <code>MT_ALLOWED_ORIGINS</code>.</small></td>
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

client = MemoryClient(namespace="demo", use_db=False)

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

<h3>Data Flow</h3>

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
             │ safety)  │ │          │ │              │
             └──────────┘ └──────────┘ └──────┬───────┘
                    │              │          │
                    ▼              ▼          ▼
             ┌──────────────────────────────────────┐
             │         Persistence Layer             │
             │  ┌────────────┐  ┌─────────────────┐ │
             │  │ PostgreSQL │  │ Qdrant (optional)│ │
             │  │ events     │  │ vector store     │ │
             │  │ entity_    │  │ fallback recall  │ │
             │  │ state      │  └─────────────────┘ │
             │  │ relations  │                       │
             │  └────────────┘                       │
             └──────────────────────────────────────┘
                                │
                    ┌───────────┼──────────────┐
                    ▼           ▼              ▼
             ┌──────────┐ ┌──────────┐ ┌──────────────┐
             │ Golden   │ │ Recall   │ │ Decay/Prune  │
             │ Thread   │ │(graph    │ │(topology-    │
             │(causal   │ │ primary) │ │ aware)       │
             │ chain)   │ │          │ │              │
             └──────────┘ └──────────┘ └──────────────┘
</pre>

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
  └─ schedule async enrichment            ← Qdrant, embeddings, NER, inference
     └─ return entity_id
</pre>

<h3>Read Path</h3>

<pre>
<b>recall(query, mode="hybrid")</b>
  │
  ├─ resolve query to seed nodes:
  │    1. UUID match         → direct graph lookup
  │    2. name/content match → graph search
  │    3. vector fallback    → Qdrant → resolve to graph seeds
  │
  ├─ GraphEngine.activation(seeds, depth=3, decay=0.5, threshold=0.3)
  │    ┌────────────────────────────────────────────────────────┐
  │    │ BFS spreading activation along truth-weighted edges    │
  │    │ seed starts at 1.0, each hop: edge.confidence × decay  │
  │    │ multiple paths to same node → max activation wins      │
  │    └────────────────────────────────────────────────────────┘
  │
  ├─ score nodes: sqrt(activation × truth_score)
  ├─ fill from vector search if too few results
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
</table>

<br>

<h2>📦 Project Structure</h2>

<pre>
memory_thread/
├── <b>sdk/</b>                    # Public SDK
│   ├── client.py            # MemoryClient — main API surface
│   ├── models.py            # RecallResult, Memory, etc.
│   └── slab_ingest.py       # Background slab ingestion
├── <b>cli/</b>                    # CLI commands
│   ├── main.py              # Typer entry point
│   ├── provider.py          # LLM provider CRUD
│   ├── client_admin.py      # API key management
│   └── galaxy.py            # Schema inspection
├── <b>api/</b>                    # FastAPI server (with auth)
├── <b>services/</b>                # Core services
│   ├── graph_engine.py      # iGraph materialized view
│   ├── golden_thread.py     # Causal chain tracing
│   ├── memory_tiers.py      # Hot/warm/cold tiers
│   ├── context_monitor.py   # Proactive injection
│   ├── thread_service.py    # Session management
│   ├── workflow_induction.py
│   ├── attestation_service.py
│   ├── tms_service.py       # Truth vector math
│   └── wal.py               # Write-ahead log
├── <b>nervous/</b>                # Security & access control
│   ├── vault.py             # Fernet-encrypted credential store
│   ├── access_control.py    # RBAC engine
│   ├── client_registry.py   # API key registry
│   ├── audit_ledger.py      # Audit trail
│   └── galaxy_core.py       # Multi-agent orchestration
├── <b>models/</b>                 # Pydantic schemas (Event, EntityState, TruthVector)
├── <b>db/</b>                     # Database clients + schema archive
├── <b>config/</b>                # Settings (pydantic-settings)
└── <b>utils/</b>                 # Embeddings, secure_sdk, health
</pre>

<br>

<h2>🧪 Tests</h2>

<pre>
pytest tests/ -q       # 20 tests, 2 skipped (perf benchmarks)
</pre>

<table>
<tr><th>Test</th><th>What it verifies</th></tr>
<tr><td><code>test_golden_thread_reconstruction.py</code></td><td>Causal chain correctness via graph traversal</td></tr>
<tr><td><code>test_truth_retrieval_quality.py</code></td><td>Truth-weighted recall ranks high-truth memories higher</td></tr>
<tr><td><code>test_memory_client_durability_modes.py</code></td><td>Sync/batched durability boundaries, WAL flush, compaction</td></tr>
<tr><td><code>test_wal_recovery.py</code></td><td>Crash recovery at 5 sizes (10, 30, 50, 70, 90 entries)</td></tr>
<tr><td><code>test_qdrant_dimension_guard.py</code></td><td>Graceful handling of embedding dimension mismatch</td></tr>
<tr><td><code>test_namespace_isolation.py</code></td><td>Cross-namespace reads blocked. Truth scores isolated.</td></tr>
<tr><td><code>test_contradiction_accuracy.py</code></td><td>Precision and recall of contradiction detection</td></tr>
<tr><td><code>test_decay_curves.py</code></td><td>Freshness decay matches mathematical specification</td></tr>
<tr><td><code>test_graceful_degradation.py</code></td><td>Behavior under Postgres/Qdrant/embedding failures</td></tr>
</table>

<br>

<h2>📄 Documentation</h2>

<table>
<tr><th>File</th><th>Content</th></tr>
<tr><td><code>docs/README.md</code></td><td>Documentation map</td></tr>
<tr><td><code>docs/GRAPH_CORE_ARCHITECTURE.md</code></td><td>Full graph-neural core architecture (2,252 lines)</td></tr>
<tr><td><code>docs/continuity.md</code></td><td>Session handover — what's built and what remains</td></tr>
<tr><td><code>docs/THESIS.md</code></td><td>Thesis-ready system description</td></tr>
<tr><td><code>docs/DURABILITY_AND_PERFORMANCE.md</code></td><td>WAL architecture and throughput benchmarks</td></tr>
</table>

<br>

<h2>📜 License</h2>

<p>MIT — see <a href="LICENSE">LICENSE</a>.</p>

<hr>

<p align="center">
  <sub>Built with ❤️ for agents that need to <i>remember</i>, not just <i>search</i>.</sub>
</p>
