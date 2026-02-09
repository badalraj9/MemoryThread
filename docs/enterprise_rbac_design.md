# RBAC & Authority Design for Memory Thread

## 1. Role Hierarchy (Pentagon Classification)

Memory Thread implements a **Pentagon-grade clearance system** with six tiers, each unlocking progressively more powerful capabilities.

### Clearance Grades

| Grade         | Name       | Clearance | CLI Access                                                                |
| :------------ | :--------- | :-------- | :------------------------------------------------------------------------ |
| **E-CLASS**   | Guest      | 0         | `mt`, `mt ask`, `mt whoami`                                               |
| **C-CLASS**   | Employee   | 1         | + `mt status`, `mt search`, `mt load`                                     |
| **B-CLASS**   | Developer  | 2         | + `mt galaxy`, `mt conflicts`, `mt provenance`, `mt agent`, `mt provider` |
| **A-CLASS**   | Researcher | 3         | + `mt decay`, `mt consolidate`, `mt export`, `mt snapshot`                |
| **S-CLASS**   | Executive  | 4         | + `mt prune`, `mt audit`, `mt clients`                                    |
| **SSS-CLASS** | Godfather  | 5         | + `mt clear`, `mt rootkey`, `mt su`, `mt sudo`                            |

### Grant Hierarchy

```
SSS-CLASS (Godfather)  ─▶ can grant ─▶ S-CLASS
S-CLASS   (Executive)  ─▶ can grant ─▶ A-CLASS
A-CLASS   (Researcher) ─▶ can grant ─▶ B-CLASS
B-CLASS   (Developer)  ─▶ can grant ─▶ C-CLASS
C-CLASS   (Employee)   ─▶ can grant ─▶ E-CLASS
E-CLASS   (Guest)      ─▶ no grant power
```

---

## 2. Namespace Domains

| Domain       | Accessible By |
| :----------- | :------------ |
| `public`     | All grades    |
| `team_*`     | C-CLASS+      |
| `tech_*`     | B-CLASS+      |
| `research_*` | A-CLASS+      |
| `ops_*`      | S-CLASS+      |
| `*` (all)    | SSS-CLASS     |

---

## 3. The "Firewall" Logic (Read Access)

When `recall()` or `chat()` executes, the access control layer checks:

1. **Namespace Access:** Does user's grade permit reading this namespace?
2. **Clearance Level:** Is the memory tagged with a clearance level ≤ user's grade?

**Rule:** `IF (User.Grade >= Namespace.MinGrade) AND (User.Grade >= Memory.Clearance) THEN Access Granted`

Denied memories appear as `[REDACTED]` in search results.

---

## 4. The "Truth Authority" Logic (Write Access)

When `remember()` executes (including auto-remember during chat), the authority score is calculated from the user's grade and target namespace:

| User Grade    | Target Domain  | Authority Score | Logic              |
| :------------ | :------------- | :-------------- | :----------------- |
| **SSS-CLASS** | Any            | **0.95**        | Strategic override |
| **S-CLASS**   | `ops_*`        | **0.90**        | Operational domain |
| **A-CLASS**   | `research_*`   | **0.90**        | Expert domain      |
| **B-CLASS**   | `tech_*`       | **0.90**        | Expert domain      |
| **B-CLASS**   | `research_*`   | **0.50**        | Observer           |
| **C-CLASS**   | `team_*`       | **0.60**        | Standard input     |
| **E-CLASS**   | `public`       | **0.10**        | Low trust          |
| Any           | Outside domain | **0.00**        | Write denied       |

**Conflict Resolution:** Higher authority memories naturally win during contradiction detection. If an Employee says "Sky is Green" (auth 0.6) and an Executive says "Sky is Blue" (auth 0.95), the TMS resolves "Blue" as truth.

---

## 5. Implementation Architecture

### `AccessControlService`

```python
class AccessControlService:
    def get_grade(self, role: str) -> int: ...
    def calculate_write_authority(self, role: str, namespace: str) -> float: ...
    def can_read(self, role: str, memory_namespace: str, memory_clearance: int) -> bool: ...
    def can_execute(self, role: str, command: str) -> bool: ...
```

### `SecureMemoryClient` (Wrapper)

Wraps `MemoryClient` to enforce RBAC transparently:

- **On `chat()`:** Auto-calculates authority, filters context by clearance
- **On `remember()`:** Injects authority and clearance metadata
- **On `recall()`:** Filters results by namespace/clearance access

### `MT_ROLE` Environment Variable

The user's current role is set via environment variable:

```bash
export MT_ROLE=developer    # B-CLASS
export MT_USER=alice
export MT_NAMESPACE=tech_core
```

---

## 6. CLI Integration

- **Grade Badge:** Displayed in CLI prompt showing current clearance
- **Access Denied:** Commands above user's grade show `⛔ ACCESS DENIED — requires {grade}`
- **Redacted Results:** Search results from higher-clearance namespaces show `[REDACTED]`
- **Authority Display:** Memories show authority indicator (HIGH/MED/LOW) based on source grade
