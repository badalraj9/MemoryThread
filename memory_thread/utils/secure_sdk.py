
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

    def remember(self, content: str, namespace: str = "public",
                 memory_type: str = "fact") -> Optional[uuid.UUID]:
        """
        Secure Remember with Provenance.
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

        # 3. Embed Envelope into Content (Payload Injection)
        # Strategy: We append a hidden metadata block or struct if SDK supported it.
        # Since SDK treats content as string, we will use a "Payload Injection" strategy
        # where we serialize the envelope into the string or utilize the SDK's ability
        # to store JSON if we were passing a dict.
        # However, `MemoryClient.remember` takes `content: str`.
        #
        # BETTER STRATEGY: The Core SDK actually creates an Event with a `delta`.
        # The `delta` usually contains `{"content": "..."}`.
        # We can't change the SDK `remember` signature.
        # BUT, looking at `MemoryClient.remember` implementation:
        # It takes `content`.
        # It creates a `delta={"content": content, ...}`.
        # It allows NO metadata injection via arguments.
        #
        # WORKAROUND: We will JSON-encode the content to include the envelope.
        # Users of SecureClient will need to decode it, OR we decode on recall.

        secure_payload = {
            "text": content,
            "_provenance": envelope.to_dict()
        }

        serialized_content = json.dumps(secure_payload)

        # 4. Call Core
        # We pass the serialized JSON as the "content".
        # The Core treats it as a string (safe).
        # Secure Recall will parse it back.

        event_id = self._core_client.remember(
            content=serialized_content,
            source=f"agent:{self.user.role}", # Legacy audit
            confidence=1.0,
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
