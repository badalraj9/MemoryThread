"""
Client Registry - API Consumer Management for Memory Thread.

Tracks all systems connecting to MT via API with RBAC enforcement.
"""
import os
import json
import uuid
import hashlib
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Any, Optional
from dataclasses import dataclass, field, asdict

from memory_thread.utils.logger import get_logger

log = get_logger(__name__)

# Registry storage
REGISTRY_PATH = Path(os.path.expanduser("~/.mt/clients.json"))


@dataclass
class APIClient:
    """Registered API client."""
    client_id: str
    name: str
    role: str
    authority: float
    api_key_hash: str
    domains: List[str] = field(default_factory=list)
    created_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    last_access: Optional[str] = None
    access_count: int = 0
    active: bool = True
    
    def to_dict(self) -> Dict:
        return asdict(self)


class ClientRegistry:
    """
    Manages API client registrations.
    
    Features:
    - Register clients with role and authority
    - Generate API keys
    - Authenticate requests
    - Track access
    """
    
    # Role hierarchy (higher = more access)
    ROLE_HIERARCHY = {
        "root": 5,
        "godfather": 5,  # SSS-CLASS (same as root)
        "admin": 4,
        "executive": 4,  # S-CLASS (same as admin)
        "researcher": 3, # A-CLASS
        "engineer": 3,
        "developer": 3,  # B-CLASS (same as engineer)
        "employee": 2,
        "guest": 1,
        "agent": 2,  # Same as employee
    }
    
    def __init__(self):
        self._clients: Dict[str, APIClient] = {}
        self._load()
    
    def _ensure_storage(self):
        REGISTRY_PATH.parent.mkdir(parents=True, exist_ok=True)
    
    def _load(self):
        """Load registry from disk."""
        if REGISTRY_PATH.exists():
            try:
                with open(REGISTRY_PATH, 'r') as f:
                    data = json.load(f)
                    for client_id, client_data in data.items():
                        self._clients[client_id] = APIClient(**client_data)
            except Exception as e:
                log.warning(f"Failed to load client registry: {e}")
    
    def _save(self):
        """Persist registry to disk."""
        self._ensure_storage()
        try:
            data = {cid: c.to_dict() for cid, c in self._clients.items()}
            with open(REGISTRY_PATH, 'w') as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            log.error(f"Failed to save client registry: {e}")
    
    def _hash_key(self, api_key: str) -> str:
        """Hash API key for storage."""
        return hashlib.sha256(api_key.encode()).hexdigest()
    
    def _generate_api_key(self, client_id: str) -> str:
        """Generate unique API key."""
        raw = f"{client_id}-{uuid.uuid4().hex}-{datetime.utcnow().timestamp()}"
        return f"mt_{hashlib.sha256(raw.encode()).hexdigest()[:32]}"
    
    def register(
        self,
        name: str,
        role: str = "agent",
        authority: float = 0.5,
        domains: List[str] = None,
        registrar_role: str = "admin"
    ) -> Dict[str, Any]:
        """
        Register a new API client.
        
        Args:
            name: Client name
            role: Client role (agent, engineer, etc.)
            authority: Truth authority score (0.0-1.0)
            domains: Allowed namespaces
            registrar_role: Role of the person registering (for hierarchy check)
            
        Returns:
            {client_id, api_key, role, authority}
            
        Note: API key is returned ONLY at registration time.
        """
        # Hierarchy check: registrar must be >= client role
        registrar_level = self.ROLE_HIERARCHY.get(registrar_role, 0)
        client_level = self.ROLE_HIERARCHY.get(role, 0)
        
        if registrar_level < client_level:
            raise PermissionError(f"Cannot register {role} client - requires higher rank")
        
        client_id = f"client_{uuid.uuid4().hex[:8]}"
        api_key = self._generate_api_key(client_id)
        
        client = APIClient(
            client_id=client_id,
            name=name,
            role=role,
            authority=min(1.0, max(0.0, authority)),
            api_key_hash=self._hash_key(api_key),
            domains=domains or ["public"],
        )
        
        self._clients[client_id] = client
        self._save()
        
        log.info(f"Registered client: {name} ({role}, authority={authority})")
        
        return {
            "client_id": client_id,
            "api_key": api_key,  # Only returned once!
            "name": name,
            "role": role,
            "authority": authority,
            "domains": client.domains,
        }
    
    def authenticate(self, api_key: str) -> Optional[APIClient]:
        """
        Authenticate an API key.
        
        Returns:
            APIClient if valid, None otherwise
        """
        key_hash = self._hash_key(api_key)
        
        for client in self._clients.values():
            if client.api_key_hash == key_hash and client.active:
                # Update access tracking
                client.last_access = datetime.utcnow().isoformat()
                client.access_count += 1
                self._save()
                return client
        
        return None
    
    def get_client(self, client_id: str) -> Optional[APIClient]:
        """Get client by ID."""
        return self._clients.get(client_id)
    
    def list_clients(self, include_inactive: bool = False) -> List[Dict]:
        """List all registered clients."""
        clients = []
        for client in self._clients.values():
            if include_inactive or client.active:
                info = client.to_dict()
                del info["api_key_hash"]  # Don't expose hash
                clients.append(info)
        return clients
    
    def deactivate(self, client_id: str, deactivator_role: str = "admin") -> bool:
        """Deactivate a client."""
        client = self._clients.get(client_id)
        if not client:
            return False
        
        # Hierarchy check
        deactivator_level = self.ROLE_HIERARCHY.get(deactivator_role, 0)
        client_level = self.ROLE_HIERARCHY.get(client.role, 0)
        
        if deactivator_level <= client_level:
            raise PermissionError(f"Cannot deactivate {client.role} client - requires higher rank")
        
        client.active = False
        self._save()
        log.info(f"Deactivated client: {client.name} ({client_id})")
        return True
    
    def reactivate(self, client_id: str) -> bool:
        """Reactivate a client."""
        client = self._clients.get(client_id)
        if not client:
            return False
        
        client.active = True
        self._save()
        return True
    
    def rotate_key(self, client_id: str, rotator_role: str = "admin") -> Optional[str]:
        """
        Generate new API key for client.
        
        Returns:
            New API key (only returned once)
        """
        client = self._clients.get(client_id)
        if not client:
            return None
        
        # Hierarchy check
        rotator_level = self.ROLE_HIERARCHY.get(rotator_role, 0)
        client_level = self.ROLE_HIERARCHY.get(client.role, 0)
        
        if rotator_level < client_level:
            raise PermissionError(f"Cannot rotate key for {client.role} client")
        
        new_key = self._generate_api_key(client_id)
        client.api_key_hash = self._hash_key(new_key)
        self._save()
        
        log.info(f"Rotated API key for client: {client.name}")
        return new_key
    
    def get_stats(self) -> Dict[str, Any]:
        """Get registry statistics."""
        active = sum(1 for c in self._clients.values() if c.active)
        by_role = {}
        for c in self._clients.values():
            if c.active:
                by_role[c.role] = by_role.get(c.role, 0) + 1
        
        return {
            "total_clients": len(self._clients),
            "active_clients": active,
            "inactive_clients": len(self._clients) - active,
            "by_role": by_role,
        }


# Singleton
client_registry = ClientRegistry()
