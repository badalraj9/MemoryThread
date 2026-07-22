# MemoryThread — Web UI Design Spec

## Product DNA

MemoryThread is a **truth-preserving, multi-agent cognitive memory system** for AI. It's an event-sourced memory layer that stores everything as a causal graph with 4D truth vectors (confidence, authority, freshness, corroboration). The web UI is called **"Graph Explorer"**.

**Vibe:** Dark, academic/research tool. Minimal, precise, terminal-adjacent. Think Linear + Stripe dashboard meets a neuroscience lab monitor. Green accent (`#3dd68c`), monospace secondary font (`JetBrains Mono`), subtle grid background.

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────┐
│                     Shell Layout                             │
│  ┌───────┬─────────────────────────────────────────────┐    │
│  │       │                                             │    │
│  │ Side  │         Content Area                        │    │
│  │ Bar   │    (Router-driven: Graph / Chat / Dash)     │    │
│  │       │                                             │    │
│  │ Nav   │                                             │    │
│  │       │                                             │    │
│  └───────┴─────────────────────────────────────────────┘    │
│  ───────────── Status Bar (namespace, health pills) ─────── │
└─────────────────────────────────────────────────────────────┘
```

**Routes:**
- `/` → Landing page (full-viewport cinematic intro)
- `/explore` → Graph Explorer (centerpiece)
- `/chat` → Chat interface with memory panel
- `/dashboard` → Stats, health, metrics
- `/galaxy` → Multi-agent fact/belief explorer
- `/settings` → Configuration

---

## Component Tree (Full)

### Phase 1: Shell & Infrastructure

#### 1. `AppShell` — Root layout
- **Props:** `children`
- **States:** N/A (structural)
- **Description:** Full-height flex layout. Contains TopBar + (Sidebar || null) + Content area. Handles keyboard shortcuts globally.
- **Edge case:** On landing page (`/`), sidebar is hidden, content is full-bleed.

#### 2. `TopBar` — Global header
- **Props:** none
- **States:** N/A
- **Description:** Thin horizontal bar (48px). Left: logo + breadcrumb. Center: global SearchBar. Right: namespace dropdown + health badges.
- **Edge case:** Health badges poll every 10s; show grey "connecting..." on first load before first response.

#### 3. `Sidebar` — Navigation
- **Props:** `collapsed: boolean`, `onToggle: () => void`
- **States:** collapsed (icons only, 52px) / expanded (180px with labels)
- **Description:** Vertical nav. Items: Graph Explorer, Chat, Dashboard, Galaxy, Settings. Each with Lucide icon. Active route highlighted. Collapse toggle at bottom.
- **Edge case:** On mobile or narrow viewport (<900px), sidebar auto-collapses.

#### 4. `StatusBadge` — Health indicator pill
- **Props:** `label: string`, `status: 'healthy' | 'degraded' | 'down' | 'loading'`
- **States:** healthy (green), degraded (amber), down (red), loading (grey pulsing)
- **Description:** Small rounded pill with dot indicator + label text. Used in TopBar for Postgres, Graph Engine, WAL status.
- **Edge case:** First render before API call shows "checking..." with grey pulse.

---

### Phase 2: The Graph (Centerpiece)

#### 5. `ForceGraph` — Main graph canvas
- **Props:** `nodes: GraphNode[]`, `edges: GraphEdge[]`, `onNodeClick: (id) => void`, `onNodeHover: (id | null) => void`, `filters: GraphFilters`
- **States:**
  - `loading`: First load, spinning indicator overlay
  - `empty`: No nodes/edges — show "Ingest your first memory" empty state with CTA
  - `populated`: Graph rendering with physics simulation
  - `filtered`: Some nodes hidden by filters — show count badge ("23 of 147 visible")
  - `error`: Failed to load graph data — error message with retry button
- **Description:** Custom D3 force-directed graph. SVG-based. `forceSimulation` with charge (-300), link distance (80), center gravity. Smooth `alpha` cooling on init. 60fps during interaction, drops to idle when stable. Nodes are `<circle>`, edges are `<path>` (cubic bezier curves).
- **Interactions:**
  - **Pan:** Click-drag on background
  - **Zoom:** Scroll wheel. Smooth D3 zoom behavior. Min zoom: 0.1x, max: 5x.
  - **Click node:** Select, open NodeInspector sidebar
  - **Click background:** Deselect, close sidebar
  - **Hover node:** Show NodeTooltip, dim other nodes by 50%
  - **Drag node:** Reposition (pinned until released, then returns to simulation)
  - **Double-click node:** Zoom to fit, center view on it
- **Animation effects:**
  - **On mount:** Nodes spawn from center with stagger, edges fade in behind
  - **On new memory:** Node pulses in from 0 to full size, ripple to neighbors
  - **On selection:** Selected node gets glow stroke (2px with `#3dd68c`), connected edges highlight, rest dims to 20% opacity
  - **On golden thread trace:** Animated path highlight along causal chain (dashed line with dash-offset animation)
