
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
        "executive": ClearanceLevel.TOP_SECRET
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
        }
    }

    # Authority Scoring Matrix: (Role, Domain) -> Score
    AUTHORITY_MATRIX = {
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
            domains=cls.ROLE_DOMAINS[role]["read"] # Simplification for context
        )

    @classmethod
    def calculate_write_authority(cls, user: UserContext, target_namespace: str) -> float:
        """
        Determines the Truth Score (Authority) for a write operation.
        Returns 0.0 if write is denied.
        """
        # 1. Check Write Permission
        allowed_writes = cls.ROLE_DOMAINS[user.role]["write"]
        if "*" not in allowed_writes and target_namespace not in allowed_writes:
            return 0.0 # Denied

        # 2. Calculate Score
        # Check specific rule first
        score = cls.AUTHORITY_MATRIX.get((user.role, target_namespace))
        if score is None:
            # Check wildcard rule
            score = cls.AUTHORITY_MATRIX.get((user.role, "*"))

        if score is None:
            # Fallback default authority
            score = 0.5

        return score

    @classmethod
    def can_read(cls, user: UserContext, memory_namespace: str, memory_clearance: int = 0) -> bool:
        """
        The Firewall Check.
        Returns True if the user is allowed to see this memory.
        """
        # 1. Domain Check
        allowed_reads = cls.ROLE_DOMAINS[user.role]["read"]
        if "*" not in allowed_reads and memory_namespace not in allowed_reads:
            return False

        # 2. Clearance Check
        # If memory has higher clearance requirement than user possesses -> Block
        if memory_clearance > user.clearance:
            return False

        return True
