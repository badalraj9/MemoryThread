from pydantic import BaseModel, Field
from typing import List, Dict, Optional, Any
from enum import Enum
from datetime import datetime
import uuid


class ActorEnum(str, Enum):
    USER = "USER"
    AGENT = "AGENT"
    SYSTEM = "SYSTEM"


class ActionEnum(str, Enum):
    PLANT = "PLANT"
    ADD = "ADD"
    REMOVE = "REMOVE"
    UPDATE = "UPDATE"
    OBSERVE = "OBSERVE"
    INFER = "INFER"
    LINK = "LINK"
    UNLINK = "UNLINK"
    MERGE = "MERGE"


class TruthVector(BaseModel):
    confidence: float = Field(..., ge=0.0, le=1.0)
    authority: float = Field(..., ge=0.0, le=1.0)
    freshness: float = Field(..., ge=0.0, le=1.0)
    corroboration: float = Field(..., ge=0.0)  # Can be > 1.0 (log scale later)

    @property
    def truth_score(self) -> float:
        """Compute overall truth score by delegating to TruthVectorService."""
        from memory_thread.services.tms_service import TruthVectorService

        return TruthVectorService.calculate_score(self)


class Event(BaseModel):
    id: uuid.UUID = Field(default_factory=uuid.uuid4)
    namespace: str = "user"
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    actor: ActorEnum
    action: ActionEnum
    object_id: uuid.UUID
    delta: Dict[str, Any]
    antecedents: List[uuid.UUID] = []
    truth_vector: TruthVector
    thread_id: Optional[uuid.UUID] = None


class EntityState(BaseModel):
    entity_id: uuid.UUID
    namespace: str
    current_value: Dict[str, Any]
    truth_vector: TruthVector
    version: int = 0
    last_event_id: uuid.UUID
    updated_at: datetime = Field(default_factory=datetime.utcnow)