- **Edge case:** >1000 nodes — switch to Canvas renderer (detect via node count threshold), fall back to simplified rendering (no labels, reduced physics quality).

#### 6. `GraphNode` — Visual node element
- **Props:** `node: GraphNode`, `isSelected: boolean`, `isDimmed: boolean`, `isHighlighted: boolean`
- **States:** default, hovered, selected, dimmed, pulsing (on update)
- **Description:** SVG circle. Radius = `map(truth_score, 0→1, 4→20)`. Fill = categorical color by `memory_type`. Stroke = selected state glow. Framer Motion `animate` drives transitions between states.
- **Memory type color mapping:**
  - `fact` → `#3dd68c` (green)
  - `event` → `#6c8fff` (blue)
  - `preference` → `#a78bfa` (purple)
  - `identity` → `#f0a500` (amber)
  - `prediction` → `#f25050` (red)
  - `decision` → `#f97316` (orange)
  - `failure` → `#ef4444` (red - darker)
  - `workflow` → `#22d3ee` (cyan)
  - `belief` → `#e879f9` (pink)
- **Edge case:** Node with very low truth score (<0.2) renders as semi-transparent (opacity 0.3) with dashed border, suggesting "decayed/prunable".

#### 7. `GraphEdge` — Visual edge/link
- **Props:** `edge: GraphEdge`, `isHighlighted: boolean`, `isDimmed: boolean`
- **States:** default, highlighted, dimmed, animated (golden thread trace)
- **Description:** SVG `<path>` with cubic bezier. Stroke-width = `map(confidence, 0→1, 0.5→3)`. Stroke-opacity = confidence * 0.6. Arrow marker if directed. Label on hover (relation type).
- **Edge case:** Multiple edges between same nodes — offset curves to prevent overlap (bundling).

#### 8. `GraphControls` — Overlay controls
- **Props:** `filters: GraphFilters`, `onFilterChange: (f) => void`, `onZoomToFit: () => void`, `onReset: () => void`
- **States:** N/A
- **Description:** Top-right overlay on the graph canvas. Small semi-transparent panel with:
  - Zoom to Fit button
  - Filter: namespace dropdown
  - Filter: memory type checkboxes (collapsible)
  - Filter: truth score range slider (0–1)
  - Toggle: show edge labels
  - Reset Layout button
- **Edge case:** When all filters active result in 0 visible nodes, show inline banner "No nodes match filters" with reset link.

#### 9. `NodeTooltip` — Hover preview
- **Props:** `node: GraphNode`, `position: {x, y}`, `onClose: () => void`
- **States:** N/A
- **Description:** Floating panel near cursor. Shows: content (truncated 120 chars), truth score bar (4px tall, green fill), memory type badge, source label, entity_id (truncated).
- **Edge case:** Tooltip near viewport edge flips position to stay visible. Follows cursor with slight delay (50ms).

#### 10. `NodeInspector` — Slide-over detail panel
- **Props:** `nodeId: string | null`, `onClose: () => void`
- **States:**
  - `closed`: Hidden
  - `loading`: Skeleton placeholders
  - `loaded`: Full content visible
  - `error`: "Failed to load node details" with retry
  - `empty`: Node exists but no additional data
- **Description:** Slides in from right edge (400px). Divided into sections:
  1. **Header:** Entity ID (truncated monospace), memory type badge, close button
  2. **Content:** Full memory content text
  3. **Truth Vector:** 4 horizontal bars with labels:
     - Confidence — green fill
     - Authority — amber fill
     - Freshness — blue fill
     - Corroboration — purple fill
     - Composite score — large number at bottom
  4. **Golden Thread:** Collapsible timeline. Each event shown as a node on a vertical line. Click event to expand details (actor, action, delta).
  5. **Related Memories:** Horizontal scroll list of connected node cards. Click navigates to that node.
  6. **Actions:** Delete (forget) button with confirmation dialog.
