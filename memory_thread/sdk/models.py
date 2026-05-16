import uuid
from datetime import datetime
from typing import Optional, List, Dict, Any
from dataclasses import dataclass, field


@dataclass
class ConnectionConfig:
    """Parsed connection configuration from MT_URL."""

    host: str
    port: int
    namespace: str
    api_key: Optional[str] = None
    use_db: bool = True


@dataclass
class Memory:
    """A single memory with truth metadata."""

    content: str
    entity_id: uuid.UUID
    truth_score: float
    confidence: float
    authority: float
    freshness: float
    corroboration: int
    timestamp: datetime
    source: str
    memory_type: str = "fact"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "content": self.content,
            "entity_id": str(self.entity_id),
            "truth_score": self.truth_score,
            "confidence": self.confidence,
            "freshness": self.freshness,
            "source": self.source,
            "timestamp": self.timestamp.isoformat(),
        }


@dataclass
class RecallResult:
    """Result of a recall operation."""

    memories: List[Memory]
    query: str
    total_found: int

    def to_context(self, max_chars: int = 2000) -> str:
        if not self.memories:
            return "No relevant memories found."

        lines = ["Relevant memories:"]
        char_count = len(lines[0])

        for i, mem in enumerate(self.memories, 1):
            line = f"{i}. {mem.content}"
            if char_count + len(line) > max_chars:
                break
            lines.append(line)
            char_count += len(line)

        return "\n".join(lines)

    def format(self) -> str:
        return self.to_context()


@dataclass
class WritePathMetric:
    calls: int = 0
    total_ms: float = 0.0
    max_ms: float = 0.0
