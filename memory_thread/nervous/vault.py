import os
import hashlib
import uuid
import json
from typing import Optional, Tuple

VAULT_PATH = os.path.expanduser("~/.mt/vault.json")

class Vault:
    """
    Secure Credential Store.
    Manages PINs and the Nuclear Key for Godfather access.
    """
    def __init__(self):
        self._ensure_storage()
        self._cache = self._load()

    def _ensure_storage(self):
        directory = os.path.dirname(VAULT_PATH)
        if not os.path.exists(directory):
            try:
                os.makedirs(directory, exist_ok=True)
            except OSError:
                pass

    def _load(self) -> dict:
        if os.path.exists(VAULT_PATH):
            try:
                with open(VAULT_PATH, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except:
                pass
        return {}

    def _save(self):
        try:
            with open(VAULT_PATH, 'w', encoding='utf-8') as f:
                json.dump(self._cache, f, indent=2)
        except:
            pass

    def _hash(self, secret: str) -> str:
        return hashlib.sha256(secret.encode()).hexdigest()

    def get_or_create_godfather_key(self) -> str:
        """
        Generates the Nuclear Key if missing.
        Returns the PLAINTEXT key (only once/on request) for display.
        """
        if "godfather_hash" in self._cache:
            return "[HIDDEN - ALREADY SET]"

        # Generate new key
        key = f"MT-{uuid.uuid4().hex[:12].upper()}"
        self._cache["godfather_hash"] = self._hash(key)
        self._save()
        return key

    def verify_godfather(self, key_input: str) -> bool:
        """Checks against the Nuclear Key."""
        stored = self._cache.get("godfather_hash")
        if not stored: return False
        return self._hash(key_input) == stored

    def set_pin(self, username: str, pin: str):
        """Sets a simple PIN for a user."""
        self._cache[f"pin_{username}"] = self._hash(pin)
        self._save()

    def verify_pin(self, username: str, pin_input: str) -> bool:
        """Verifies user PIN."""
        stored = self._cache.get(f"pin_{username}")
        if not stored:
            # Default PIN for demo if not set: '0000'
            return pin_input == "0000"
        return self._hash(pin_input) == stored

# Singleton
vault = Vault()
