import os
import hashlib
import secrets
import json
from typing import Optional, Tuple

from cryptography.fernet import Fernet
from hashlib import sha256
import base64

VAULT_PATH = os.path.expanduser("~/.mt/vault.json")


def _get_fernet() -> Fernet:
    raw = os.environ.get("MT_SECRET_KEY")
    if not raw:
        raise RuntimeError("MT_SECRET_KEY environment variable must be set for encrypted vault")
    key = base64.urlsafe_b64encode(sha256(raw.encode()).digest())
    return Fernet(key)


class Vault:
    """
    Secure Credential Store.
    Manages PINs and the Nuclear Key for Godfather access.
    Provider credentials encrypted with Fernet (symmetric AES).
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
                with open(VAULT_PATH, "r", encoding="utf-8") as f:
                    return json.load(f)
            except json.JSONDecodeError as e:
                import logging

                logging.getLogger(__name__).warning(f"Vault file corrupted, starting fresh: {e}")
            except Exception as e:
                import logging

                logging.getLogger(__name__).error(f"Failed to load vault: {e}")
        return {}

    def _save(self):
        try:
            with open(VAULT_PATH, "w", encoding="utf-8") as f:
                json.dump(self._cache, f, indent=2)
        except Exception as e:
            import logging

            logging.getLogger(__name__).error(f"Failed to save vault: {e}")

    def _hash(self, secret: str) -> str:
        return hashlib.sha256(secret.encode()).hexdigest()

    def get_or_create_godfather_key(self) -> str:
        if "godfather_hash" in self._cache:
            return "[HIDDEN - ALREADY SET]"

        key = f"MT-{secrets.token_hex(16).upper()}"
        self._cache["godfather_hash"] = self._hash(key)
        self._save()
        return key

    def verify_godfather(self, key_input: str) -> bool:
        stored = self._cache.get("godfather_hash")
        if not stored:
            return False
        return self._hash(key_input) == stored

    def set_pin(self, username: str, pin: str):
        self._cache[f"pin_{username}"] = self._hash(pin)
        self._save()

    def verify_pin(self, username: str, pin_input: str) -> bool:
        stored = self._cache.get(f"pin_{username}")
        if not stored:
            return pin_input == "0000"
        return self._hash(pin_input) == stored

    # ========== PROVIDER CREDENTIALS (Encrypted) ==========

    def set_provider(
        self,
        name: str,
        api_key: str,
        base_url: str = None,
        model: str = None,
        user_id: str = "default",
    ):
        import base64 as _b64

        f = _get_fernet()
        encrypted_key = f.encrypt(api_key.encode()).decode()

        provider_data = {
            "key_hash": self._hash(api_key),
            "key_enc": encrypted_key,
            "base_url": base_url,
            "model": model,
            "owner": user_id,
        }

        key = f"providers_{user_id}"
        if key not in self._cache:
            self._cache[key] = {}

        self._cache[key][name.lower()] = provider_data
        self._save()

    def get_provider(self, name: str, user_id: str = "default") -> dict:
        user_providers = self._cache.get(f"providers_{user_id}", {})
        provider = user_providers.get(name.lower())

        if not provider and user_id != "default":
            default_providers = self._cache.get("providers_default", {})
            provider = default_providers.get(name.lower())

        if not provider:
            global_providers = self._cache.get("providers", {})
            provider = global_providers.get(name.lower())

        if not provider:
            return None

        encrypted_key = provider.get("key_enc", "")
        if not encrypted_key:
            return None

        # Try Fernet decryption first; fall back to base64 for legacy entries
        api_key = None
        try:
            f = _get_fernet()
            api_key = f.decrypt(encrypted_key.encode()).decode()
        except Exception:
            try:
                import base64 as _b64

                api_key = _b64.b64decode(encrypted_key).decode()
            except Exception:
                api_key = None

        return {
            "api_key": api_key,
            "base_url": provider.get("base_url"),
            "model": provider.get("model"),
            "owner": provider.get("owner", "default"),
        }

    def list_providers(self, user_id: str = "default") -> list:
        user_providers = set(self._cache.get(f"providers_{user_id}", {}).keys())
        default_providers = set(self._cache.get("providers_default", {}).keys())
        global_providers = set(self._cache.get("providers", {}).keys())

        return list(user_providers | default_providers | global_providers)

    def delete_provider(self, name: str, user_id: str = "default") -> bool:
        key = f"providers_{user_id}"
        providers = self._cache.get(key, {})
        if name.lower() in providers:
            del providers[name.lower()]
            self._save()
            return True
        return False

    def get_active_provider(self, user_id: str = "default") -> str:
        user_active = self._cache.get(f"active_provider_{user_id}")
        if user_active:
            return user_active
        return self._cache.get("active_provider", "local")

    def set_active_provider(self, name: str, user_id: str = "default"):
        self._cache[f"active_provider_{user_id}"] = name.lower()
        self._save()


# Singleton
vault = Vault()
