
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
from memory_thread.nervous.authority_store import authority_store, AuthorityGrant

class Grade(IntEnum):
    E_CLASS = 0   # Public / Guest
    C_CLASS = 1   # Internal / Employee
    B_CLASS = 2   # Confidential / Developer
    A_CLASS = 3   # Secret / Researcher
    S_CLASS = 4   # Top Secret / Executive
    SSS_CLASS = 5 # Godfather / Root

    def __str__(self):
        return self.name

@dataclass
class UserContext:
    user_id: str
    role: str
    grade: Grade
    domains: List[str]

    @property
    def clearance(self):
        return self.grade # Alias for backward compatibility

class AccessControlService:
    """
    The Single Source of Truth for Permissions and Authority.
    Hardened for Pentagon-style Grade System.
    """

    # --- POLICY DEFINITIONS ---

    # Map Roles to Default Clearance Grades
    ROLE_GRADES = {
        "guest": Grade.E_CLASS,
        "employee": Grade.C_CLASS,
        "developer": Grade.B_CLASS,
        "researcher": Grade.A_CLASS,
        "executive": Grade.S_CLASS,
        "godfather": Grade.SSS_CLASS # Hidden Role
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
        "godfather": {
            "read": ["*"],
            "write": ["*"]
        }
    }

    # Authority Scoring Matrix: (Role, Domain) -> Score
    AUTHORITY_MATRIX = {
        ("godfather", "*"): 1.0,
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
        if role == "root": role = "godfather" # Alias

        if role not in cls.ROLE_GRADES:
            role = "guest"

        return UserContext(
            user_id=user_id,
            role=role,
            grade=cls.ROLE_GRADES[role],
            domains=cls.ROLE_DOMAINS[role]["read"]
        )

    @classmethod
    def calculate_write_authority(cls, user: UserContext, target_domain: str) -> float:
        """
        Determines the Truth Score (Authority) for a write operation.
        Returns 0.0 if write is denied.
        """
        # 1. Check Dynamic Grants (Layer III) - Grants Override Permissions
        dynamic_score = authority_store.get_score(user.role, target_domain)
        if dynamic_score is not None:
            return dynamic_score

        # 2. Check Write Permission (Static)
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

        # 3. Calculate Static Score
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
    def grant_authority(cls, granter: UserContext, target_role: str, domain: str, score: float) -> bool:
        """
        Dynamic Authority Grant (Governance).
        Granter must have equal or higher authority in that domain to grant it.
        """
        # 1. Check Granter's Power
        granter_auth = cls.calculate_write_authority(granter, domain)
        if granter_auth < score:
            ledger.log(AuditEvent(
                action_type="GRANT_DENIED",
                actor_id=granter.user_id,
                role=granter.role,
                target=domain,
                details={"reason": "insufficient_authority", "yours": granter_auth, "requested": score}
            ))
            return False

        # 2. Execute Grant
        grant = AuthorityGrant(
            granter_id=granter.user_id,
            granter_role=granter.role,
            target_role=target_role.lower(),
            target_domain=domain,
            score=score
        )
        authority_store.add_grant(grant)

        # 3. Audit
        ledger.log(AuditEvent(
            action_type="AUTHORITY_GRANT",
            actor_id=granter.user_id,
            role=granter.role,
            target=f"{target_role}:{domain}",
            details={"score": score}
        ))
        return True

    @classmethod
    def revoke_authority(cls, revoker: UserContext, target_role: str, domain: str) -> bool:
        """
        Dynamic Revocation.
        """
        # 1. Check Revoker's Power (Must be Admin/Exec or original granter ideally, simplified here)
        if revoker.role not in ["executive", "godfather"]:
             ledger.log(AuditEvent(
                action_type="REVOKE_DENIED",
                actor_id=revoker.user_id,
                role=revoker.role,
                target=domain,
                details={"reason": "requires_exec_or_godfather"}
            ))
             return False

        # 2. Execute Revoke
        authority_store.revoke(target_role.lower(), domain, revoker.role)

        # 3. Audit
        ledger.log(AuditEvent(
            action_type="AUTHORITY_REVOKE",
            actor_id=revoker.user_id,
            role=revoker.role,
            target=f"{target_role}:{domain}"
        ))
        return True

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
    def _get_domain_clearance(cls, domain: str) -> Grade:
        if "public" in domain: return Grade.E_CLASS
        if "team" in domain: return Grade.C_CLASS
        if "tech" in domain: return Grade.B_CLASS
        if "research" in domain: return Grade.A_CLASS
        if "secret" in domain: return Grade.S_CLASS
        return Grade.C_CLASS

    # --- SUDO COMMANDS (Top-Down RBAC) ---
    
    # Role alias mapping for CLI
    ROLE_ALIASES = {
        "root": "godfather",
        "admin": "executive",
        "engineer": "developer",
        "employee": "employee",
        "guest": "guest",
    }
    
    @classmethod
    def sudo_enable_role(
        cls, 
        granter: UserContext, 
        target_role: str, 
        target_user: str
    ) -> Dict[str, Any]:
        """
        Enable a role for a user (top-down hierarchy).
        
        Granter must have higher grade than target role.
        
        Args:
            granter: The user performing the grant
            target_role: Role to grant (guest, employee, engineer, admin, root)
            target_user: User receiving the role
            
        Returns:
            {success, message, new_role}
        """
        # Normalize role
        target_role = target_role.lower()
        mapped_role = cls.ROLE_ALIASES.get(target_role, target_role)
        
        if mapped_role not in cls.ROLE_GRADES:
            return {"success": False, "message": f"Unknown role: {target_role}"}
        
        target_grade = cls.ROLE_GRADES[mapped_role]
        
        # Hierarchy check: granter must be STRICTLY higher
        if granter.grade <= target_grade:
            ledger.log(AuditEvent(
                action_type="SUDO_ENABLE_DENIED",
                actor_id=granter.user_id,
                role=granter.role,
                target=f"{target_user}:{target_role}",
                details={"reason": "hierarchy_violation", "granter_grade": str(granter.grade), "target_grade": str(target_grade)}
            ))
            return {
                "success": False,
                "message": f"Cannot grant {target_role} - requires higher rank than {target_role}"
            }
        
        # Log the grant
        ledger.log(AuditEvent(
            action_type="SUDO_ENABLE",
            actor_id=granter.user_id,
            role=granter.role,
            target=f"{target_user}:{target_role}",
            details={"granted_role": mapped_role}
        ))
        
        # In production, this would update a user-role mapping in the database
        # For now, we just return success
        return {
            "success": True,
            "message": f"Granted {target_role} to {target_user}",
            "new_role": mapped_role,
            "new_grade": str(target_grade)
        }
    
    @classmethod
    def sudo_disable_role(
        cls,
        revoker: UserContext,
        target_role: str,
        target_user: str
    ) -> Dict[str, Any]:
        """
        Disable a role for a user.
        
        Revoker must have higher grade than target role.
        """
        target_role = target_role.lower()
        mapped_role = cls.ROLE_ALIASES.get(target_role, target_role)
        
        if mapped_role not in cls.ROLE_GRADES:
            return {"success": False, "message": f"Unknown role: {target_role}"}
        
        target_grade = cls.ROLE_GRADES[mapped_role]
        
        if revoker.grade <= target_grade:
            return {
                "success": False,
                "message": f"Cannot revoke {target_role} - requires higher rank"
            }
        
        ledger.log(AuditEvent(
            action_type="SUDO_DISABLE",
            actor_id=revoker.user_id,
            role=revoker.role,
            target=f"{target_user}:{target_role}"
        ))
        
        return {
            "success": True,
            "message": f"Revoked {target_role} from {target_user}"
        }

