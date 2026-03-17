# Memory Thread - Project Context Summary

> **Last Updated**: 2026-03-15  
> **Total Development Time**: ~100 hours over 4 months  
> **Status**: Core system complete, agent system design ready

---

## Project Overview

Memory Thread is a **truth-preserving cognitive memory system for AI** - think of it as a "memory brain" for AI agents. Unlike traditional vector databases that treat all data equally, MT tracks:
- **Truth vectors**: confidence, authority, freshness, corroboration
- **Provenance**: where each piece of information came from
- **Multi-agent beliefs**: different agents can have different interpretations of the same fact
- **Decay**: memories fade over time like human brains

---

## Current Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                    Memory Thread                                 │
├─────────────────────────────────────────────────────────────────┤
│  SDK / API Layer                                                │
│  ├── MemoryClient (Python SDK)                                  │
│  ├── REST API (FastAPI)                                         │
│  └── CLI (Typer + Rich)                                         │
├─────────────────────────────────────────────────────────────────┤
│  Galaxy Schema (OLAP for Cognition)                            │
│  ├── Fact Store (Layer 0) - Immutable raw data                  │
│  ├── Belief Store (Layer 1) - Agent interpretations             │
│  └── Query Engine (Layer 2) - SLICE/DICE/DRILL/ROLL            │
├─────────────────────────────────────────────────────────────────┤
│  Core Services                                                  │
│  ├── TMS (Truth Maintenance System)                            │
│  ├── Code Intelligence (AST-based code analysis)               │
│  ├── Document Intelligence (PDF/MD parsing)                     │
│  ├── WAL (Write-Ahead Log for crash safety)                    │
│  └── Decay Engine (memory freshness)                            │
├─────────────────────────────────────────────────────────────────┤
│  Storage                                                        │
│  ├── PostgreSQL (primary)                                      │
│  ├── Qdrant (vector search)                                     │
│  ├── SQLite (fallback)                                         │
│  └── File fallback (~/.mt/)                                     │
└─────────────────────────────────────────────────────────────────┘
```

---

## What Was Implemented

### Core System (Done)
- [x] MemoryClient SDK with remember(), recall(), chat()
- [x] Truth vectors (confidence, authority, freshness, corroboration)
- [x] Galaxy Schema with SLICE/DICE/DRILL/ROLL queries
- [x] PostgreSQL, Qdrant, SQLite with fallback chain
- [x] Write-Ahead Log (WAL) for crash safety
- [x] REST API with OpenAPI docs
- [x] CLI with 20+ commands (mt init, mt serve, mt ask, etc.)
- [x] Cloud LLM integration (Groq, OpenRouter, Ollama)
- [x] Code ingestion (AST parsing for Python, regex for others)
- [x] Document ingestion (PDF, Markdown, text)
- [x] RBAC cleanup (removed, now simpler)
- [x] Docker Compose for one-command startup

### Design Documents (Done)
- [x] `docs/AGENT_SYSTEM_DESIGN.md` - Agent framework design
- [x] `docs/ENTERPRISE_PLATFORM.md` - Enterprise architecture
- [x] `docs/ENTERPRISE_ROADMAP.md` - 44-week roadmap

---

## Key Technical Decisions

1. **Default use_db=False** - Faster init (1s vs 15s), use DB for persistence later
2. **Mock embeddings by default** - Real embeddings need cached model, fallback works offline
3. **Lazy service loading** - Don't load all services at __init__
4. **Simple auth** - Removed complex RBAC, use namespace + API keys
5. **Groq first** - Fastest cloud LLM, free tier available

---

## Known Limitations

- Embedding model loading slow (needs optimization)
- Service init takes ~15s with DB, ~1s without
- Qdrant client has API mismatch (need to fix)
- Semantic search weak (using mock embeddings)
- No real multi-agent yet (design exists)

---

## What Was Discussed

### 1. Launch Readiness
We checked launch readiness from `docs/LAUNCH_READINESS.md`:
- Phase 1 (RBAC cleanup) - DONE
- `mt init` - Already exists
- `mt serve` - Added
- Docker Compose - Created

### 2. Cloud Model Testing
- Tested Groq API (works)
- Tested OpenRouter API (needs key)
- Fixed embedding dimension (384 for MiniLM)
- Qdrant collection recreated with correct dimension

### 3. Code Ingestion Flow
- AST parsing for Python
- Extracts: classes, functions, imports, call graph
- Converts to Galaxy Schema facts
- Query example: "What does chat() call?" → finds call graph

### 4. Document Ingestion
- Supports PDF, Markdown, text
- Extracts: sections, key terms, citations, figures
- Stored as Galaxy Schema facts

### 5. Derived Beliefs (Galaxy Schema Core)
```
Single Fact → Multiple Agent Interpretations
fact_id = mt.ingest_fact("User clicked login")
mt.derive_belief(fact_id, "Security event", agent_id="SecurityBot")
mt.derive_belief(fact_id, "Conversion", agent_id="AnalyticsBot")
```

### 6. Agent System Design
- Tool registry (read, grep, run, edit)
- Agent class with name, role, tools
- Execution loop: Plan → Execute → Verify → Remember
- Pre-built agents: CodeReviewer, BugHunter, DocWriter

### 7. Enterprise Platform Vision
- MT server on NAS/workstation
- Multiple connectors: CLI, Web, IDE, Slack
- Multi-tenant support
- On-premise (data never leaves company)
- One brain for entire enterprise

---

## Where We Left Off

1. **Launch readiness at ~60%** - Core works, some polish needed
2. **Agent system designed** - Ready to implement
3. **Enterprise roadmap created** - 44-week plan
4. **README updated** - Ready for open source

---

## Prompts to Restore Context

When continuing work on Memory Thread, use these prompts:

### General Context
```
You are working on Memory Thread - a truth-preserving cognitive memory system for AI.
We've spent ~100 hours building it over 4 months. 
The core system is done: SDK, API, CLI, code/doc ingestion, Galaxy Schema, truth vectors.
We designed an agent system and enterprise platform but haven't implemented them yet.
Key files: memory_thread/sdk.py, memory_thread/cli.py, docs/AGENT_SYSTEM_DESIGN.md
```

### For Launch Readiness
```
Continue improving launch readiness from docs/LAUNCH_READINESS.md.
We completed Phase 1 (RBAC cleanup), mt serve, Docker Compose.
Remaining: WAL recovery, graceful shutdown, optimizations.
```

### For Agent System
```
Implement the agent system from docs/AGENT_SYSTEM_DESIGN.md.
Start with: Tool Registry → Agent Class → Execution Loop → Built-in Agents.
```

### For Enterprise Platform
```
Expand Memory Thread into enterprise platform from docs/ENTERPRISE_ROADMAP.md.
Phase 1: Agent system first (local use)
Phase 2: Connectors (Web, IDE, Slack)
Phase 3: Enterprise features (multi-tenant, auth)
```

### For Code Optimization
```
Optimize Memory Thread performance:
- Embedding model loading (slow first run)
- Service init (15s → should be 1s)
- Use real embeddings, not mock
- Fix Qdrant client API
```

### Testing
```
Test MT functionality:
1. python -m memory_thread.cli ask "who am I" --provider groq
2. Test code ingestion: mt codebase .
3. Test document: mt document path/to/file.pdf
4. Check docker-compose.yml works
```

---

## Quick Reference

### Start MT Server
```bash
# Local
python -m memory_thread.cli serve