- **Animation:** Panel slides in with 300ms ease-out. Content sections stagger in (50ms delay each). Transition to `@radix-ui/react-dialog` on mobile.
- **Edge case:** Very long content (>1000 chars) shows in a scrollable container with "Show more" if under 500 chars actually just show full text.

#### 11. `GraphEmptyState` — First-use state
- **Props:** `onIngest: () => void`
- **States:** N/A
- **Description:** Centered over graph canvas when no nodes exist. Icon (🧠 or custom SVG), title "No memories yet", description "Your cognitive graph starts empty. Ingest your first memory to see it come alive.", CTA button "Ingest a Memory" + secondary "Try with Sample Data".
- **Edge case:** Shown only on first visit (localStorage flag). Subsequent empty states show different messaging.

---

### Phase 3: Landing Page

#### 12. `LandingPage` — Full-viewport intro
- **Props:** none
- **States:** initial (pre-scroll), scrolling, transitioned (left page)
- **Description:** Full viewport (100vh). Dark background with the D3 graph running live (seeded with sample data showing the graph forming). Center overlay:
  - Title: "MemoryThread" (large, 64px, light weight)
  - Tagline: "A truth-preserving cognitive graph for AI"
  - Subtitle: "Event-sourced memory with 4D truth vectors, causal tracing, and multi-agent belief spaces."
  - Two CTAs: "Explore the Graph" → /explore, "See How It Works" → scrolls down
- **Scroll behavior:** Framer Motion `useScroll` + `useTransform`. On scroll: graph zooms out, title fades up, transitions to ScrollNarrative sections. At threshold, navigates to `/explore`.

#### 13. `ScrollNarrative` — Story sections
- **Props:** none
- **States:** per-section: entering, active, leaving
- **Description:** 3–4 sticky scroll sections below hero. Each section takes 80vh, using `position: sticky; top: 0`. As user scrolls through, the graph (still visible behind glassmorphism overlay) animates to demonstrate the concept:
  1. **"Every memory is an event"** — Nodes appear one by one, each with a ripple
  2. **"Truth is a vector"** — Hover a node, the 4 truth bars pulse
  3. **"Causal chains connect everything"** — Golden thread animation traces through nodes
  4. **"Multiple agents, shared beliefs"** — Graph splits into colored clusters
- **Edge case:** Reduced motion preference (`prefers-reduced-motion`) — use simpler fade transitions, no parallax.

---

### Phase 4: Memory Browser & Chat

#### 14. `ChatPanel` — Chat interface
- **Props:** `threadId: string | null`, `onNewThread: () => void`
- **States:**
  - `empty`: No messages — show suggestion chips
  - `loading`: Sending message — typing indicator visible
  - `populated`: Messages in thread
  - `error`: API error — error banner with retry
- **Description:** React port of `mt_chat_ui.html`. Message list (scrollable), input bar at bottom. Messages are bubbles: user = right-aligned blue, AI = left-aligned dark. Typing indicator = 3 bouncing dots. Each AI response shows model tag + entity_id badge.
- **Suggestion chips:** "My name is...", "I prefer...", "What do you remember about me?", "I work on..."
- **Edge case:** Network disconnected — show offline indicator, queue message for retry.

#### 15. `MessageBubble` — Single chat message
- **Props:** `role: 'user' | 'assistant'`, `content: string`, `meta?: {model, entityId, timestamp}`
- **States:** sending (greyed out, spinner), sent, error (red border, retry)
- **Description:** Flex layout. Avatar (initials or icon) + bubble content. User: right-aligned. Assistant: left-aligned. Meta row below showing timestamp + optional model tag.

#### 16. `RecallSidebar` — Chat memory panel
- **Props:** `memories: Memory[]`, `context: string | null`, `searchResults: Memory[]`, `onSearch: (q) => void`, `activeTab: 'recalled' | 'context' | 'search'`
- **States:**
  - `recalled` tab: list of memories retrieved for current turn, or empty state
  - `context` tab: injected prompt context text, or "No context injected" empty state
  - `search` tab: search input + results, or "Search memories" empty state
- **Description:** Replicates the right panel from `mt_chat_ui.html`. Each tab has its own content. Memory cards use MemoryCard component. Stats grid at bottom (memories, events, avg truth, vector DB status).

