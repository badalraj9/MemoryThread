"""
Fact Store - Layer 0 of Galaxy Schema.

Content-addressed, immutable storage for raw facts.
This is the most resilient layer - falls back to file storage if DB fails.
"""
import os
import json
import hashlib
from pathlib import Path
from typing import Optional, Dict, Any
from datetime import datetime

from memory_thread.utils.logger import get_logger

log = get_logger(__name__)

# File fallback location
FACTS_DIR = Path(os.path.expanduser("~/.mt/facts"))


class FactStore:
    """
    Content-addressed fact storage.
    
    Facts are:
    - Immutable (append-only)
    - Content-addressed (hash-based ID)
    - Deduplicated automatically
    
    Fallback: If DB fails, uses ~/.mt/facts/{hash}.json
    """
    
    def __init__(self):
        self._pg = None
        self._qdrant = None
        self._use_db = True
        self._ensure_fallback_dir()
    
    def _ensure_fallback_dir(self):
        FACTS_DIR.mkdir(parents=True, exist_ok=True)
    
    @property
    def pg(self):
        if self._pg is None:
            try:
                from memory_thread.db.postgres_client import PostgresClient
                self._pg = PostgresClient()
            except Exception as e:
                log.warning(f"Postgres unavailable, using file fallback: {e}")
                self._use_db = False
        return self._pg
    
    def _hash_content(self, content: str) -> str:
        """Generate content-addressed hash."""
        return hashlib.sha256(content.encode('utf-8')).hexdigest()[:16]
    
    def store(
        self,
        content: str,
        source_uri: Optional[str] = None,
        content_type: str = "text",
        metadata: Optional[Dict] = None
    ) -> str:
        """
        Store a fact (content-addressed, deduplicated).
        
        Args:
            content: Raw content (code, text, log, etc.)
            source_uri: Origin URI (file path, URL, etc.)
            content_type: Type (text, code, log, document)
            metadata: Additional metadata
            
        Returns:
            fact_id (content hash)
        """
        fact_id = self._hash_content(content)
        
        # Check if already exists
        if self.exists(fact_id):
            log.debug(f"Fact already exists: {fact_id}")
            return fact_id
        
        fact = {
            "fact_id": fact_id,
            "content": content,
            "source_uri": source_uri,
            "content_type": content_type,
            "content_length": len(content),
            "created_at": datetime.utcnow().isoformat(),
            "metadata": metadata or {},
        }
        
        # Try DB first
        if self._use_db and self.pg:
            try:
                self._store_db(fact)
            except Exception as e:
                log.warning(f"DB store failed, using file: {e}")
                self._store_file(fact_id, fact)
        else:
            self._store_file(fact_id, fact)
        
        log.info(f"Stored fact: {fact_id} (source={source_uri})")
        return fact_id
    
    def _store_db(self, fact: Dict):
        """Store fact in Postgres."""
        with self.pg.get_cursor() as cur:
            cur.execute("""
                INSERT INTO facts (fact_id, content, source_uri, content_type, metadata, created_at)
                VALUES (%s, %s, %s, %s, %s, %s)
                ON CONFLICT (fact_id) DO NOTHING
            """, (
                fact["fact_id"],
                fact["content"],
                fact["source_uri"],
                fact["content_type"],
                json.dumps(fact["metadata"]),
                fact["created_at"]
            ))
    
    def _store_file(self, fact_id: str, fact: Dict):
        """Store fact as JSON file (fallback)."""
        path = FACTS_DIR / f"{fact_id}.json"
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(fact, f, indent=2)
    
    def get(self, fact_id: str) -> Optional[Dict]:
        """Retrieve a fact by ID."""
        # Try DB first
        if self._use_db and self.pg:
            try:
                result = self._get_db(fact_id)
                if result:
                    return result
            except Exception as e:
                log.debug(f"DB get failed: {e}")
        
        # Fall back to file
        return self._get_file(fact_id)
    
    def _get_db(self, fact_id: str) -> Optional[Dict]:
        """Get fact from Postgres."""
        with self.pg.get_cursor() as cur:
            cur.execute("""
                SELECT fact_id, content, source_uri, content_type, metadata, created_at
                FROM facts WHERE fact_id = %s
            """, (fact_id,))
            row = cur.fetchone()
            
            if row:
                return {
                    "fact_id": row[0],
                    "content": row[1],
                    "source_uri": row[2],
                    "content_type": row[3],
                    "metadata": row[4] if isinstance(row[4], dict) else json.loads(row[4] or "{}"),
                    "created_at": row[5],
                }
        return None
    
    def _get_file(self, fact_id: str) -> Optional[Dict]:
        """Get fact from file fallback."""
        path = FACTS_DIR / f"{fact_id}.json"
        if path.exists():
            with open(path, 'r', encoding='utf-8') as f:
                return json.load(f)
        return None
    
    def exists(self, fact_id: str) -> bool:
        """Check if fact exists."""
        # Check file first (faster)
        if (FACTS_DIR / f"{fact_id}.json").exists():
            return True
        
        # Check DB
        if self._use_db and self.pg:
            try:
                with self.pg.get_cursor() as cur:
                    cur.execute("SELECT 1 FROM facts WHERE fact_id = %s", (fact_id,))
                    return cur.fetchone() is not None
            except Exception:
                pass
        
        return False
    
    def list_facts(self, limit: int = 100) -> list:
        """List all facts."""
        facts = []
        
        # Get from files
        for f in FACTS_DIR.glob("*.json"):
            if len(facts) >= limit:
                break
            try:
                with open(f, 'r') as file:
                    data = json.load(file)
                    facts.append({
                        "fact_id": data["fact_id"],
                        "source_uri": data.get("source_uri"),
                        "content_type": data.get("content_type"),
                        "created_at": data.get("created_at"),
                    })
            except Exception:
                pass
        
        return facts
    
    def get_stats(self) -> Dict:
        """Get fact store statistics."""
        file_count = len(list(FACTS_DIR.glob("*.json")))
        
        return {
            "file_facts": file_count,
            "db_available": self._use_db and self.pg is not None,
            "fallback_path": str(FACTS_DIR),
        }


# Singleton
fact_store = FactStore()
