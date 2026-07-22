# Memory Thread — Frontend Architecture & Philosophy v1.0

## Mission Statement

Memory Thread is not a chatbot. Memory Thread is not a dashboard. Memory Thread is not a graph database explorer.

Memory Thread is a **Cognitive Memory Visualization Engine**. Its purpose is to allow users to observe, inspect, and understand how an artificial memory system organizes, connects, and evolves knowledge.

The graph is not a visualization placed inside the application. The graph **is** the application.

Every UI decision must reinforce this principle.

---

## Product Identity

The experience should never resemble:
- Neo4j / Gephi / Graph visualization tools
- Grafana / Kibana / Monitoring dashboards
- AI chat applications
- Enterprise admin panels

Instead, the desired impression:

> *"I am observing an artificial mind organizing, recalling, connecting, and evolving its memories in real time."*

---

## Routes

```
/          Landing page (full-viewport cinematic intro)
/explore   Memory Space (the core experience)
/settings  Configuration (minimal)
```

Everything else can be added later if the product genuinely needs it.

---

## Guiding Principles

### 1. Single Responsibility

Every component owns exactly one concern. A component should never know why something happened unless that is its responsibility.

### 2. Event-Driven Architecture

No component directly controls another whenever possible. Everything communicates through events:

```
Search
  ↓
EventBus
  ↓
ActivationEngine
  ↓
AnimationDirector
  ↓
ParticleRenderer
```

This keeps the system loosely coupled and easy to extend.

### 3. Cognitive Logic ≠ Rendering Logic

The frontend understands two different domains that must remain independent:

**Cognitive Domain** — Selection, Activation, Search, Inspector state
**Rendering Domain** — Particles, Shaders, Camera, GPU buffers

---

## Philosophy: The Graph is the Application

The graph must occupy almost the entire screen. Every permanent UI element competes with the graph for attention. Since the graph represents the product itself, no permanent UI should distract from it.

- Permanent UI is reduced to the absolute minimum.
- Additional controls appear only when requested.
- The user's eyes remain on the cognitive field.

---

## What We Removed and Why

### Sidebar — Removed
- Every pixel occupied by navigation is a pixel removed from the brain visualization.
- Sidebars create a "dashboard" mentality (admin panel, analytics software, enterprise app).
- Navigation is unnecessary — the system only contains a few major interactions.
- Navigation exists through: landing page, keyboard shortcuts, command palette (future).

### Top Bar — Removed (replaced by search overlay)
- Breadcrumbs are never needed (no deep navigation hierarchy).
- Namespaces are an advanced concept.
- Health indicators are developer information.
- Keep only: Memory Thread logo + Search bar, positioned minimally over the canvas.

### Status Bar — Removed
- Node count, edge count, SSE status, PostgreSQL health are implementation details.
- Users interact with memories, not SSE or databases.
- Diagnostics move to a developer/debug overlay, never visible during normal use.

### Dashboard — Removed
- Memory Thread is not an analytics platform.
- The user's goal is not to monitor infrastructure.
- The user's goal is to inspect cognition.
- Dashboard becomes a future optional module.

### Chat — Removed (critical decision)
- If users see a chat window, they naturally ignore the graph. The graph becomes decoration.
- Memory Thread exposes memory directly — users can search, inspect, follow reasoning, inspect truth, inspect relationships.
- Chat wraps those operations in natural language, adding a layer instead of exposing cognition.
- Search provides intentional control — the user specifies what they want, the graph visualizes the result.
- Chat can exist in another application that uses Memory Thread internally.

### Permanent Filter Panels / Controls — Removed
- Buttons, menus, toggles all permanently compete with the graph.
- Most users interact with them only occasionally.
- Access via: keyboard shortcuts, floating command palette, radial menu, contextual menu.

---

## What Stays and Why

### Search — Primary Interaction
Search is not conversation. Search is navigation. It acts as the entry point into the cognitive graph.

