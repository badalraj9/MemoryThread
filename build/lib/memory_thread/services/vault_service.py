"""
Vault Service - Intact File Storage for Memory Thread.

Stores original files alongside chunked/embedded versions.
Files are stored by content hash for deduplication.
"""
import os
import hashlib
import json
import shutil
from pathlib import Path
from typing import Dict, List, Optional, Any
from datetime import datetime
import uuid

from memory_thread.utils.logger import get_logger

log = get_logger(__name__)

# Default vault location
VAULT_ROOT = Path(os.path.expanduser("~/.mt/vault"))


class VaultService:
    """
    Stores original files intact while MT processes them.
    
    Structure:
        ~/.mt/vault/
            {content_hash}/
                original.{ext}
                metadata.json
    """
    
    def __init__(self, vault_root: Path = None):
        self.root = vault_root or VAULT_ROOT
        self._ensure_root()
    
    def _ensure_root(self):
        """Create vault directory if needed."""
        self.root.mkdir(parents=True, exist_ok=True)
    
    def _hash_file(self, path: Path) -> str:
        """Generate SHA256 hash of file content."""
        sha256 = hashlib.sha256()
        with open(path, 'rb') as f:
            for chunk in iter(lambda: f.read(8192), b''):
                sha256.update(chunk)
        return sha256.hexdigest()[:16]  # Short hash for readability
    
    def store(self, path: str) -> Dict[str, Any]:
        """
        Store a file in the vault.
        
        Args:
            path: Path to file
            
        Returns:
            {vault_id, hash, original_name, size, stored_at, vault_path}
        """
        src = Path(path)
        if not src.exists():
            raise FileNotFoundError(f"File not found: {path}")
        
        if src.is_dir():
            return self.store_folder(path)
        
        # Hash content
        content_hash = self._hash_file(src)
        
        # Create vault entry directory
        vault_dir = self.root / content_hash
        vault_dir.mkdir(exist_ok=True)
        
        # Copy original (preserve extension)
        ext = src.suffix or ""
        dest = vault_dir / f"original{ext}"
        
        if not dest.exists():
            shutil.copy2(src, dest)
        
        # Store metadata
        metadata = {
            "vault_id": content_hash,
            "original_name": src.name,
            "original_path": str(src.absolute()),
            "extension": ext,
            "size_bytes": src.stat().st_size,
            "stored_at": datetime.utcnow().isoformat(),
            "content_hash": content_hash,
        }
        
        meta_path = vault_dir / "metadata.json"
        with open(meta_path, 'w') as f:
            json.dump(metadata, f, indent=2)
        
        log.info(f"Stored in vault: {src.name} -> {content_hash}")
        
        return {
            **metadata,
            "vault_path": str(dest),
        }
    
    def store_folder(self, path: str) -> Dict[str, Any]:
        """
        Store all files in a folder.
        
        Returns:
            {files: [...], folder_id, total_size}
        """
        folder = Path(path)
        if not folder.is_dir():
            raise ValueError(f"Not a directory: {path}")
        
        folder_id = f"folder_{uuid.uuid4().hex[:8]}"
        results = []
        total_size = 0
        
        for file_path in folder.rglob("*"):
            if file_path.is_file():
                try:
                    result = self.store(str(file_path))
                    result["relative_path"] = str(file_path.relative_to(folder))
                    results.append(result)
                    total_size += result["size_bytes"]
                except Exception as e:
                    log.warning(f"Failed to store {file_path}: {e}")
        
        return {
            "folder_id": folder_id,
            "original_path": str(folder.absolute()),
            "files": results,
            "file_count": len(results),
            "total_size_bytes": total_size,
        }
    
    def get_original(self, vault_id: str) -> Optional[Path]:
        """Get path to original file in vault."""
        vault_dir = self.root / vault_id
        if not vault_dir.exists():
            return None
        
        # Find original.* file
        for f in vault_dir.glob("original.*"):
            return f
        
        # Fallback to any original file
        original = vault_dir / "original"
        if original.exists():
            return original
        
        return None
    
    def get_metadata(self, vault_id: str) -> Optional[Dict]:
        """Get metadata for a vault entry."""
        meta_path = self.root / vault_id / "metadata.json"
        if not meta_path.exists():
            return None
        
        with open(meta_path) as f:
            return json.load(f)
    
    def list_vault(self) -> List[Dict]:
        """List all entries in the vault."""
        entries = []
        for vault_dir in self.root.iterdir():
            if vault_dir.is_dir():
                meta = self.get_metadata(vault_dir.name)
                if meta:
                    entries.append(meta)
        return entries
    
    def delete(self, vault_id: str) -> bool:
        """Delete a vault entry."""
        vault_dir = self.root / vault_id
        if vault_dir.exists():
            shutil.rmtree(vault_dir)
            log.info(f"Deleted from vault: {vault_id}")
            return True
        return False
    
    def get_stats(self) -> Dict[str, Any]:
        """Get vault statistics."""
        entries = self.list_vault()
        total_size = sum(e.get("size_bytes", 0) for e in entries)
        return {
            "total_entries": len(entries),
            "total_size_bytes": total_size,
            "total_size_mb": round(total_size / (1024 * 1024), 2),
            "vault_path": str(self.root),
        }


# Singleton
vault_service = VaultService()
