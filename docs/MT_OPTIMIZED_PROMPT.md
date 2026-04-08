# MT Optimized Restart Prompt

We are starting the `mt-optimized` branch for MemoryThread.

## Goal

Clean and optimize MT without damaging the irreducible core identity of MT.

## Core MT Features That Must Be Preserved

- application-level WAL durability
- event -> state derivation
- replay / recovery semantics
- truth-vector semantics: confidence, authority, freshness, corroboration
- provenance / causal memory behavior
- temporal memory behavior
- namespace isolation
- optional retrieval/enrichment layered on top, not defining the core

## What We Already Learned

- slab ingest was originally bottlenecked because it called `_remember_direct()` with per-item WAL work
- slab drain was changed to batch with WAL
- entity extraction was moved off the synchronous path into a background thread
- diagnostics showed `_remember_direct()` is still the dominant cost
- inside `_remember_direct()`, entity extraction was the biggest cost before async deferral
- remaining cost is mostly the real MT core path plus SDK/service architecture overhead
- current Python architecture is likely near the ceiling of this design, but not the ceiling of Python itself

## Optimization Principles

- do not remove core MT semantics
- do not optimize blindly; keep boundaries explicit
- preserve SDK/API/CLI behavior as much as possible
- move non-core intelligence out of the synchronous write path
- benchmark after each meaningful change
- no C++ rewrite yet; first prove the optimized architecture in Python

## Target Branch

- create and work on `mt-optimized`

## Planned First Steps

1. create branch `mt-optimized`
2. define and document two paths:
   - critical write path
   - async enrichment path
3. reduce synchronous write path to:
   - validate input
   - WAL prewrite
   - create event
   - derive state
   - persist required core state
   - WAL commit
   - return
4. identify everything still on the synchronous path that is not core MT
5. move non-core work behind explicit background processing boundaries
6. add built-in instrumentation so monkeypatch diagnostics are no longer needed
7. rerun benchmarks after each stage

## Expected Outcome For `mt-optimized`

- cleaner architecture
- same MT identity
- less bloated `MemoryClient`
- explicit sync vs async stage boundaries
- improved EPS without semantic loss

## Resume Instructions

When resuming:

1. inspect current branch/worktree
2. create `mt-optimized`
3. produce a keep/modify/remove plan file before broad changes
4. begin the first cleanup pass

## Short Design Intent

MT should keep durable event-state memory semantics and stop forcing every intelligent feature onto the write path.
