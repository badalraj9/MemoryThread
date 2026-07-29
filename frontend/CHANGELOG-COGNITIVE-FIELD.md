# Cognitive Field Engine — Implementation Log

## Philosophy

Memory Thread is not a graph explorer. It is a **Cognitive Field** — a living visualization of an artificial memory system. The paradigm:

| Old | New |
|---|---|
| Nodes | **Memories** (centers of influence, particles are visual anchors) |
| Edges | **Influence Paths** (directional potential, invisible until meaningful) |
| Events | **Activation Pulses** (temporary, born and disappear) |
| Graph | **Cognitive Field** (infinite space, emergent shape) |

### Core Principles
- **Fields, not nodes** — A memory has influence beyond its visible particle
- **Physics is language, not law** — Inspired by fluid dynamics / EM / diffusion, not a simulation
- **Silence is communication** — Most of the experience is quiet. The system earns attention.
- **Meaning determines rhythm** — Strong memories activate fast, weak hesitate, distant arrive later
- **Patient mind** — Not an animated graph. A mind that rests, thinks, notices, remembers, forgets.

---

## Files Created (10 files)

### `ShaderPipeline.ts`
Custom GLSL vertex/fragment shaders for particles. Features:
- Time-based breathing oscillation (`sin(uTime * 0.0015 + aPhase) * 0.006`)
- Core + glow + halo rendering layers
- Size computed from scale, pixel ratio, and camera distance
- Uniforms: uTime, uPixelRatio, uDecayRate, uAmbientIntensity, uBreathPhase

### `ParticleRenderer.ts`
Pre-allocated `BufferGeometry` with 2000 particle slots. No geometry rebuilds — only `needsUpdate`. Features:
- Dead slot tracking (reuse freed slots)
- Instruction queue from AnimationDirector
- Lerp-based smoothing (opacity, scale, glow) at 0.12 factor
- Custom ShaderMaterial

### `FlowField.ts`
180 ambient particles representing background cognitive noise. Designed to be almost imperceptible — users notice only after staring several seconds. Drift speed: 0.02–0.06 px/frame.

### `ForceSimulation.ts`
D3 force simulation — physics only, no DOM. Features:
- Link force with confidence-based distance/strength
- Charge repulsion: -200 (spreads nodes apart)
- Center force at (0, 0)
- Collide radius: 30 (prevents overlap)
- Alpha minimum: 0.001 (never fully freezes)
- Tick handlers for position sync

### `ActivationEngine.ts`
BFS propagation where meaning determines rhythm:
- Strong memories (high confidence) activate immediately (~40ms)
- Weak associations hesitate (up to 400ms)
- Long-distance connections arrive later
- Max depth: 4
- Intensity decays with distance: `strength * 0.6 * 0.65^depth`

