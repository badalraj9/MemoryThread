
import os
import sys
from unittest.mock import patch

# Mock environment variables to match default behavior
os.environ.pop("MT_USER", None)
os.environ.pop("MT_PROVIDER", None)

# Add project root to path
sys.path.append(os.getcwd())

from memory_thread.sdk import MemoryClient
from memory_thread.nervous.vault import vault

def reproduce():
    print("--- Reproduction Script ---")
    
    # 1. Check Vault state directly
    print(f"Vault active provider (user='user'): {vault.get_active_provider('user')}")
    print(f"Vault active provider (user='default'): {vault.get_active_provider('default')}")
    
    # 2. Simulate SDK Chat
    client = MemoryClient() # Defaults to user="default" inside chat()
    
    # We need to spy on _generate_ollama to see if it's called
    with patch.object(client, '_generate_ollama', side_effect=lambda p, model: f"CALLED_OLLAMA({model})") as mock_ollama:
        with patch.object(client, '_generate_smollm', side_effect=lambda p: "CALLED_SMOLLM") as mock_smollm:
            
            print("\nCalling client.chat('test')...")
            response = client.chat("test")
            
            print(f"Response: {response}")
            
            if mock_ollama.called:
                print("PASSED: Ollama was called!")
            elif mock_smollm.called:
                print("FAILED: SmolLM was called instead of Ollama.")
                print("Reason: SDK likely defaulted to user='default' which has no active provider.")
            else:
                print("FAILED: Neither was called? (Maybe cloud provider?)")

if __name__ == "__main__":
    reproduce()