# Or with docker
docker compose up -d
```

### Test Cloud LLM
```bash
# Make sure .env has GROQ_API_KEY
python -m memory_thread.cli ask "hello" --provider groq
```

### Ingest Code
```bash
mt codebase /path/to/project --store
```

### Ingest Document
```bash
mt document path/to/file.pdf --store
```

### Check Status
```bash
mt status
```

---

## File Structure

```
MemoryThread/
├── memory_thread/
│   ├── api/server.py          # REST API
│   ├── cli.py                 # CLI commands
│   ├── sdk.py                 # MemoryClient
│   ├── services/
│   │   ├── code_intelligence.py    # Code parsing
│   │   ├── document_intelligence.py # PDF/MD parsing
│   │   ├── belief_store.py         # Galaxy Schema L1
│   │   ├── fact_store.py           # Galaxy Schema L0
│   │   ├── tms_service.py          # Truth Maintenance
│   │   ├── wal.py                  # Write-Ahead Log
│   │   └── decay_engine.py        # Memory decay
│   ├── db/                     # Database clients
│   └── utils/embeddings.py     # Embedding generation
├── docs/
│   ├── ARCHITECTURE.md
│   ├── AGENT_SYSTEM_DESIGN.md
│   ├── ENTERPRISE_PLATFORM.md
│   ├── ENTERPRISE_ROADMAP.md
│   └── LAUNCH_READINESS.md
├── docker-compose.yml
├── README.md
└── pyproject.toml
```

---

*This document should be read first when continuing work on Memory Thread to restore full context of what was built and what was planned.*