import sys
import os

# Ensure we can import tests module
sys.path.append(os.getcwd())

# Apply patches BEFORE importing the app
from tests.phase5_ordeal.mocks import apply_patches
apply_patches("mock_main")

# Now import the main app
from memory_thread.cli.main import app

if __name__ == "__main__":
    app()
