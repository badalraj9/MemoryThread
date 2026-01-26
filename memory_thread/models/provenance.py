from dataclasses import dataclass, field
from typing import Optional, Dict
from datetime import datetime
import uuid

@dataclass
class Actor:
    user_id: str
    role: str
    agent_id: Optional[str] = None

    def to_dict(self) -> Dict:
        return {
            "user_id": self.user_id,
            "role": self.role,
            "agent_id": self.agent_id
        }

@dataclass
class Origin:
    client_id: str
    session_id: Optional[str] = None
    machine_id: Optional[str] = None

    def to_dict(self) -> Dict:
        return {
            "client_id": self.client_id,
            "session_id": self.session_id,
            "machine_id": self.machine_id
        }

@dataclass
class Scope:
    namespace: str
    domain: Optional[str] = None
    project_id: Optional[str] = None

    def to_dict(self) -> Dict:
        return {
            "namespace": self.namespace,
            "domain": self.domain,
            "project_id": self.project_id
        }

@dataclass
class ProvenanceEnvelope:
    """
    The immutable Identity & Namespace Envelope.
    Must be embedded in every memory event payload.
    """
    event_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    actor: Actor = None
    origin: Origin = None
    scope: Scope = None

    def to_dict(self) -> Dict:
        return {
            "event_id": self.event_id,
            "timestamp": self.timestamp,
            "actor": self.actor.to_dict() if self.actor else None,
            "origin": self.origin.to_dict() if self.origin else None,
            "scope": self.scope.to_dict() if self.scope else None
        }
