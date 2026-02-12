import json
import logging
from datetime import datetime
from typing import Dict, Any, Optional
from dataclasses import dataclass, field
import uuid
import os

# We treat the audit ledger as a separate system component
# In a real enterprise setup, this would write to a WORM (Write Once Read Many) storage
# For this implementation, we will use a dedicated JSONL file or a separate DB table if available.
# To allow portability without complex setup, we default to a file-based ledger in ~/.mt/audit/

DEFAULT_AUDIT_PATH = os.path.expanduser("~/.mt/audit_ledger.jsonl")

@dataclass
class AuditEvent:
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    action_type: str = "GENERIC"  # ACCESS_DENIED, OVERRIDE, REDACTION, PRUNING
    actor_id: str = "system"
    role: str = "system"
    target: str = ""
    details: Dict[str, Any] = field(default_factory=dict)

    def to_json(self) -> str:
        return json.dumps({
            "id": self.id,
            "timestamp": self.timestamp,
            "type": self.action_type,
            "actor": {
                "id": self.actor_id,
                "role": self.role
            },
            "target": self.target,
            "details": self.details
        })

class AuditLedger:
    def __init__(self, file_path: str = DEFAULT_AUDIT_PATH):
        self.file_path = file_path
        self._ensure_dir()

    def _ensure_dir(self):
        directory = os.path.dirname(self.file_path)
        if not os.path.exists(directory):
            try:
                os.makedirs(directory, exist_ok=True)
            except OSError:
                # Fallback to local dir if permission denied
                self.file_path = "audit_ledger.jsonl"

    def log(self, event: AuditEvent):
        """Append an event to the ledger."""
        try:
            with open(self.file_path, 'a', encoding='utf-8') as f:
                f.write(event.to_json() + "\n")
        except Exception as e:
            # Fallback logging if file write fails - Audit must never fail silently
            logging.critical(f"AUDIT WRITE FAILED: {event.to_json()} - Error: {e}")

    def query(self, actor_id: Optional[str] = None, limit: int = 100) -> list:
        """
        Query audit logs (Reverse chronological).
        Protected method - should only be exposed to Root/Superuser.
        """
        results = []
        try:
            if not os.path.exists(self.file_path):
                return []

            # Read from end (efficient for tail) would be better, but for now scan whole
            with open(self.file_path, 'r', encoding='utf-8') as f:
                lines = f.readlines()

            for line in reversed(lines):
                if len(results) >= limit:
                    break
                try:
                    data = json.loads(line)
                    if actor_id:
                        if data['actor']['id'] != actor_id:
                            continue
                    results.append(data)
                except:
                    continue
        except Exception:
            return []

        return results

# Singleton instance
ledger = AuditLedger()
