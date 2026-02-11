from __future__ import annotations
from typing import Optional, List, Literal
from pydantic import BaseModel, Field
from datetime import datetime
import uuid

MemoryType = Literal["identity", "preference", "event", "fact", "task", "belief", "timeline", "other"]
MemorySource = Literal["user", "system", "model"]

class MemoryMetadata(BaseModel):
    source: MemorySource = "user"
    negation: bool = False
    emotion: Optional[str] = None
    deadline: Optional[datetime] = None

class MemoryObject(BaseModel):
    id: uuid.UUID = Field(default_factory=uuid.uuid4)
    content: str
    memory_type: MemoryType
    importance: float = 0.5
    entities: List[str] = Field(default_factory=list)
    topics: List[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    last_accessed: datetime = Field(default_factory=datetime.utcnow)
    relations: List[uuid.UUID] = Field(default_factory=list)
    metadata: MemoryMetadata = Field(default_factory=MemoryMetadata)
    domain: Optional[str] = None
    current_value: Optional[str] = None
    history: Optional[List[dict]] = None
    embedding: Optional[List[float]] = None