#### 17. `MemoryTable` — Tabular view of all memories
- **Props:** `memories: Memory[]`, `loading: boolean`, `onSort: (key, dir) => void`, `onSelect: (id) => void`, `selectedIds: Set<string>`, `onBulkAction: (action) => void`
- **States:** loading (skeleton rows), empty (no memories message), populated, filtered (showing X of Y)
- **Description:** Virtualized table via `react-window`. Columns:
  - Content (truncated, max 200px)
  - Truth Score (mini bar + numeric)
  - Memory Type (colored badge)
  - Source (label)
  - Freshness (mini bar)
  - Timestamp (relative: "2h ago")
  - Actions (view on graph, forget)
- **Interactions:** Click row to select (checkbox). Shift-click for range. Sort ASC/DESC by clicking column header. Bulk action bar appears when >= 1 selected.
- **Edge case:** >10,000 memories — virtual scroll keeps it performant. Show count badge "1-50 of 12,430".

#### 18. `SearchBar` — Global search
- **Props:** `placeholder?: string`, `onResultSelect: (entityId) => void`
- **States:** idle, typing (debounce spinner: 300ms), results (dropdown), no results, error
- **Description:** Input field with search icon. `/memory/recall` query on debounced input. Dropdown shows top 5 results as compact MemoryCards. Click navigates to graph view centered on that node. Keyboard: arrow keys navigate results, Enter selects, Escape closes.
- **Edge case:** Search while offline — show "No connection" message, cache last results.

---

### Phase 5: Dashboard & Monitoring

#### 19. `Dashboard` — Main monitoring page
- **Props:** none
- **States:** loading (skeleton grid), loaded, error (retry banner), stale (subtle "data may be stale" warning if >30s since last update)
- **Description:** Grid layout (2 columns desktop, 1 column mobile). Contains: StatsGrid, TruthDistributionChart, HealthSummary, EventTimeline (latest 10), DecayCurves (if data available).

#### 20. `StatsGrid` — KPI row
- **Props:** `stats: Stats | null`, `loading: boolean`
- **States:** loading (skeleton cards), loaded, error (dashes)
- **Description:** 4 stat cards in a row. Each card: label (small, uppercase, dim), value (large, bold), sub-label (tiny, dim). Cards: Total Memories, Total Events, Avg Truth Score, Health Score. Health Score card also shows green/amber/red indicator.
- **Edge case:** Any stat is null/undefined — show "—" instead of 0 (distinguishes "not loaded" from "zero").

#### 21. `TruthDistributionChart` — Score histogram
- **Props:** `data: {bucket: string, count: number}[]`, `loading: boolean`
- **States:** loading, empty (no data), populated
- **Description:** Recharts `BarChart`. X-axis: score buckets ("0.0-0.1", "0.1-0.2", ... "0.9-1.0"). Y-axis: count. Bars colored green gradient (low scores dim, high scores bright). Tooltip on hover shows exact count + bucket.
- **Edge case:** All memories in 1 bucket — show note "Low variance in truth scores" to alert user.

#### 22. `EventTimeline` — Recent events
- **Props:** `events: Event[]`, `loading: boolean`
- **States:** loading, empty, populated
- **Description:** Vertical timeline. Each event row: timestamp (relative), actor icon, action label (color-coded), content preview, entity_id link. Click entity_id navigates to graph.
- **Edge case:** Very frequent events (>100/min) — aggregate into summary rows with expand.

#### 23. `HealthSummary` — Component health
- **Props:** `checks: HealthCheck[]`, `loading: boolean`
- **States:** loading, all healthy, degraded, error
- **Description:** List of health checks. Each row: status icon (green check / amber warning / red X), component name, latency (if applicable), detail message. Last checked timestamp at bottom.

---

### Phase 6: Galaxy (Multi-Agent)

#### 24. `GalaxyDashboard` — Multi-agent overview
- **Props:** none
- **States:** loading, loaded, error
- **Description:** Top section: agent count, fact count, belief count. Main area: tabs for Facts, Beliefs, Conflicts. Each tab has its own component.

#### 25. `FactList` — Immutable facts browser
- **Props:** `facts: Fact[]`, `loading: boolean`, `onFactClick: (id) => void`
- **States:** loading, empty, populated
- **Description:** Card list. Each fact card: content hash (truncated, monospace), content, source URI, content type badge, timestamp. Click expands to show full metadata JSON.

#### 26. `BeliefMatrix` — Agent belief heatmap
- **Props:** `beliefs: Belief[]`, `agents: Agent[]`
- **States:** loading, empty (no beliefs yet), populated
- **Description:** 2D grid. Rows = agents (labeled). Columns = belief dimensions (derived dynamically). Cell = authority score mapped to color (white → green gradient). Hover shows exact values. Click cell shows belief detail.