```
Search
  ↓
Matching memories activate
  ↓
Related memories illuminate
  ↓
Energy propagates
  ↓
Camera focuses
  ↓
Inspector opens
```

The graph itself becomes the response.

### Node Inspector — Temporary
The graph intentionally hides detailed information. Showing full memory text on every node creates visual chaos. The inspector reveals detail only after explicit user selection (progressive disclosure: overview first, detail on demand).

- Appears on node click or search result selection
- Disappears on close or background click
- Contains: Memory content, Truth Vector, Golden Thread timeline, Related Memories, Actions

---

## Core Interface

```
──────────────────────────────────

        Memory Thread

           Search

──────────────────────────────────



          Living Brain



──────────────────────────────────
```

Visible permanently: Memory Thread logo, Search bar.
Visible temporarily: Inspector, Tooltip, Context menu, Command palette.

---

## Architecture

```
Backend
────────────────────────────────

Graph Engine     — iGraph cognitive graph
Truth Engine     — Truth Management System (4D truth vectors)
Delta Engine     — SSE delta generation on mutation
Reasoning Engine — Golden thread, contradiction detection, activation

        │
        ▼

     SSE / API
  (delta events, not full re-fetches)

        │
        ▼

Frontend
────────────────────────────────

AppShell
  └── LandingPage             (full-viewport cinematic intro)
  └── MemorySpace
        ├── SearchOverlay         (minimal input over canvas)
        └── CognitiveCanvas       (React lifecycle: mount, resize, unmount)
              └── CognitiveFieldEngine  (runtime orchestration — "brain stem")
                    ├── ParticleRenderer    (Three.js GPU particles)
                    ├── FlowField           (ambient particle drift)
                    ├── ShaderPipeline      (custom GLSL shaders)
                    ├── ForceSimulation     (D3 — computes positions, never renders)
                    ├── ActivationEngine    (visual BFS propagation, zero API)
                    ├── AnimationDirector   (cognitive events → particle instructions)
                    ├── CameraController    (inertia, overshoot, smooth focus)
                    ├── SelectionManager    (raycaster picking only)
                    └── InspectorManager    (opens/closes NodeInspector)

  └── NodeInspector (slide-over detail panel)
```

---

## Delta Synchronization

```
Initial Load
  ↓
Full Graph (GET /graph)
  ↓
SSE Delta (node_added / node_removed / node_updated / edge_added / edge_removed)
  ↓
SSE Delta
  ↓
...
  ↓
Reconnect
  ↓
Full Sync (GET /graph — drift correction)
```

No full re-fetch after every mutation. SSE events carry structured deltas. Frontend applies them incrementally to the local graph model and D3 simulation.

**Delta payload shape:**
```json
{
  "type": "delta",
  "seq": 142,
  "changes": {
    "nodes_added": [{ "id": "...", "type": "entity", "truth_confidence": 0.85, ... }],
    "nodes_removed": ["id1", "id2"],
    "nodes_updated": [{ "id": "...", "truth_confidence": 0.7, ... }],
    "edges_added": [{ "source": "...", "target": "...", "type": "relates", ... }],
    "edges_removed": ["source:target"]
  }
}
```

New nodes without server positions are placed at the centroid of their neighbors (or origin). D3 simulation re-heats with `alpha(0.3)` and the particle drifts to equilibrium.

---

## Dual Activation Engines

There are two activation engines with different responsibilities:

### Frontend ActivationEngine (visual propagation)

```
Search Result
  ↓
BFS
  ↓
Distance decay
  ↓
Propagation delay
  ↓
Intensity
  ↓
Particle animation
  ↓
Camera hints
```

- Pure visualization. No knowledge of truth scores or semantics.
- Zero latency — the graph data is already in memory.
- Runs at 60 FPS. Owned by the renderer.

### Backend Reasoning Engine (truth-aware traversal)

```
Seed
  ↓
Truth Engine
  ↓
Authority
  ↓
Conflict Resolution
  ↓
Temporal Decay
  ↓
Confidence
  ↓
Golden Thread
  ↓
Return path
```

