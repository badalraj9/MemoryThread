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

class TruthVector(BaseModel):
    confidence: float = Field(..., ge=0.0, le=1.0)
    authority: float = Field(..., ge=0.0, le=1.0)
    freshness: float = Field(..., ge=0.0, le=1.0)
    corroboration: float = Field(..., ge=0.0) # Can be > 1.0 (log scale later)

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

class EntityState(BaseModel):
    entity_id: uuid.UUID
    namespace: str
    current_value: Dict[str, Any]
    truth_vector: TruthVector
    version: int = 0
    last_event_id: uuid.UUID
    updated_at: datetime = Field(default_factory=datetime.utcnow)
