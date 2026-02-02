# RBAC & Authority Design for Memory Thread Enterprise

## 1. Role Hierarchy & Permissions

We will implement a Role-Based Access Control (RBAC) system defined in a configuration structure (simulating a policy file).

### Roles

| Role | Clearance Level | Description |
| :--- | :--- | :--- |
| **GUEST** | 0 | Public access only. Can read `public` namespace. |
| **EMPLOYEE** | 1 | Standard internal access. Can read/write `team_*` namespaces. |
| **DEVELOPER** | 2 | Technical access. Can read/write `tech_*`, read `product`. |
| **RESEARCHER** | 3 | Cross-domain access. Read ALL. Write `research`. |
| **EXECUTIVE** | 4 | Strategic access. Full Read/Write/Override power. |

### Domains (Namespaces)

*   `public`: Accessible by everyone.
*   `team_general`: Accessible by Employees+.
*   `tech_core`: Accessible by Developers, Researchers, Execs.
*   `finance_secret`: Accessible by Executives only.
*   `research_lab`: Accessible by Researchers, Execs.

---

## 2. The "Firewall" Logic (Read Access)

When a `recall()` or `chat()` happens, the Firewall checks:

1.  **Direct Namespace Access:** Does user have `READ` permission on the memory's namespace?
2.  **Clearance Level:** Is the memory tagged with a clearance level higher than the user?
    *   *Note: In the Core SDK, we store `clearance` in the memory's metadata/payload.*

**Rule:** `IF (User.Roles allows Namespace) AND (User.Clearance >= Memory.Clearance) THEN Access Granted.`

---

## 3. The "Truth Authority" Logic (Write Access)

When a `remember()` happens, we calculate the `authority` (0.0 - 1.0) passed to the Core SDK based on the User's Role and the Domain they are writing to.

**Matrix:**

| User Role | Target Domain | Authority Score | Logic |
| :--- | :--- | :--- | :--- |
| **EXECUTIVE** | Any | **0.95** | Strategic override. |
| **RESEARCHER**| `research_lab` | **0.90** | Expert domain. |
| **RESEARCHER**| `tech_core` | **0.50** | Observer. |
| **DEVELOPER** | `tech_core` | **0.90** | Expert domain. |
| **DEVELOPER** | `finance_secret`| **0.00** | (Write Denied) |
| **EMPLOYEE** | `team_general` | **0.60** | Standard input. |
| **GUEST** | `public` | **0.10** | Low trust. |

*   **Conflict Resolution:** If an *Employee* says "Sky is Green" (Auth 0.6) and an *Executive* says "Sky is Blue" (Auth 0.95), the Core SDK's math naturally resolves "Blue" as the truth.
*   **Decay:** Higher authority memories decay slower (managed by core, but we can influence initial freshness).

---

## 4. Implementation Strategy (No Core Changes)

1.  **`AccessControlService` (New Class):**
    *   Holds the hardcoded Policy (the matrix above).
    *   `calculate_write_authority(user, namespace) -> float`
    *   `can_read(user, memory_namespace, memory_metadata) -> bool`

2.  **`SecureMemoryClient` (Wrapper Class):**
    *   Wraps `MemoryClient`.
    *   **Input:** `user_id`, `role`.
    *   **On `remember(content, namespace)`:**
        *   Call `AccessControlService` to get authority.
        *   Inject `clearance_level` into the `metadata` of the memory (Core SDK stores payload/metadata).
        *   Call `CoreSDK.remember(content, authority=calculated_auth)`.
    *   **On `recall(query)`:**
        *   Call `CoreSDK.recall(query)`.
        *   Iterate results.
        *   Filter out any memory where `AccessControlService.can_read(...)` is False.
        *   Return filtered list (or "[REDACTED]" placeholders).

## 5. TUI Integration

*   **New Command:** `/login <role>` (Simulates switching user token).
*   **Visuals:**
    *   Display current "Security Clearance" in the footer.
    *   Show `[REDACTED]` for memories the current user shouldn't see.
    *   Show "Authority: High/Med/Low" indicators on messages.
