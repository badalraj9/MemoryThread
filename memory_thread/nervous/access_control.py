
"""
Enterprise Access Control Service (The Firewall).

This module implements the "Intelligent Firewall" that sits between users and the raw memory store.
It enforces:
1. Role-Based Access Control (RBAC)
2. Domain-Specific Authority Scoring
3. Clearance Level Filtering
"""
from typing import Dict, List, Optional, Any
from dataclasses import dataclass
from enum import Enum, IntEnum
from memory_thread.models.provenance import ProvenanceEnvelope, Actor, Scope
from memory_thread.nervous.audit_ledger import ledger, AuditEvent

class ClearanceLevel(IntEnum):
    PUBLIC = 0
    INTERNAL = 1
    CONFIDENTIAL = 2
    SECRET = 3
    TOP_SECRET = 4

@dataclass
class UserContext:
    user_id: str
    role: str
    clearance: ClearanceLevel
    domains: List[str]

class AccessControlService:
    """
    The Single Source of Truth for Permissions and Authority.
    """

    # --- POLICY DEFINITIONS (In a real system, this comes from DB/LDAP) ---

    # Map Roles to Default Clearance
    ROLE_CLEARANCE = {
        "guest": ClearanceLevel.PUBLIC,
        "employee": ClearanceLevel.INTERNAL,
        "developer": ClearanceLevel.CONFIDENTIAL,
        "researcher": ClearanceLevel.SECRET,
        "executive": ClearanceLevel.TOP_SECRET,
        "root": ClearanceLevel.TOP_SECRET # God mode
    }

    # Map Roles to Domain Access (Namespaces they can Read/Write)
    # Format: "role": {"read": [domains], "write": [domains]}
    # "*" is wildcard
    ROLE_DOMAINS = {
        "guest": {
            "read": ["public"],
            "write": ["public"]
        },
        "employee": {
            "read": ["public", "team_general"],
            "write": ["team_general"]
        },
        "developer": {
            "read": ["public", "team_general", "tech_core", "product"],
            "write": ["tech_core", "product"]
        },
        "researcher": {
            "read": ["*"], # Can read everything (subject to clearance)
            "write": ["research_lab", "tech_core"]
        },
        "executive": {
            "read": ["*"],
            "write": ["*"]
        },
        "root": {
            "read": ["*"],
            "write": ["*"]
        }
    }

    # Authority Scoring Matrix: (Role, Domain) -> Score
    AUTHORITY_MATRIX = {
        ("root", "*"): 1.0,
        ("executive", "*"): 0.95,
        ("researcher", "research_lab"): 0.90,
        ("researcher", "tech_core"): 0.50,
        ("developer", "tech_core"): 0.90,
        ("developer", "product"): 0.80,
        ("employee", "team_general"): 0.60,
        ("guest", "public"): 0.10
    }

    # --- PUBLIC API ---

    @classmethod
    def create_context(cls, user_id: str, role: str) -> UserContext:
        """Factory to create a user context from a role."""
        role = role.lower()
        if role not in cls.ROLE_CLEARANCE:
            role = "guest"

        return UserContext(
            user_id=user_id,
            role=role,
            clearance=cls.ROLE_CLEARANCE[role],
            domains=cls.ROLE_DOMAINS[role]["read"]
        )

    @classmethod
    def calculate_write_authority(cls, user: UserContext, target_domain: str) -> float:
        """
        Determines the Truth Score (Authority) for a write operation.
        Returns 0.0 if write is denied.
        """
        # 1. Check Write Permission
        allowed_writes = cls.ROLE_DOMAINS[user.role]["write"]
        if "*" not in allowed_writes and target_domain not in allowed_writes:
            # AUDIT LOG: Write Denied
            ledger.log(AuditEvent(
                action_type="WRITE_DENIED",
                actor_id=user.user_id,
                role=user.role,
                target=target_domain,
                details={"reason": "domain_restriction"}
            ))
            return 0.0 # Denied

        # 2. Calculate Score
        # Check specific rule first
        score = cls.AUTHORITY_MATRIX.get((user.role, target_domain))
        if score is None:
            # Check wildcard rule
            score = cls.AUTHORITY_MATRIX.get((user.role, "*"))

        if score is None:
            # Fallback default authority
            score = 0.5

        return score

    @classmethod
    def can_read(cls, user: UserContext, envelope: Dict) -> bool:
        """
        The Firewall Check.
        Validates access against the PROVENANCE ENVELOPE.
        """
        # Extract scope from envelope dict
        # Structure: envelope = {_provenance: {scope: {domain: ...}}}
        # Or sometimes the envelope is passed directly if we extracted it.

        # We assume 'envelope' is the provenance dict or the full memory payload containing it
        provenance = envelope.get('_provenance')
        if not provenance:
            # If no provenance (legacy data), we might fallback or deny.
            # For strict security: Deny. For compatibility: Allow if Public.
            # Let's check if 'namespace' is at top level
            namespace = envelope.get('namespace', 'public')
            # Fallback logic
            return cls._legacy_check(user, namespace)

        scope = provenance.get('scope', {})
        target_domain = scope.get('domain') or scope.get('namespace')

        # 1. Domain Check
        allowed_reads = cls.ROLE_DOMAINS[user.role]["read"]
        if "*" not in allowed_reads and target_domain not in allowed_reads:
            # Silent Redaction (no audit log for simple filter to avoid spam)
            return False

        # 2. Clearance Check (Implicit in domain for this prototype)
        # In a full system, envelope would carry a specific classification tag
        # Here we map domain -> clearance
        req_clearance = cls._get_domain_clearance(target_domain)

        if req_clearance > user.clearance:
            # AUDIT: Access Denied (Clearance)
            ledger.log(AuditEvent(
                action_type="ACCESS_DENIED",
                actor_id=user.user_id,
                role=user.role,
                target=target_domain,
                details={"reason": "insufficient_clearance", "required": req_clearance.name}
            ))
            return False

        return True

    @classmethod
    def _legacy_check(cls, user: UserContext, namespace: str) -> bool:
        allowed = cls.ROLE_DOMAINS[user.role]["read"]
        if "*" in allowed: return True
        return namespace in allowed

    @classmethod
    def _get_domain_clearance(cls, domain: str) -> ClearanceLevel:
        if "public" in domain: return ClearanceLevel.PUBLIC
        if "team" in domain: return ClearanceLevel.INTERNAL
        if "tech" in domain: return ClearanceLevel.CONFIDENTIAL
        if "research" in domain: return ClearanceLevel.SECRET
        if "secret" in domain: return ClearanceLevel.TOP_SECRET
        return ClearanceLevel.INTERNAL
