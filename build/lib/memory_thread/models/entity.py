from typing import Dict, Any, Optional
from uuid import UUID, uuid4
from datetime import datetime
from pydantic import BaseModel, Field

class Entity(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    namespace: str = "user"
    entity_type: str
    name: str
    attributes: Dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)
    merged_into: Optional[UUID] = None

    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat(),
            UUID: lambda v: str(v)
        }

class MergeProposal(BaseModel):
    source_entity: Entity
    target_entity: Entity
    confidence: float
    reason: str
    timestamp: datetime = Field(default_factory=datetime.now)

class EntityMergeLog(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    source_entity_id: UUID
    target_entity_id: UUID
    confidence: float
    reason: str
    timestamp: datetime = Field(default_factory=datetime.now)