- Called only when the user requests explicit reasoning (e.g., Golden Thread).
- Returns a path with truth metadata.
- The renderer animates that path visually.

---

## Animation Director

Translates cognitive events into visual choreography. The ParticleRenderer never knows what a "merge" or "golden thread" is — it only receives rendering instructions.

### Input → Output

```
Activation      →  { particleId, opacity, scale, glow, velocity }
Merge           →  { particleId, targetPosition, duration, easing }
Forget          →  { particleId, fadeDuration, dissolveCurve }
Contradiction   →  { particleIds[], turbulence, frequency }
Golden Thread   →  { path[], pulseSpeed, glowIntensity }
```

```
Event                     Animation
──────────────────────────────────────────────────────
Remember                  Particle emerges from center, drifts to equilibrium
Search                    Activation wave propagates from seed nodes
Recall                    Pulse through graph along activated paths
Contradiction             Local turbulence, unstable oscillation
Merge                     Two particles spiral together
Forget                    Particle loses energy, slowly dissolves
Golden Thread             Gold pulse travels along causal path
Hover                     Immediate neighbors illuminate, rest dim
```

Every animation has meaning. If an animation cannot be explained by an internal cognitive process, it should not exist.

---

## Event Bus (Frontend)

An internal EventBus decouples all subsystems. No component calls another directly. Each listens to events it cares about.

```
Search
  ↓
EventBus
  ↓
ActivationEngine → AnimationDirector → ParticleRenderer
  ↓
CameraController
  ↓
InspectorManager
  ↓
FlowField
```

### Formal Event Catalog

Every event is a contract. Defined upfront to prevent scope creep.

**Search**
- `SearchStarted` — { query: string }
- `SearchCompleted` — { seedIds: string[], results: SearchResult[] }

**Selection**
- `NodeHovered` — { nodeId: string | null }
- `NodeSelected` — { nodeId: string }
- `NodeDeselected` — {}

**Activation**
- `ActivationStarted` — { seedIds: string[] }
- `ActivationWave` — { nodeId: string, intensity: number, delayMs: number }
- `ActivationFinished` — {}

**Golden Thread**
- `GoldenThreadRequested` — { nodeId: string }
- `GoldenThreadReceived` — { path: GoldenThreadNode[] }

**Graph Mutations (from SSE)**
- `NodeAdded` — { node: GraphNode }
- `NodeUpdated` — { node: GraphNode }
- `NodeRemoved` — { nodeId: string }
- `EdgeAdded` — { edge: GraphEdge }
- `EdgeRemoved` — { source: string, target: string }

**Cognitive Events**
- `MemoryAdded` — { entityId: string }
- `MemoryUpdated` — { entityId: string }
- `MemoryRemoved` — { entityId: string }
- `ContradictionDetected` — { entityIds: string[], severity: number }
- `MergeStarted` — { sourceId: string, targetId: string }
- `MergeFinished` — { survivingId: string }

**Camera**
- `CameraFocusRequested` — { nodeIds: string[], duration: number }
- `CameraFocusCompleted` — {}

**Inspector**
- `InspectorOpenRequested` — { nodeId: string }
- `InspectorClosed` — {}

**Errors**
- `SSEDisconnected` — { retryCount: number }
- `SSEReconnected` — {}
- `DeltaParseError` — { raw: string, error: string }
- `ActivationFailed` — { reason: string }
- `SearchFailed` — { query: string, error: string }
- `GraphLoadFailed` — { error: string }

Error events do not crash the UI. They trigger graceful degradation: silent retry, stale data indicator, or fade-to-idle.

---

## Camera Controller

The camera should feel alive, never mechanical:
- Inertia (momentum on pan/zoom release)
- Smooth focus (slerp/lerp to target, not instant snap)
- Tiny overshoot and gentle correction
- Double-click node: zoom to fit with focus animation
- Golden thread trace: animate camera along path points

---

## Color Palette

Almost monochrome. Communication主要通过 motion and brightness, not color.

