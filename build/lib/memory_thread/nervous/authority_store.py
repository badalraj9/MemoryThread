
import json
import os
import uuid
from datetime import datetime
from typing import List, Optional, Dict
from dataclasses import dataclass, field

DEFAULT_AUTH_STORE = os.path.expanduser("~/.mt/authority_grants.jsonl")

@dataclass
class AuthorityGrant:
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    granter_id: str = ""
    granter_role: str = ""
    target_role: str = ""  # Role being granted power
    target_domain: str = "" # Domain scope
    score: float = 0.5
    active: bool = True

    def to_json(self) -> str:
        return json.dumps({
            "id": self.id,
            "timestamp": self.timestamp,
            "granter": {"id": self.granter_id, "role": self.granter_role},
            "target_role": self.target_role,
            "domain": self.target_domain,
            "score": self.score,
            "active": self.active
        })

class AuthorityStore:
    """
    Persistent store for dynamic authority grants.
    """
    def __init__(self, file_path: str = DEFAULT_AUTH_STORE):
        self.file_path = file_path
        self._ensure_dir()
        self._cache: List[Dict] = []
        self.reload()

    def _ensure_dir(self):
        directory = os.path.dirname(self.file_path)
        if not os.path.exists(directory):
            try:
                os.makedirs(directory, exist_ok=True)
            except OSError:
                self.file_path = "authority_grants.jsonl"

    def reload(self):
        """Load grants into memory cache."""
        self._cache = []
        if not os.path.exists(self.file_path):
            return

        try:
            with open(self.file_path, 'r', encoding='utf-8') as f:
                for line in f:
                    try:
                        self._cache.append(json.loads(line))
                    except: continue
        except Exception:
            pass

    def add_grant(self, grant: AuthorityGrant):
        """Persist a new grant."""
        try:
            with open(self.file_path, 'a', encoding='utf-8') as f:
                f.write(grant.to_json() + "\n")
            self._cache.append(json.loads(grant.to_json()))
        except Exception as e:
            print(f"Failed to save grant: {e}")

    def revoke(self, target_role: str, domain: str, revoker_role: str):
        """
        Soft-revoke a grant (mark inactive).
        Requires appending a new 'revocation' record effectively.
        In this append-only log, we treat a new entry with active=False as revocation.
        """
        # We don't overwrite the file (append-only ledger principle).
        # We append a record that effectively cancels previous ones.
        grant = AuthorityGrant(
            granter_role=revoker_role,
            granter_id="revocation",
            target_role=target_role,
            target_domain=domain,
            score=0.0,
            active=False
        )
        self.add_grant(grant)

    def get_score(self, role: str, domain: str) -> Optional[float]:
        """
        Get the *latest* active grant score for a Role+Domain.
        """
        # Scan from newest to oldest
        for entry in reversed(self._cache):
            if entry['target_role'] == role:
                # Check Domain match (exact or wildcard)
                entry_domain = entry['domain']
                if entry_domain == "*" or entry_domain == domain:
                    if entry['active']:
                        return entry['score']
                    else:
                        # If latest entry is inactive/revoked, stop and return None (fallback to matrix)
                        # Or return 0.0?
                        # Design decision: Revocation means "remove dynamic grant",
                        # falling back to hardcoded matrix?
                        # Or explicit 0.0 override?
                        # Let's say explicit 0.0 override to allow 'blocking'.
                        return 0.0
        return None

# Singleton
authority_store = AuthorityStore()
