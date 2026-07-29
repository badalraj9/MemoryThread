# Volumetric Neural Field Engine — Master Technical Specification & Plan

## 1. Vision & Visual Reference Benchmark

MemoryThread is transforming from a particle-based starfield into an **observable artificial mind**, directly inspired by the cinematic neural visual identity of **Ultron / JARVIS** (*Avengers: Age of Ultron*).

### Visual Identity Principles:
- **Continuous Fluid Volume**: Cognition is dense, continuous, and self-illuminating—not empty space filled with isolated dots.
- **Dual-Entity Color Spaces**:
  - **Electric Cyan (`#22d3ee` / `#3dd68c`)**: Active memory space, facts, identity, structure (JARVIS aesthetic).
  - **Warm Golden Amber (`#f59e0b` / `#d6b85c`)**: Authority, beliefs, predictions, multi-agent belief spaces (Mind Stone / Ultron aesthetic).
- **Filamentary Synaptic Tendrils**: Thousands of razor-thin glowing electric neural threads weaving *inside* the translucent volumetric density cloud.
- **Hyper-Dense Luminous Cores**: Blindingly bright inner nuclei with soft Gaussian halos.
- **Electric Plasma Turbulence**: Subtle high-frequency 3D Curl Noise jitter running along active neural pathways.

---

## 2. 4-Layer System Architecture

$$\begin{aligned}
\text{\textbf{Layer 1: Cognitive Engine}} & \quad \longrightarrow \quad \text{Graph, Embeddings, 4D Truth Vectors, Actions} \\
\Downarrow & \\
\text{\textbf{Layer 2: Continuous Influence Field}} & \quad \longrightarrow \quad \text{3D Scalar Density Map (\texttt{DataTexture3D}) + Voxel Grid} \\
\Downarrow & \\
\text{\textbf{Layer 3: Signal Uniform Layer}} & \quad \longrightarrow \quad \text{Dynamic perturbations, wave functions, dye pulses, GLSL uniforms} \\
\Downarrow & \\
\text{\textbf{Layer 4: Viewport Rasterizer}} & \quad \longrightarrow \quad \text{Raymarched Volume Shader + Synaptic Filament Tendrils}
\end{aligned}$$

---

## 3. Mathematical Specifications

### 3.1 Wyvill Quintic Density Kernel
For a point $\mathbf{p} = (x,y,z)$ in 3D space and memory center $\mathbf{c}_i$ with radius $R_i$:
$$r = \frac{\|\mathbf{p} - \mathbf{c}_i\|}{R_i}$$
$$f(r) = \begin{cases} \left(1 - r^2\right)^3 & \text{if } r < 1 \\ 0 & \text{if } r \ge 1 \end{cases}$$
Accumulated voxel density:
$$\rho(\mathbf{p}) = \sum_{i=1}^{N} w_i \cdot f\left(\frac{\|\mathbf{p} - \mathbf{c}_i\|}{R_i}\right)$$
where $w_i$ is derived from the memory's composite 4D truth vector (Confidence, Authority, Freshness, Corroboration).

### 3.2 3D Simplex & Curl Noise Perturbation
Raymarching incorporates 3D Simplex Noise $N(\mathbf{p} \cdot k + t)$ for ambient bioluminescent fluid breathing, plus 3D Curl Noise $\nabla \times \mathbf{F}(\mathbf{p}, t)$ for high-frequency electric plasma turbulence along active synaptic channels.

### 3.3 Optical Raymarching Integration (Emission & Absorption)
Along ray $\mathbf{r}(t) = \mathbf{o} + t\mathbf{d}$ within bounding volume `[-0.5, 0.5]^3`:
$$\text{Color}_{\text{accum}} += (1.0 - A_{\text{accum}}) \cdot \left[ \text{Emission}(\rho, \text{truth}) + \text{CoreGlow}(\rho^3) \right] \cdot \Delta s$$
$$A_{\text{accum}} += (1.0 - A_{\text{accum}}) \cdot \text{Absorption}(\rho) \cdot \Delta s$$

---

## 4. Code Base Cleanup Audit

### 4.1 Obsolete Files to Purge
The following 5 legacy particle-renderer files in `frontend/src/components/cognitive-field/` will be removed:
- `ParticleRenderer.ts` (Point sprites replaced by Volumetric Raymarcher)
- `FlowField.ts` (2D ambient dots replaced by 3D shader noise)
- `InfluencePathEntity.ts` (Explicit lines replaced by continuous density fields & synaptic filaments)
- `MemoryEntity.ts` (Per-particle scale arrays replaced by 3D Voxel Texture)
- `ShaderPipeline.ts` (Old point sprite shaders replaced by raymarching shader)

### 4.2 Core Files Retained & Refitted
- `ForceSimulation.ts`: Physics 3D node layout generator.
- `ActivationEngine.ts`: BFS recall propagation triggering dye pulses.
- `PulseSystem.ts`: Signal array uniform manager.
- `CameraController.ts`: Smooth 3D wildlife orbit, zoom, pan, focus targeting.
- `SelectionManager.ts`: 3D raycast picker for memory density centers.
- `graph-store.ts`, `EventBus.ts`, `client.ts`: Core state management and data API.
- UI Overlays (`SearchOverlay.tsx`, `NodeInspector.tsx`, `LandingPage.tsx`, `SettingsPage.tsx`).

---

## 5. New Modular Files & Implementation Plan

### Phase 1: Core Volumetric Raymarcher & 3D Texture
- **`DataTexture3DManager.ts`**: Builds and updates a `THREE.Data3DTexture` ($64 \times 64 \times 64$ voxel density grid) executing Wyvill Quintic kernel rasterization.
- **`VolumetricRaymarchShader.ts`**: WebGL Raymarching fragment & vertex shader implementing 3D bounding box raymarching, 3D Simplex noise, dual color palettes (Cyan `#22d3ee` / Amber `#f59e0b`), core emission glow, and signal uniform integration.
- **`VolumetricFieldRenderer.ts`**: Three.js volume bounding mesh manager handling rendering ticks and uniform updates.

### Phase 2: Ultron Filamentary Synaptic Tendrils (Extra Feature)
- **`SynapticFilamentRenderer.ts`**: Procedural 3D noise-distorted energy filaments threading through density centers with glowing additive shaders.
- **`PlasmaNoiseEffect.ts`**: 3D Curl noise GLSL shader module for high-frequency electric plasma jitter.

### Phase 3: Engine Conductor Refactoring & UI Integration
- Update **`CognitiveFieldEngine.ts`** to tie `DataTexture3DManager`, `VolumetricFieldRenderer`, and `SynapticFilamentRenderer` to Zustand store updates and EventBus signals.
- Polish **`CognitiveCanvas.tsx`**, **`SearchOverlay.tsx`**, and **`NodeInspector.tsx`** for full UI synergy with the new Ultron neural field.

---

## 6. Verification Plan

### Automated Build Verification
- Execute `npm run build` inside `frontend/` to ensure zero TypeScript errors or GLSL compilation failures.

### Visual & Performance Verification
- Verify 60fps continuous volumetric fluid cloud rendering on `/explore`.
- Verify cyan (JARVIS) and golden amber (Mind Stone) color transitions based on truth vectors and agent belief states.
- Test search recall pulses to ensure high-velocity dye/light propagation along synaptic tendrils.
- Test smooth camera navigation, zoom, and 3D node selection.
