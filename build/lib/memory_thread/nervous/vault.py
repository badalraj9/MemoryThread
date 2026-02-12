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
            except json.JSONDecodeError as e:
                import logging
                logging.getLogger(__name__).warning(f"Vault file corrupted, starting fresh: {e}")
            except Exception as e:
                import logging
                logging.getLogger(__name__).error(f"Failed to load vault: {e}")
        return {}

    def _save(self):
        try:
            with open(VAULT_PATH, 'w', encoding='utf-8') as f:
                json.dump(self._cache, f, indent=2)
        except Exception as e:
            import logging
            logging.getLogger(__name__).error(f"Failed to save vault: {e}")

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

    # ========== PROVIDER CREDENTIALS (User-Scoped) ==========
    
    def set_provider(self, name: str, api_key: str, base_url: str = None, model: str = None, user_id: str = "default"):
        """
        Store provider credentials securely (per-user).
        
        Args:
            name: Provider name (groq, openrouter, openai, etc.)
            api_key: API key (stored encoded)
            base_url: Optional base URL for custom endpoints
            model: Default model for this provider
            user_id: User who owns this key (for multi-user vaults)
        """
        import base64
        encoded_key = base64.b64encode(api_key.encode()).decode()
        
        provider_data = {
            "key_hash": self._hash(api_key),
            "key_enc": encoded_key,
            "base_url": base_url,
            "model": model,
            "owner": user_id,
        }
        
        # Store under user namespace
        key = f"providers_{user_id}"
        if key not in self._cache:
            self._cache[key] = {}
        
        self._cache[key][name.lower()] = provider_data
        self._save()
    
    def get_provider(self, name: str, user_id: str = "default") -> dict:
        """
        Get provider credentials for a user.
        
        Falls back to 'default' user if user doesn't have the provider.
        
        Returns:
            {api_key, base_url, model, owner} or None
        """
        # Try user-specific first
        user_providers = self._cache.get(f"providers_{user_id}", {})
        provider = user_providers.get(name.lower())
        
        # Fallback to default user
        if not provider and user_id != "default":
            default_providers = self._cache.get("providers_default", {})
            provider = default_providers.get(name.lower())
        
        # Legacy fallback (global providers)
        if not provider:
            global_providers = self._cache.get("providers", {})
            provider = global_providers.get(name.lower())
        
        if not provider:
            return None
        
        import base64
        try:
            api_key = base64.b64decode(provider["key_enc"]).decode()
        except:
            api_key = None
        
        return {
            "api_key": api_key,
            "base_url": provider.get("base_url"),
            "model": provider.get("model"),
            "owner": provider.get("owner", "default"),
        }
    
    def list_providers(self, user_id: str = "default") -> list:
        """List configured providers for a user (includes inherited from default)."""
        user_providers = set(self._cache.get(f"providers_{user_id}", {}).keys())
        default_providers = set(self._cache.get("providers_default", {}).keys())
        global_providers = set(self._cache.get("providers", {}).keys())
        
        return list(user_providers | default_providers | global_providers)
    
    def delete_provider(self, name: str, user_id: str = "default") -> bool:
        """Remove a provider for a user."""
        key = f"providers_{user_id}"
        providers = self._cache.get(key, {})
        if name.lower() in providers:
            del providers[name.lower()]
            self._save()
            return True
        return False
    
    def get_active_provider(self, user_id: str = "default") -> str:
        """Get active provider for a user."""
        # Try specific user preference
        user_active = self._cache.get(f"active_provider_{user_id}")
        if user_active:
            return user_active

        # Try global preference (legacy)
        global_active = self._cache.get("active_provider")
        if global_active:
            return global_active

        return "local"
    
    def set_active_provider(self, name: str, user_id: str = "default"):
        """Set active provider for a user."""
        self._cache[f"active_provider_{user_id}"] = name.lower()
        # Also set global for backward compat if it's the default user
        if user_id == "default":
            self._cache["active_provider"] = name.lower()
        self._save()


# Singleton
vault = Vault()