```
Primary:
  White     — default particles
  Cyan      — secondary / ambient
  Blue      — tertiary

Reserved (semantic only):
  Gold      — Golden Thread
  Red       — Contradiction
```

No other colors unless they represent a unique cognitive event. Memory type colors (fact, event, preference, etc.) are not rendered as color — they are expressed through particle behavior.

---

## Connections (Edges)

Traditional graph software renders every edge. At scale this becomes visual noise.

Connections remain invisible by default. They appear only when they communicate meaning:
- **Hover** — immediate neighbors illuminate
- **Golden Thread** — causal path appears
- **Search** — activated paths illuminate
- **Reasoning** — information pulses along connections

Every visible edge must justify its existence.

---

## Ambient Field

Not every particle represents a memory. Some represent the cognitive field itself:
- Prevent static appearance
- Communicate system activity
- Give depth and atmosphere
- Reinforce "living brain" feeling

These particles carry no information. They visualize the environment.

---

## Layout

```
┌──────────────────────────────────────────────┐
│                                              │
│   Memory Thread                              │
│                                              │
│   [ Search... ]           ← minimal overlay  │
│                                              │
│                                              │
│          Living Brain                         │
│      (Three.js full-viewport)                │
│                                              │
│                                              │
│                                              │
│                                    [Inspector] ← temporary
│                                              │
└──────────────────────────────────────────────┘
```

Full viewport. No borders. No chrome. The cognitive field extends edge to edge.

---

## File Structure

```
frontend/
└── src/
    ├── api/
    │   ├── client.ts               — REST API wrapper
    │   └── sse.ts                  — SSE connection manager
    │
    ├── event-bus/
    │   └── EventBus.ts             — Internal EventBus with typed events
    │
    ├── store/
    │   └── graph-store.ts          — Zustand store (graph data, selection, filters)
    │
    ├── types/
    │   └── graph.ts                — All type definitions
    │
    ├── components/
    │   ├── AppShell.tsx            — Root wrapper (bootstrap only, no layout)
    │   ├── LandingPage.tsx         — Cinematic intro
    │   ├── MemorySpace.tsx         — /explore route, wires high-level events
    │   ├── SearchOverlay.tsx       — Minimal search input over canvas
    │   ├── NodeInspector.tsx       — Detail slide-over panel
    │   │
    │   └── cognitive-field/
    │       ├── CognitiveCanvas.tsx      — React lifecycle (mount, resize, unmount)
    │       ├── CognitiveFieldEngine.ts  — Runtime orchestration ("brain stem")
    │       ├── ParticleRenderer.ts      — Three.js Points with custom shaders
    │       ├── ShaderPipeline.ts        — GLSL vertex/fragment shaders
    │       ├── FlowField.ts             — Ambient particle drift
    │       ├── ForceSimulation.ts       — D3 force (physics only, no DOM)
    │       ├── ActivationEngine.ts      — Visual BFS propagation
    │       ├── AnimationDirector.ts     — Cognitive events → particle instructions
    │       ├── CameraController.ts      — Inertia, focus, overshoot
    │       ├── SelectionManager.ts      — Raycaster picking only
    │       └── InspectorManager.ts      — Open/close/populate NodeInspector
    │
    ├── App.tsx                     — Root component with TanStack Router
    ├── main.tsx                    — Entry point
    └── index.css                   — Tailwind + theme (dark academic)
```

---

## Component Responsibilities

### AppShell
Only application bootstrapping. Never owns layout. Never owns graph logic.

### MemorySpace
Owns the overall Memory Space experience. Creates CognitiveCanvas, SearchOverlay, and NodeInspector. Wires high-level events between them. Nothing more.

### CognitiveCanvas
Owns the Three.js renderer, animation loop, resize handling, and render lifecycle. Should not know anything about search, activation, or memory types. On mount: creates CognitiveFieldEngine. On unmount: disposes it.

### CognitiveFieldEngine ⭐
The heart of the frontend. Think of it as the brain stem — it keeps everything running but doesn't make cognitive decisions.