#### 27. `GalaxyQueryBuilder` — OLAP query form
- **Props:** `onQuery: (operation, params) => void`, `results: GalaxyResult | null`, `loading: boolean`
- **States:** form input, loading (spinner on submit button), results (table), empty results ("No results found"), error
- **Description:** Operation selector dropdown (SLICE, DICE, DRILL_DOWN, ROLL_UP, SEARCH). Dynamic form fields based on operation:
  - SLICE: agent_id, belief_id filters
  - DICE: min_authority, min_confidence sliders
  - DRILL_DOWN: source_uri, belief_id
  - ROLL_UP: source_uri, agent_id
  - SEARCH: free text query
  - Common: top_k slider (1-100)
- Results displayed as table with columns based on operation type.

#### 28. `ConflictGraph` — Mini contradiction viewer
- **Props:** `conflicts: Conflict[]`, `loading: boolean`
- **States:** loading, empty ("No conflicts detected — clean"), populated, error
- **Description:** Mini force-directed graph (reuses layout from ForceGraph but simpler, fewer nodes). Conflicting beliefs shown with red edges between agent nodes. Click conflict edge shows resolution options (authority/consensus/recency strategy selector).

---

### Phase 7: System Controls

#### 29. `ContradictionChecker` — Content check tool
- **Props:** none (self-contained with API call)
- **States:** input, checking (spinner), result found (conflict display), no conflict (green success), error
- **Description:** Textarea input + "Check" button. Result: CONFLICT = red banner showing conflicting memory content + entity_id link + explanation. NO CONFLICT = green banner "No contradictions found".

#### 30. `PruneControl` — Memory pruning panel
- **Props:** none
- **States:** idle, previewing (shows count), executing (progress), done (result count)
- **Description:** Threshold slider (0.0-1.0, default 0.3) with live preview count ("X memories below threshold"). "Preview" button scans and shows list of candidates. "Execute Prune" button with confirmation dialog.

#### 31. `DecayControl` — Decay configuration
- **Props:** none
- **States:** idle, applying, done
- **Description:** Table of memory types with their decay lambda values. Inline editing. "Apply Decay" button. Optional: "Simulate" button shows projected decay curve chart for next 30 days.

#### 32. `MergeProposals` — Entity dedup UI
- **Props:** `proposals: MergeProposal[]`, `onApprove: (proposal) => void`, `onReject: (proposal) => void`, `loading: boolean`
- **States:** loading, empty ("No duplicates detected"), populated, error
- **Description:** List of detected duplicate entity pairs. Each proposal card: source entity (left) vs target entity (right) side-by-side comparison showing content + truth vectors. Confidence score badge. Approve / Reject buttons. "Scan for Duplicates" manual trigger button.

#### 33. `SnapshotManager` — State checkpoints
- **Props:** `snapshots: Snapshot[]`, `onTakeSnapshot: () => void`, `loading: boolean`
- **States:** loading, empty, populated, taking (progress indicator)
- **Description:** List of snapshots with: timestamp (absolute), Merkle hash (truncated monospace, copyable), entity count. "Take Snapshot" button. Click snapshot to expand details.

#### 34. `SettingsPage` — Configuration
- **Props:** none
- **States:** loading, loaded, saving, error
- **Description:** Form sections:
  1. **Namespace:** current namespace display + switcher
  2. **API:** API key display (masked) + regenerate button
  3. **Durability:** WAL mode toggle (sync/batched)
  4. **TMS Weights:** 4 sliders for confidence/authority/freshness/corroboration weights (must sum to 1.0)
  5. **Theme:** dark/light/system toggle
  6. **Danger Zone:** "Reset Graph" / "Clear All Memories" with confirmation
- **Edge case:** Unsaved changes — show unsaved indicator dot on tab. Confirm before navigating away.

---

## Data Flow

```
User Action → Zustand Action → API Client (fetch) → FastAPI Backend
                                            ↓
User sees ← React Re-render ← Zustand State ← Response
```

- **TanStack Query** handles caching, deduplication, background refetching for API calls
- **Zustand** handles UI state (sidebar open, selected node, active filters)
- When user clicks a graph node:
  1. `ForceGraph` calls `onNodeClick(id)`
  2. Store sets `selectedNodeId`
  3. `NodeInspector` picks up the change, calls `api.getGoldenThread(id)`
  4. TanStack Query manages loading/error/success states
  5. Result stored in TanStack Query cache, rendered by NodeInspector

