# Mathematical Specifications

## 1. Truth Maintenance Algebra (TMS)

The Truth Maintenance System treats "Truth" not as a boolean (`True`/`False`) but as a 4-dimensional tensor. The scalar "Truth Score" ($S$) is a derived property used for ranking and decision-making.

### 1.1 The Truth Vector
Let $V_e$ be the Truth Vector for an event $e$:
$$ V_e = \begin{bmatrix} C_e \\ A_e \\ F_e \\ R_e \end{bmatrix} $$

Where:
*   $C_e \in [0, 1]$: **Confidence**. The model's internal probability (logit) of correctness.
*   $A_e \in [0, 1]$: **Authority**. The reliability of the source (User=1.0, Verified Agent=0.9, Web=0.5).
*   $F_e \in [0, 1]$: **Freshness**. A time-decayed value representing temporal relevance.
*   $R_e \in [0, \infty)$: **Corroboration**. A count of distinct sources confirming this fact.

### 1.2 The Truth Score Function
The scalar Truth Score $S(V_e)$ is a linear combination of the vector components with a logarithmic dampener on corroboration.

$$ S(V_e) = w_1 \cdot C_e + w_2 \cdot A_e + w_3 \cdot F_e + w_4 \cdot \ln(1 + R_e) $$

**Default Weights (Phase 3.4):**
$$ w_1 = 1.0, \quad w_2 = 1.0, \quad w_3 = 1.0, \quad w_4 = 1.0 $$

**Implementation:** `memory_thread.services.tms_service.TruthVectorService.calculate_score`

---

## 2. Temporal Decay Mechanics

Memory fades over time unless reinforced. This is modeled via an exponential decay function applied to the $F$ (Freshness) component.

### 2.1 The Decay Function
Let $t_{now}$ be the current time and $t_{event}$ be the timestamp of the memory.
Let $\Delta t$ be the age in days: $\Delta t = (t_{now} - t_{event})_{\text{days}}$.

The decayed importance $I(t)$ is calculated as:

$$ I(t) = \max(0.01, I_0 \cdot e^{-\lambda \cdot \Delta t}) $$

Where $\lambda$ (Lambda) is the decay rate specific to the memory type:
*   **Events:** $\lambda = 0.02$ (Fast decay)
*   **Preferences:** $\lambda = 0.005$ (Slow decay)
*   **Identities:** $\lambda = 0.0005$ (Near-permanent)

**Implementation:** `memory_thread.services.decay_service.apply_decay`

---

## 3. State Derivation Logic

The state of an entity $E$ at time $t$ is the result of applying a sequence of Event Deltas ($\delta$) to an initial empty state $S_0$.

### 3.1 The Derivation Function
$$ S_{t+1} = f(S_t, \delta_{t+1}) $$

The application logic $f$ depends on the field type within the delta $\delta$:

1.  **Numeric Fields (Counter-style):**
    If $S_t[k] \in \mathbb{R}$ and $\delta[k] \in \mathbb{R}$:
    *   If Action is `ADD` or `PLANT`: $S_{t+1}[k] = S_t[k] + \delta[k]$
    *   If Action is `REMOVE`: $S_{t+1}[k] = S_t[k] - \delta[k]$
    *   If Action is `UPDATE`: $S_{t+1}[k] = \delta[k]$

2.  **Discrete Fields (Replacement):**
    For all other types:
    $$ S_{t+1}[k] = \delta[k] $$

**Implementation:** `memory_thread.services.tms_service.StateDerivationService.apply_event`

---

## 4. The Slab Allocator Protocol

To achieve zero-copy ingestion, the system uses a custom binary protocol over shared memory.

### 4.1 Memory Layout
The Shared Memory segment is divided into $N$ blocks of size $M$ (default 64KB).
Each block (Slab) follows this binary structure:

| Offset | Size | Type | Description |
| :--- | :--- | :--- | :--- |
| 0x00 | 4 Bytes | `uint32_t` (Big Endian) | **Length Header** ($L$). The size of the payload. |
| 0x04 | $L$ Bytes | `bytes` | **Payload**. The UTF-8 JSON or Text content. |
| ... | ... | ... | *Padding / Unused Space* |

### 4.2 Allocation Algorithm (Stack-Based)
The allocator uses a LIFO Stack for $O(1)$ allocation, protected by a Semaphore.

1.  **Reserve:**
    $$ \text{Acquire}(Sem) $$
    $$ \text{Lock}(L) $$
    $$ \text{SlabID} \leftarrow Stack[top] $$
    $$ top \leftarrow top - 1 $$
    $$ \text{Unlock}(L) $$

2.  **Release:**
    $$ \text{Lock}(L) $$
    $$ top \leftarrow top + 1 $$
    $$ Stack[top] \leftarrow \text{SlabID} $$
    $$ \text{Unlock}(L) $$
    $$ \text{Release}(Sem) $$

**Implementation:** `memory_thread.utils.shared_memory.SlabAllocator`
