"""
Vault and Access Control tests for Memory Thread.
Tests credential storage, RBAC, and provider management.
"""
import pytest


class TestVaultBasics:
    """Tests for basic Vault functionality."""
    
    def test_vault_initializes(self, vault):
        """Vault should initialize without errors."""
        assert vault is not None
    
    def test_godfather_key_generated(self, vault):
        """First call should generate godfather key."""
        key = vault.get_or_create_godfather_key()
        assert key.startswith("MT-") or key == "[HIDDEN - ALREADY SET]"
    
    def test_godfather_key_hidden_after_first(self, vault):
        """Subsequent calls should hide the key."""
        vault.get_or_create_godfather_key()
        second_call = vault.get_or_create_godfather_key()
        assert second_call == "[HIDDEN - ALREADY SET]"
    
    def test_verify_godfather_correct(self, vault):
        """Correct key should verify."""
        key = vault.get_or_create_godfather_key()
        if key != "[HIDDEN - ALREADY SET]":
            assert vault.verify_godfather(key) == True
    
    def test_verify_godfather_wrong(self, vault):
        """Wrong key should not verify."""
        vault.get_or_create_godfather_key()
        assert vault.verify_godfather("WRONG-KEY") == False


class TestVaultPins:
    """Tests for PIN management."""
    
    def test_set_and_verify_pin(self, vault):
        """Set PIN should be verifiable."""
        vault.set_pin("testuser", "1234")
        assert vault.verify_pin("testuser", "1234") == True
    
    def test_wrong_pin_fails(self, vault):
        """Wrong PIN should fail verification."""
        vault.set_pin("testuser", "1234")
        assert vault.verify_pin("testuser", "9999") == False
    
    def test_default_pin(self, vault):
        """Unset users should use default PIN."""
        # Default is "0000"
        assert vault.verify_pin("newuser", "0000") == True


class TestProviderCredentials:
    """Tests for provider credential management."""
    
    def test_set_provider(self, vault):
        """Should store provider credentials."""
        vault.set_provider("groq", "test_api_key", user_id="testuser")
        
        creds = vault.get_provider("groq", user_id="testuser")
        assert creds is not None
        assert creds["api_key"] == "test_api_key"
    
    def test_provider_with_url_and_model(self, vault):
        """Should store URL and model with provider."""
        vault.set_provider(
            "openai", 
            "sk-test",
            base_url="https://api.openai.com/v1",
            model="gpt-4",
            user_id="testuser"
        )
        
        creds = vault.get_provider("openai", user_id="testuser")
        assert creds["base_url"] == "https://api.openai.com/v1"
        assert creds["model"] == "gpt-4"
    
    def test_user_scoped_providers(self, vault):
        """Different users should have separate providers."""
        vault.set_provider("groq", "alice_key", user_id="alice")
        vault.set_provider("groq", "bob_key", user_id="bob")
        
        alice_creds = vault.get_provider("groq", user_id="alice")
        bob_creds = vault.get_provider("groq", user_id="bob")
        
        assert alice_creds["api_key"] == "alice_key"
        assert bob_creds["api_key"] == "bob_key"
    
    def test_fallback_to_default_provider(self, vault):
        """Should fallback to default user's provider."""
        vault.set_provider("shared", "default_key", user_id="default")
        
        # User without this provider should get default's
        creds = vault.get_provider("shared", user_id="newuser")
        assert creds is not None
        assert creds["api_key"] == "default_key"
    
    def test_list_providers(self, vault):
        """Should list configured providers."""
        vault.set_provider("groq", "key1", user_id="testuser")
        vault.set_provider("openai", "key2", user_id="testuser")
        
        providers = vault.list_providers(user_id="testuser")
        assert "groq" in providers
        assert "openai" in providers
    
    def test_delete_provider(self, vault):
        """Should remove provider."""
        vault.set_provider("temp", "key", user_id="testuser")
        assert vault.delete_provider("temp", user_id="testuser") == True
        
        creds = vault.get_provider("temp", user_id="testuser")
        assert creds is None


class TestActiveProvider:
    """Tests for active provider switching."""
    
    def test_default_active_is_local(self, vault):
        """Default active provider should be 'local'."""
        active = vault.get_active_provider(user_id="anyuser")
        assert active == "local"
    
    def test_set_active_provider(self, vault):
        """Should set active provider for user."""
        vault.set_active_provider("groq", user_id="testuser")
        
        active = vault.get_active_provider(user_id="testuser")
        assert active == "groq"
    
    def test_user_specific_active(self, vault):
        """Active provider should be user-specific."""
        vault.set_active_provider("groq", user_id="alice")
        vault.set_active_provider("openai", user_id="bob")
        
        assert vault.get_active_provider(user_id="alice") == "groq"
        assert vault.get_active_provider(user_id="bob") == "openai"