Responsibilities:
- Initialize renderer, particle system, force simulation, shaders, camera
- Connect each subsystem to the EventBus
- Update all systems each frame (tick D3, update particles, render)
- Coordinate startup and shutdown order

It does not decide what to render. It ensures rendering happens.

### ParticleRenderer
Knows only: particle position, velocity, scale, opacity, color, animation data. Receives buffer updates from AnimationDirector. Never knows about truth, merge, golden thread, memory, or search.

### ShaderPipeline
Pure GPU. Receives buffers and uniforms. Returns pixels. Nothing else.

### FlowField
Computes ambient particle movement only.

### ForceSimulation
Owns D3 force simulation. Computes positions. Never renders.

### ActivationEngine
Input: seed node IDs. Output: an activation timeline (frame X → nodes Y activate with intensity Z). Decides order, delay, and intensity. Nothing visual.

### AnimationDirector ⭐
Probably the smartest frontend class. Translates cognitive events into choreography.

```
Input:  Activation, Merge, Forget, Contradiction, Golden Thread
Output: Particle instructions — { particleId, opacity, scale, glow, velocity }
```

### CameraController
Owns only the camera. Input: focus node → moves camera. No raycasting. No selection.

### SelectionManager
Extremely small. Mouse → raycast → selected node → EventBus. No camera, no animation, no inspector, no activation.

### InspectorManager
Owns opening, closing, populating, and animating the NodeInspector. Never computes data — reads from store and API.

---

## Data Flow

### Search flow
```
User types in SearchOverlay
  → POST /api/memory/recall (debounced 300ms)
  → Backend returns seed node IDs
  → EventBus fires SearchCompleted with seed IDs
  → ActivationEngine receives event, runs BFS from seeds with distance decay
  → ActivationEngine fires ActivationWave events: { nodeId, intensity, delayMs }
  → AnimationDirector receives wave, choreographs particle glow sequence
  → ParticleRenderer executes: raises energy attribute on affected particles
  → CameraController receives CameraFocusRequested with centroid of region
  → InspectorManager receives InspectorOpenRequested for the top result
```

### Remember flow (real-time via SSE)
```
Backend: memory stored → GraphEngine mutates → DeltaEngine computes delta
  → SSE pushes delta event
  → EventBus fires NodeAdded with new node data
  → GraphStore applies delta to local graph model
  → ForceSimulation receives new node, re-heats alpha(0.3)
  → AnimationDirector receives NodeAdded, produces emerge choreography
  → ParticleRenderer receives instructions: new particle emerges from center
  → Particle drifts to D3 equilibrium position over time
```

### Node selection flow
```
User clicks particle
  → SelectionManager raycasts, finds hit
  → EventBus fires NodeSelected with node ID
  → CameraController receives CameraFocusRequested, focuses on position
  → InspectorManager receives InspectorOpenRequested
  → NodeInspector fetches GET /api/memory/{id}/golden-thread
  → NodeInspector renders truth vector, causal chain, related memories
```

---

## Performance Guidelines

- D3 simulation runs in requestAnimationFrame, not setInterval
- ParticleRenderer uses pre-allocated BufferGeometry with dead slot tracking (no geometry rebuild on every delta)
- Batch SSE deltas: if multiple deltas arrive within one frame, coalesce them before applying to D3
- All particle updates go through BufferAttribute.needsUpdate, never rebuild geometry
- Shader uniforms for global parameters (time, decay rate, ambient intensity) to avoid per-particle CPU updates
- Search debounce: 300ms
- SSE reconnect backoff: 1s, 2s, 4s, 8s, max 30s

---

## Dependencies (npm)

In package.json:
- react, react-dom (^19)
- @tanstack/react-router
- @tanstack/react-query
- zustand
- d3, @types/d3
- framer-motion
- lucide-react
- tailwindcss, @tailwindcss/vite
- vite, @vitejs/plugin-react

To install:
- three, @types/three