### `AnimationDirector.ts`
Choreographer — translates cognitive events to particle instructions. ParticleRenderer never knows about memory. Animations:
- Activation pulse: scale 6–18, glow 0.3–1.0
- Hover: 60ms hesitation before response, scale 12
- Select: scale 16, gold color (#d6b85c), glow 0.8
- Emerge: scale 8, 800ms ease-out
- Forget: 2000ms dissolve
- Contradiction: red (#ff4033), scale 8–16
- Golden Thread: gold pulse along path

### `CameraController.ts`
Wildlife photographer camera:
- Patient — no idle wandering
- Smooth focus with ease-out (cubic) and tiny overshoot
- Base distance: z=600
- Inertia on release (0.92 damping)

### `SelectionManager.ts`
Raycaster picking with 60ms hesitation before hover response. Subconscious delay makes the system feel like it's "noticing" the user.

### `InspectorManager.ts`
EventBus bridge — opens/closes NodeInspector in response to cognitive events.

### `CognitiveFieldEngine.ts`
The boring conductor. Initializes all subsystems, connects them via EventBus, subscribes to Zustand store, runs the animation pulse. Does not decide what to render — ensures rendering happens.

---

## Files Refactored (1 file)

### `CognitiveCanvas.tsx`
Before: 386-line monolith (Three.js, D3, raycaster, camera, animation loop, store subscription all in one React component)
After: 28-line thin lifecycle wrapper — creates engine, calls resize/start, disposes on unmount. That's it.

---

## EventBus Additions

Added cognitive activity events for real-time agent visualization:
- `AgentActivityPulse` — { nodeId, intensity, type }
- `AgentRecallBurst` — { nodeIds[] }
- `AgentTraversalPath` — { nodeIds[], edgeIds[] }

---

## Fixes Applied

### 1. Particle Size (Shader)
- **Before**: `120.0 / -mvPosition.z` → sub-1-pixel particles
- **After**: `600.0 / -mvPosition.z` → ~10px particles

### 2. Initial Particle Scale
- **Before**: scale=0.5, opacity=0 (invisible, animate in)
- **After**: scale=8, opacity=0.65 (immediately visible)

### 3. Lerp Smoothing Rate
- **Before**: 0.08 factor (~700ms to settle)
- **After**: 0.12 factor (~400ms to settle)

### 4. Camera Distance
- **Before**: z=980 (far, small particles)
- **After**: z=600 (closer, better fill)

### 5. D3 Forces
- **Before**: charge=-100, collide=22 (clustering)
- **After**: charge=-200, collide=30 (spread out)

### 6. Resize Bug
- **Before**: `if (this.running) return` — resize blocked after start
- **After**: No guard, auto-check every 500ms in tick loop

### 7. Mock Mode
- **Before**: `VITE_MOCK === 'true'` — off by default, fetch hang on missing backend
- **After**: `VITE_MOCK !== 'false'` — on by default

### 8. Zero-Dimension Protection
- **Before**: No guard — renderer could be 0x0
- **After**: `Math.max(..., 1)` on all dimension reads

---

## Build Status

Build passes with zero errors.

---

## V2 Rewrite: Field Volume Rendering (Major)

### The Problem
The original renderer rendered **points** (dots on a dark background). The user perceived "space" (stars on black) — not a cognitive field. The philosophy said "the primary thing should be the field," but the field was invisible.

### The Fix — Dual-Layer Rendering

**Layer 1: Field Volume** (`aFieldScale` attribute + `fieldVertexShader`/`fieldFragmentShader`)
- Each memory renders as a large, soft Gaussian splat (scale 50–90)
- Very low per-particle opacity (0.04–0.10) + additive blending → overlapping regions create brighter volume
- Gaussian falloff: `exp(-dist² * 12)` → soft, cloud-like edges
- Cool cyan-white color, slow breathing (`sin(uTime * 0.0006)`)
- **This is the primary visual.** The user sees a glowing volume first.

**Layer 2: Anchor Particles** (`aScale` attribute + `anchorVertexShader`/`anchorFragmentShader`)
- Smaller, brighter dots (scale 6–10) inside the field volume
- Sharp core (`exp(-dist² * 40)`) + softer glow + halo
- Higher opacity (0.5–0.8)
- **Secondary visual.** The user discovers memories inside the field.

### Shared Geometry
Both layers use the same `BufferGeometry` but separate `THREE.Points` instances with different shader materials. The field layer renders first (behind), anchors render on top.

### Scale Hierarchy
- Idle: anchor=6–8, field=50–65
- Hover: anchor=12, field=90
- Select: anchor=16, field=120
- Activation pulse: anchor=6–18, field=50–135
- Forget: both → 0

### Rendering Order
```
Scene
├── Field Volume Points (renderOrder: 0)  ← volumetric glow, behind everything
├── Anchor Points (renderOrder: 1)        ← bright dots, on top of field
├── Edge Lines (interaction only)         ← hover/activation edges
└── Ambient Particles (very subtle)       ← background cognitive noise
```

## Remaining

- Golden Thread path animation (node-by-node gold pulse)
- SSE cognitive activity parsing (AgentActivityPulse from backend)
- Breathing idle rhythm (periodic subtle alpha nudge)
- 40-80ms hesitation on edge illumination (matches selection manager)
