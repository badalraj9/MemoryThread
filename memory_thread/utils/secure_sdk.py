
"""
Secure Memory Client Wrapper.

This wrapper injects the Enterprise Firewall layer (AccessControlService)
transparently around the core SDK MemoryClient.

UPDATED: Enforces Provenance Envelope on every write.
"""
from typing import Optional, List, Dict, Any, Union
import uuid
import json
import datetime

from memory_thread.sdk import MemoryClient, RecallResult, Memory
from memory_thread.nervous.access_control import AccessControlService, UserContext
from memory_thread.models.provenance import ProvenanceEnvelope, Actor, Origin, Scope
from memory_thread.nervous.audit_ledger import ledger, AuditEvent

class SecureMemoryClient:
    """
    Enterprise-grade wrapper for MemoryClient.
    Enforces RBAC, Clearance, Truth Authority, and Provenance.
    """

    def __init__(self, user_id: str, role: str, client_id: str = "tui-client"):
        self.user = AccessControlService.create_context(user_id, role)
        self.origin = Origin(client_id=client_id, session_id=str(uuid.uuid4()))
        self._core_client = MemoryClient(namespace="default", use_db=True)

    @property
    def role(self):
        return self.user.role

    @property
    def clearance(self):
        return self.user.grade.name

    def ingest_fact(self, content: str, source_uri: str = "manual", namespace: str = "public") -> Optional[uuid.UUID]:
        """
        Class A Ingestion: Canonical Truth.
        - Must be raw content (no embeddings, no opinions).
        - Must be verifiable.
        """
        # DEBUG CHECK
        # print(f"DEBUG: ingest_fact called with {content}")
        # Prime Rule Checks
        if not content or not isinstance(content, str):
            raise ValueError("PRIME RULE VIOLATION: Fact content must be a non-empty string.")
        if len(content) > 100000:
             # Just a sanity check, large files are okay but memory limits exist
             pass

        # Check for Forbidden Patterns (Heuristic)
        if content.strip().startswith("[") and content.strip().endswith("]") and "," in content:
             # Rough check for vector/embedding dump
             # If it looks like a list of floats, reject.
             try:
                 possible_vec = json.loads(content)
                 if isinstance(possible_vec, list) and len(possible_vec) > 0 and isinstance(possible_vec[0], (float, int)):
                     raise ValueError("PRIME RULE VIOLATION: Embeddings cannot be stored as Truth.")
             except json.JSONDecodeError:
                 pass
             except ValueError as e:
                 raise e # Re-raise our own violation
             except Exception:
                 pass

        return self._internal_remember(
            content=content,
            namespace=namespace,
            memory_type="fact",
            confidence=1.0, # Facts are absolute
            source_uri=source_uri,
            provenance_extras={}
        )

    def record_belief(self, content: str, derived_from: List[uuid.UUID], confidence: float, namespace: str = "public") -> Optional[uuid.UUID]:
        """
        Class B Ingestion: Epistemic Artifact.
        - Must have provenance (derived_from).
        - Must have confidence.
        """
        # Prime Rule Checks
        if not derived_from or not isinstance(derived_from, list):
             raise ValueError("PRIME RULE VIOLATION: Beliefs must have explicit 'derived_from' provenance.")

        if confidence is None or not (0.0 <= confidence <= 1.0):
             raise ValueError("PRIME RULE VIOLATION: Beliefs must have a valid confidence score (0.0-1.0).")

        return self._internal_remember(
            content=content,
            namespace=namespace,
            memory_type="belief",
            confidence=confidence,
            source_uri=f"agent:{self.user.role}",
            provenance_extras={"derived_from": [str(uid) for uid in derived_from]}
        )

    def remember(self, content: str, namespace: str = "public",
                 memory_type: str = "fact", **kwargs) -> Optional[uuid.UUID]:
        """
        [DEPRECATED] Generic wrapper.
        Routes to specific methods or warns.
        """
        print(f"WARNING: 'remember()' is deprecated. Use 'ingest_fact' or 'record_belief'.")

        if memory_type == "fact":
            return self.ingest_fact(content, namespace=namespace)
        elif memory_type == "belief":
            derived = kwargs.get('derived_from', [])
            conf = kwargs.get('confidence', 0.5)
            if not derived:
                 # Soft violation for backward compat during migration?
                 # NO. Prime Rule is law.
                 raise ValueError("PRIME RULE VIOLATION: Cannot store belief without 'derived_from' via generic remember().")
            return self.record_belief(content, derived, conf, namespace)
        else:
            # Default to Fact if ambiguous but warn?
            # Safer to fail.
             raise ValueError(f"Unknown memory_type: {memory_type}")

    def _internal_remember(self, content: str, namespace: str, memory_type: str,
                           confidence: float, source_uri: str, provenance_extras: Dict) -> Optional[uuid.UUID]:
        """
        Internal Secure Persist Logic.
        """
        # 1. Check Write Permissions & Get Authority
        authority_score = AccessControlService.calculate_write_authority(self.user, namespace)

        if authority_score == 0.0:
            return None # Audit log handled in AccessControlService

        # 2. Construct Provenance Envelope
        envelope = ProvenanceEnvelope(
            actor=Actor(user_id=self.user.user_id, role=self.user.role),
            origin=self.origin,
            scope=Scope(namespace=namespace, domain=namespace) # Domain mapped to namespace for now
        )

        # Merge extras (like derived_from)
        env_dict = envelope.to_dict()
        env_dict.update(provenance_extras)

        # 3. Payload Injection
        secure_payload = {
            "text": content,
            "_provenance": env_dict
        }

        serialized_content = json.dumps(secure_payload)

        # 4. Call Core
        event_id = self._core_client.remember(
            content=serialized_content,
            source=source_uri,
            confidence=confidence,
            authority=authority_score,
            memory_type=memory_type
        )

        return event_id

    def recall(self, query: str, top_k: int = 5, target_namespaces: List[str] = None) -> RecallResult:
        """
        Secure Recall with Firewall Filtering.
        """
        if target_namespaces is None:
            # Default to all namespaces this user can read
            target_namespaces = self.user.domains

        all_memories = []

        # Calculate per-namespace limit to ensure we get enough candidates
        # We request top_k from each namespace to be safe

        for ns in target_namespaces:
            # Firewall Check: Can user read this namespace?
            # We create a dummy envelope for this high-level check
            dummy_env = {'_provenance': {'scope': {'namespace': ns}}}
            if not AccessControlService.can_read(self.user, dummy_env):
                continue

            self._core_client.namespace = ns
            result = self._core_client.recall(query, top_k=top_k)

            for mem in result.memories:
                # 1. Parse Provenance
                try:
                    payload = json.loads(mem.content)
                    if isinstance(payload, dict) and "_provenance" in payload:
                        # It's a secured memory
                        provenance = payload["_provenance"]
                        actual_text = payload["text"]
                    else:
                        # Legacy/Plain memory
                        provenance = None
                        actual_text = mem.content
                except json.JSONDecodeError:
                    provenance = None
                    actual_text = mem.content

                # 2. Construct Envelope for Firewall
                # If legacy, we assume the namespace of the query implies origin
                check_env = {"_provenance": provenance} if provenance else {"namespace": ns}

                # 3. Firewall Check
                if AccessControlService.can_read(self.user, check_env):
                    # Unpack content for the user
                    mem.content = actual_text

                    # Tag source
                    if provenance:
                        actor = provenance.get('actor', {})
                        mem.source = f"{actor.get('role', 'unknown')} (Auth: {mem.authority:.2f})"
                    else:
                        mem.source = f"{ns} (Legacy)"

                    all_memories.append(mem)
                else:
                    # Filtered out
                    pass

        # 2. Re-rank
        all_memories.sort(key=lambda m: m.truth_score, reverse=True)

        return RecallResult(
            memories=all_memories[:top_k],
            query=query,
            total_found=len(all_memories)
        )

    def get_related(self, entity_id: uuid.UUID, depth: int = 1) -> List[Dict]:
        """
        Delegated Graph Query.
        In a real secure system, we would filter these relations too.
        For this prototype, we allow structure exploration but redact details if needed.
        """
        # We need to access across all namespaces, or default to current user context?
        # Graph service is global usually.
        # We'll delegate to core client.
        return self._core_client.get_related(entity_id, depth)

    def __getattr__(self, name):
        """Delegate unknown methods to core client (e.g. get_stats, get_health)."""
        return getattr(self._core_client, name)

    def chat(self, user_message: str, system_prompt: Optional[str] = None, use_local: bool = True, smart_loop: bool = False) -> str:
        """
        Secure Chat with optional Smart Loop (Layer VI).
        """
        # 1. Secure Recall (Initial Pass)
        recall_res = self.recall(user_message, top_k=5)

        # Smart Loop: Reflection (Layer VI)
        if smart_loop and recall_res.total_found < 2:
            # If low context, ask LLM what else it needs
            reflection_prompt = f"""User: {user_message}
Current Context: {recall_res.to_context(max_chars=500)}
Task: Identify one specific search query to find missing info. Return ONLY the query."""

            if use_local:
                next_query = self._core_client._generate_local(reflection_prompt)
            else:
                next_query = self._core_client._generate_cloud(reflection_prompt)

            # Clean up query
            next_query = next_query.strip().replace('"', '')

            # Secondary Recall
            extra_res = self.recall(next_query, top_k=3)
            # Merge results (simple append for prototype)
            recall_res.memories.extend(extra_res.memories)

        # 2. Build Context
        context_str = recall_res.to_context(max_chars=3000)

        # 3. Construct Prompt
        full_prompt = f"""{system_prompt or 'You are a helpful assistant.'}

SECURITY CONTEXT:
User Role: {self.user.role}
Grade: {self.user.grade.name}

SECURE MEMORY CONTEXT (Only authorized facts):
{context_str}

User: {user_message}
Assistant:"""

        # 4. Core Generation
        if use_local:
            return self._core_client._generate_local(full_prompt)
        else:
            return self._core_client._generate_cloud(full_prompt)

    def _get_namespace_clearance(self, namespace: str) -> int:
        """Helper to map namespace to required Grade."""
        from memory_thread.nervous.access_control import Grade
        if "public" in namespace: return Grade.E_CLASS
        if "team" in namespace: return Grade.C_CLASS
        if "tech" in namespace: return Grade.B_CLASS
        if "research" in namespace: return Grade.A_CLASS
        if "secret" in namespace: return Grade.S_CLASS
        return Grade.C_CLASS

    # --- ADMIN CAPABILITY ---
    def audit_log(self, limit: int = 50) -> List[Dict]:
        """
        Root capability to view audit logs.
        """
        if self.user.role != "root":
            ledger.log(AuditEvent(
                action_type="ACCESS_DENIED",
                actor_id=self.user.user_id,
                role=self.user.role,
                target="audit_log",
                details={"reason": "requires_root"}
            ))
            return []

        return ledger.query(limit=limit)

    def clear(self):
        if self.user.role == "root":
            self._core_client.clear()
        else:
            print(f"Access Denied: Only ROOT can clear DB.")

    def grant(self, target_role: str, domain: str, score: float) -> bool:
        """Dynamic Authority Grant."""
        return AccessControlService.grant_authority(self.user, target_role, domain, score)

    def revoke(self, target_role: str, domain: str) -> bool:
        """Dynamic Revocation."""
        return AccessControlService.revoke_authority(self.user, target_role, domain)
