
"""
Secure Memory Client Wrapper.

This wrapper injects the Enterprise Firewall layer (AccessControlService)
transparently around the core SDK MemoryClient.
"""
from typing import Optional, List, Dict, Any, Union
import uuid
import json

from memory_thread.sdk import MemoryClient, RecallResult, Memory
from memory_thread.nervous.access_control import AccessControlService, UserContext, ClearanceLevel

class SecureMemoryClient:
    """
    Enterprise-grade wrapper for MemoryClient.
    Enforces RBAC, Clearance, and Truth Authority.
    """

    def __init__(self, user_id: str, role: str):
        self.user = AccessControlService.create_context(user_id, role)
        # We initialize the core SDK without a specific namespace initially,
        # or we could manage multiple clients. For simplicity, we'll use a
        # generic client and override namespaces per call if needed,
        # but the SDK is usually initialized with one.
        #
        # STRATEGY: The core SDK is namespace-bound.
        # To support cross-namespace (Federated) search, we might need
        # a slightly different approach or rely on the SDK's ability to search global if namespace is None?
        # Looking at SDK code: recall() takes a query and filters by namespace if set.
        # If we want cross-namespace, we might need a client with namespace="default" or None if supported.
        # Assuming for this prototype we are operating in a multi-tenant DB where we can query broadly.

        self._core_client = MemoryClient(namespace="default", use_db=True)

        # Monkey-patching or configuration might be needed if SDK strictly filters.
        # For now, we will rely on the fact that we can store the 'target namespace'
        # in the metadata and filter manually if the core SDK returns everything,
        # OR we instantiate distinct core clients for writes.

    @property
    def role(self):
        return self.user.role

    @property
    def clearance(self):
        return self.user.clearance.name

    def remember(self, content: str, namespace: str = "public",
                 memory_type: str = "fact") -> Optional[uuid.UUID]:
        """
        Secure Remember.
        Calculates authority and checks permissions before writing.
        """
        # 1. Check Write Permissions & Get Authority
        authority_score = AccessControlService.calculate_write_authority(self.user, namespace)

        if authority_score == 0.0:
            # Denied
            return None

        # 2. Configure the Core Client for this specific namespace
        # (This is a lightweight operation in the SDK usually)
        self._core_client.namespace = namespace

        # 3. Inject Metadata (Clearance Level)
        # The Core SDK's `remember` doesn't strictly take a metadata dict in the signature
        # presented earlier (it takes specific args).
        # However, looking at the code, it calls `tms.create_event` with a `delta`.
        # We can't easily inject arbitrary metadata into the standard `remember` without
        # changing the SDK or overloading `content` or using a lower-level call.
        #
        # TRICK: We will prepend a [HEADER] to the content or rely on the fact
        # that we are simulating the firewall.
        # BETTER TRICK: Use the `memory_type` field if it allows free text,
        # or just assume the namespace implies the clearance for this prototype.
        #
        # Let's assume Namespace -> Clearance Mapping is enforced by the Reader.
        # e.g. "finance_secret" namespace implies SECRET clearance.

        # 4. Call Core
        return self._core_client.remember(
            content=content,
            source=f"agent:{self.user.role}", # Audit trail
            confidence=1.0, # User is confident
            authority=authority_score, # The calculated firewall score
            memory_type=memory_type
        )

    def recall(self, query: str, target_namespaces: List[str] = None) -> RecallResult:
        """
        Secure Recall.
        Queries memory and REDACTS results the user shouldn't see.
        """
        if target_namespaces is None:
            # Default to all namespaces this user can read
            target_namespaces = self.user.domains

        # 1. Aggregate results from allowed namespaces
        # (Since SDK is namespace-partitioned usually, we might need to loop)
        all_memories = []

        for ns in target_namespaces:
            # Firewall Check: Can user read this namespace?
            if not AccessControlService.can_read(self.user, ns):
                continue

            self._core_client.namespace = ns
            result = self._core_client.recall(query, top_k=5) # Get top 5 per namespace

            for mem in result.memories:
                # Firewall Check: Clearance Level
                # (In this prototype, we map namespace to clearance)
                mem_clearance = self._get_namespace_clearance(ns)

                if AccessControlService.can_read(self.user, ns, mem_clearance):
                    # Tag it so UI knows where it came from
                    mem.source = f"{ns} (Auth: {mem.authority:.2f})"
                    all_memories.append(mem)
                else:
                    # Redacted entry (optional, usually just hide)
                    pass

        # 2. Re-rank/Sort combined results by Truth Score
        all_memories.sort(key=lambda m: m.truth_score, reverse=True)

        return RecallResult(
            memories=all_memories[:10], # Top 10 global
            query=query,
            total_found=len(all_memories)
        )

    def chat(self, user_message: str, system_prompt: Optional[str] = None, use_local: bool = True) -> str:
        """
        Secure Chat.
        Injects ONLY authorized context into the LLM.
        """
        # 1. Secure Recall
        # We search across all namespaces the user has access to
        recall_res = self.recall(user_message)

        # 2. Build Context manually (since we bypassed SDK's internal recall)
        context_str = recall_res.to_context(max_chars=3000)

        # 3. Construct Prompt
        full_prompt = f"""{system_prompt or 'You are a helpful assistant.'}

SECURITY CONTEXT:
User Role: {self.user.role}
Clearance: {self.user.clearance.name}

SECURE MEMORY CONTEXT (Only authorized facts):
{context_str}

User: {user_message}
Assistant:"""

        # 4. Use Core SDK's generator (bypassing its internal chat logic to use our prompt)
        if use_local:
            return self._core_client._generate_local(full_prompt)
        else:
            return self._core_client._generate_cloud(full_prompt)

    def _get_namespace_clearance(self, namespace: str) -> int:
        """Helper to map namespace to required clearance."""
        if "public" in namespace: return ClearanceLevel.PUBLIC
        if "team" in namespace: return ClearanceLevel.INTERNAL
        if "tech" in namespace: return ClearanceLevel.CONFIDENTIAL
        if "research" in namespace: return ClearanceLevel.SECRET
        if "secret" in namespace: return ClearanceLevel.TOP_SECRET
        return ClearanceLevel.INTERNAL # Default

    # --- PROXY METHODS (Pass-through) ---
    def clear(self):
        # Only allowed for Admin/Exec in real life
        if self.user.role == "executive":
            self._core_client.clear()
        else:
            print(f"Access Denied: {self.user.role} cannot clear DB.")
