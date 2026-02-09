"""
Test configuration and fixtures for Memory Thread.
"""
import pytest
import tempfile
import os
import sys

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


@pytest.fixture
def temp_dir():
    """Provide a temporary directory for tests."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield tmpdir


@pytest.fixture
def mock_env(monkeypatch, temp_dir):
    """Set up mock environment variables for testing."""
    monkeypatch.setenv("MT_DATA_DIR", temp_dir)
    monkeypatch.setenv("MT_TEST_MODE", "1")
    yield


@pytest.fixture
def memory_client(mock_env):
    """Create an in-memory MemoryClient for testing."""
    from memory_thread.sdk import MemoryClient
    return MemoryClient(namespace="test", use_db=False)


@pytest.fixture
def galaxy_client(mock_env, temp_dir, monkeypatch):
    """Create a MemoryClient with Galaxy Schema enabled."""
    # Redirect fact/belief storage to temp
    monkeypatch.setenv("MT_FACTS_DIR", os.path.join(temp_dir, "facts"))
    monkeypatch.setenv("MT_BELIEFS_DIR", os.path.join(temp_dir, "beliefs"))
    
    from memory_thread.sdk import MemoryClient
    return MemoryClient(namespace="galaxy_test", use_db=False)


@pytest.fixture
def vault(mock_env, temp_dir, monkeypatch):
    """Create a test vault with isolated storage."""
    vault_path = os.path.join(temp_dir, "vault.json")
    monkeypatch.setattr("memory_thread.nervous.vault.VAULT_PATH", vault_path)
    
    from memory_thread.nervous.vault import Vault
    return Vault()