---

## API Surface (Endpoints the UI Calls)

| Method | Path | Usage | Component |
|--------|------|-------|-----------|
| GET | `/stats` | System stats | Dashboard, StatsGrid |
| GET | `/health` | Health checks | StatusBadge, HealthSummary |
| GET | `/version` | Version info | Settings, about |
| POST | `/memory/remember` | Store a memory | ChatPanel, ingest forms |
| POST | `/memory/recall` | Search memories | SearchBar, MemoryTable, ChatPanel |
| POST | `/memory/check_contradiction` | Check for conflicts | ContradictionChecker |
| DELETE | `/memory/{id}` | Forget a memory | NodeInspector (actions) |
| GET | `/memory/{id}/golden-thread` | Causal chain | NodeInspector (golden thread) |
| POST | `/galaxy/fact` | Ingest a fact | FactList (add form) |
| POST | `/galaxy/belief` | Derive a belief | GalaxyQueryBuilder |
| POST | `/galaxy/query` | OLAP galaxy query | GalaxyQueryBuilder |
| GET | `/galaxy/stats` | Galaxy stats | GalaxyDashboard |
| GET | `/galaxy/conflicts` | Agent conflicts | ConflictGraph |
| GET | `/maintenance/proposals` | Merge proposals | MergeProposals |
| POST | `/maintenance/approve/merge` | Approve merge | MergeProposals (actions) |
| GET | `/maintenance/health/stats` | Health metrics | Dashboard, HealthSummary |
| GET | `/metrics` | Prometheus metrics | MetricsPanel |

---

## Visual Design System

### Colors (from existing `index.css`)

```
bg-base:          #050607     (deepest background)
bg-surface:       #0b0f14     (card/surface background)
border-subtle:    #1a1f26     (subtle borders)
border-default:   #1a1f26     (default borders)

text-primary:     #d6d9df     (primary text)
text-secondary:   #7a828e     (secondary/muted text)
text-tertiary:    #4a505a     (placeholder/disabled text)

accent-primary:   #3dd68c     (green — primary accent)
accent-secondary: #3dd68c     (green — secondary accent)

status-success:   #3dd68c     (green)
status-warning:   #eab308     (amber)
status-error:     #ef4444     (red)
```

### Typography
- **Primary:** Inter (sans-serif) — all UI text
- **Secondary:** JetBrains Mono (monospace) — entity IDs, code, hashes, timestamps
- **Sizes:** 10px (badges) / 12px (meta) / 14px (body) / 18px (h3) / 24px (h2) / 64px (hero)

### Spacing
- 4px grid. Common values: 8, 12, 16, 20, 24, 32, 48, 64.

### Dark/light mode
- Currently uses `prefers-color-scheme` media query
- Light mode: white bg-base, dark text, green accent shifts to darker green (`#2f7a4f`)
- Future: manual toggle in SettingsPage, persisted to Zustand

---

## Responsive Breakpoints

| Breakpoint | Width | Behavior |
|---|---|---|
| Desktop | >1200px | Full layout: sidebar + graph + inspector sidebar |
| Tablet | 768-1200px | Sidebar collapsed, inspector becomes overlay |
| Mobile | <768px | Sidebar hidden (hamburger), graph full-width, inspector = bottom sheet |

---

## Key Interactions to Polish

1. **Graph → Inspector transition:** Click node → inspector slides in from right with spring animation (300ms). Graph smoothly shifts left. No jarring layout jump.

2. **Graph node update animation:** When a `remember` occurs (via chat), new node spawns with scale 0→1 at the center, then force-simulated to position. Existing connected nodes pulse briefly.

3. **Golden thread trace:** User clicks "Trace" in inspector → graph view animates: camera focuses on entity node, then a dashed line with moving dashes traces through each ancestor node in sequence, pausing briefly at each. Like a subway map animation.

4. **Loading skeletons:** Every data-driven component shows skeleton placeholders (animated pulse, same dimensions as final content) — never raw spinners.

5. **Empty states:** Every list/table/graph has a purposeful empty state with illustration, explanation, and CTA — never just "No data".

6. **Error boundaries:** Each major section wrapped in `react-error-boundary`. Error shows component name + "Something went wrong" + retry button. Doesn't crash the whole app.
