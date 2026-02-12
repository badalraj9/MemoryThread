"""
File Ingestion Service - Load files into Memory Thread.

Stores originals in Vault, chunks content, embeds, and stores in memory.
"""
import os
from pathlib import Path
from typing import Dict, List, Any, Optional
import uuid
import re

from memory_thread.services.vault_service import vault_service
from memory_thread.utils.embeddings import get_embedding
from memory_thread.utils.logger import get_logger

log = get_logger(__name__)

# Supported file types
SUPPORTED_EXTENSIONS = {
    # Text/Code
    ".py", ".js", ".ts", ".jsx", ".tsx", ".go", ".rs", ".java", ".c", ".cpp", ".h",
    ".md", ".txt", ".rst", ".yaml", ".yml", ".json", ".xml", ".html", ".css",
    ".sh", ".bash", ".zsh", ".ps1", ".bat",
    ".sql", ".graphql",
    # Logs
    ".log",
    # Documents (text extraction)
    ".pdf",
}


class FileIngestService:
    """
    Ingests files into Memory Thread.
    
    1. Store original in Vault
    2. Parse/chunk content
    3. Embed chunks
    4. Store in MT memory
    """
    
    def __init__(self):
        self.vault = vault_service
        self._client = None
    
    def _get_client(self):
        if not self._client:
            from memory_thread.sdk import MemoryClient
            ns = os.environ.get("MT_NAMESPACE", "default")
            self._client = MemoryClient(namespace=ns, use_db=True)
        return self._client
    
    def ingest_file(self, path: str) -> Dict[str, Any]:
        """
        Ingest a single file.
        
        Returns:
            {vault_id, chunks_created, file_type}
        """
        file_path = Path(path)
        
        if not file_path.exists():
            raise FileNotFoundError(f"File not found: {path}")
        
        ext = file_path.suffix.lower()
        if ext not in SUPPORTED_EXTENSIONS:
            log.warning(f"Unsupported file type: {ext}")
        
        # 1. Store original in vault (read-only — never modifies user files)
        vault_result = self.vault.store(path)
        vault_id = vault_result["vault_id"]
        
        # 2. Extract content
        content = self._extract_content(file_path, ext)
        
        # 3. Chunk content
        chunks = self._chunk_content(content, ext)
        
        # 4. Store file-level metadata as a Galaxy fact
        client = self._get_client()
        abs_path = str(file_path.resolve())
        file_meta = (
            f"[FILE] {file_path.name}\n"
            f"  Path: {abs_path}\n"
            f"  Type: {ext}\n"
            f"  Size: {file_path.stat().st_size} bytes\n"
            f"  Chunks: {len(chunks)}"
        )
        try:
            client.ingest_fact(file_meta, source_uri=abs_path)
        except Exception:
            # Fallback: store as regular memory if Galaxy not available
            client.remember(content=file_meta, source="file", confidence=1.0, memory_type="document")
        
        # 5. Store chunks in memory — prepend source path so agents know origin
        for i, chunk in enumerate(chunks):
            tagged_chunk = f"[{file_path.name}:{i+1}/{len(chunks)}]\n{chunk}"
            client.remember(
                content=tagged_chunk,
                source="file",
                confidence=1.0,
                memory_type="code" if ext in {".py", ".js", ".ts", ".go", ".rs", ".java", ".c", ".cpp"} else "document"
            )
        
        # 6. Run document intelligence for PDFs and text docs
        doc_facts = 0
        if ext in {".pdf", ".md", ".txt", ".rst"}:
            try:
                from memory_thread.services.document_intelligence import doc_intelligence
                doc_analysis = doc_intelligence.analyze_document(str(file_path))
                if doc_analysis:
                    facts = doc_intelligence.to_galaxy_facts(doc_analysis)
                    for fact in facts:
                        client.remember(
                            content=fact["content"],
                            source="system",
                            confidence=1.0,
                            memory_type="fact"
                        )
                        doc_facts += 1
                    log.info(f"Document intelligence: {doc_facts} facts from {file_path.name}")
            except Exception as e:
                log.warning(f"Document intelligence failed (non-critical): {e}")
        
        log.info(f"Ingested {file_path.name}: {len(chunks)} chunks")
        
        return {
            "vault_id": vault_id,
            "vault_path": vault_result["vault_path"],
            "original_name": file_path.name,
            "file_type": ext,
            "chunks_created": len(chunks),
            "doc_facts": doc_facts,
            "content_length": len(content),
        }
    
    def ingest_folder(self, path: str) -> Dict[str, Any]:
        """
        Ingest all supported files in a folder.
        
        For code projects, also runs AST analysis to extract
        classes, functions, call graphs, and import relationships.
        """
        folder = Path(path)
        if not folder.is_dir():
            raise ValueError(f"Not a directory: {path}")
        
        results = []
        total_chunks = 0
        errors = []
        
        # Skip common non-code directories
        skip_dirs = {
            "__pycache__", ".git", ".venv", "venv", "node_modules",
            ".egg-info", "dist", "build", ".tox", ".mypy_cache",
            ".pytest_cache", "memory_thread.egg-info",
        }
        
        for dirpath, dirnames, filenames in os.walk(folder):
            dirnames[:] = [d for d in dirnames if d not in skip_dirs]
            
            for filename in filenames:
                file_path = Path(dirpath) / filename
                if file_path.suffix.lower() in SUPPORTED_EXTENSIONS:
                    try:
                        result = self.ingest_file(str(file_path))
                        results.append(result)
                        total_chunks += result["chunks_created"]
                    except Exception as e:
                        errors.append({"file": str(file_path), "error": str(e)})
                        log.error(f"Failed to ingest {file_path}: {e}")
        
        # Run code intelligence analysis on the entire project
        code_facts = 0
        try:
            from memory_thread.services.code_intelligence import code_intelligence
            project = code_intelligence.analyze_project(str(folder))
            
            if project.total_files > 0:
                client = self._get_client()
                
                # Store project summary
                summary = code_intelligence.project_summary_fact(project)
                client.remember(content=summary, source="system", confidence=1.0, memory_type="fact")
                code_facts += 1
                
                # Store dependency graph
                dep_graph = code_intelligence.dependency_graph_fact(project)
                if dep_graph and len(dep_graph.splitlines()) > 1:
                    client.remember(content=dep_graph, source="system", confidence=1.0, memory_type="fact")
                    code_facts += 1
                
                # Store call graph
                call_graph = code_intelligence.call_graph_fact(project)
                if call_graph:
                    client.remember(content=call_graph, source="system", confidence=1.0, memory_type="fact")
                    code_facts += 1
                
                # Store per-file structured facts
                for file_analysis in project.files:
                    facts = code_intelligence.to_galaxy_facts(file_analysis)
                    for fact in facts:
                        client.remember(
                            content=fact["content"],
                            source="system",
                            confidence=1.0,
                            memory_type="fact"
                        )
                        code_facts += 1
                
                log.info(f"Code intelligence: {code_facts} structured facts from {project.total_files} files")
        except Exception as e:
            log.warning(f"Code intelligence analysis failed (non-critical): {e}")
        
        return {
            "folder_path": str(folder),
            "files_processed": len(results),
            "chunks_created": total_chunks,
            "code_facts": code_facts,
            "errors": errors,
            "vault_path": str(self.vault.root),
        }
    
    def _extract_content(self, path: Path, ext: str) -> str:
        """Extract text content from file."""
        
        if ext == ".pdf":
            return self._extract_pdf(path)
        
        # Default: read as text
        try:
            with open(path, 'r', encoding='utf-8', errors='ignore') as f:
                return f.read()
        except Exception as e:
            log.error(f"Failed to read {path}: {e}")
            return ""
    
    def _extract_pdf(self, path: Path) -> str:
        """Extract text from PDF."""
        try:
            import pypdf
            reader = pypdf.PdfReader(str(path))
            text = ""
            for page in reader.pages:
                text += page.extract_text() or ""
            return text
        except ImportError:
            log.warning("pypdf not installed, trying pdfplumber")
            try:
                import pdfplumber
                with pdfplumber.open(path) as pdf:
                    text = ""
                    for page in pdf.pages:
                        text += page.extract_text() or ""
                    return text
            except ImportError:
                log.error("No PDF library installed. Install pypdf or pdfplumber.")
                return f"[PDF content: {path.name}]"
        except Exception as e:
            log.error(f"PDF extraction failed: {e}")
            return f"[PDF extraction failed: {path.name}]"
    
    def _chunk_content(self, content: str, ext: str) -> List[str]:
        """
        Chunk content based on file type.
        
        Code: by function/class
        Text: by paragraph or fixed size
        """
        if not content:
            return []
        
        # Code files: try to chunk by function/class
        if ext in {".py", ".js", ".ts", ".go", ".rs", ".java"}:
            return self._chunk_code(content, ext)
        
        # Default: chunk by paragraphs or fixed size
        return self._chunk_text(content)
    
    def _chunk_code(self, content: str, ext: str) -> List[str]:
        """Chunk code by logical units."""
        chunks = []
        
        if ext == ".py":
            # Simple Python chunking by def/class
            pattern = r'((?:^(?:def |class |async def ).*?(?=^(?:def |class |async def )|\Z)))'
            matches = re.findall(pattern, content, re.MULTILINE | re.DOTALL)
            if matches:
                chunks = [m.strip() for m in matches if m.strip()]
        
        # Fallback: fixed-size chunks
        if not chunks:
            chunks = self._chunk_text(content, chunk_size=500)
        
        return chunks
    
    def _chunk_text(self, content: str, chunk_size: int = 500) -> List[str]:
        """Chunk text by paragraph or fixed size."""
        # Try paragraph-based first
        paragraphs = content.split("\n\n")
        chunks = []
        current_chunk = ""
        
        for para in paragraphs:
            para = para.strip()
            if not para:
                continue
            
            if len(current_chunk) + len(para) < chunk_size:
                current_chunk += para + "\n\n"
            else:
                if current_chunk:
                    chunks.append(current_chunk.strip())
                current_chunk = para + "\n\n"
        
        if current_chunk:
            chunks.append(current_chunk.strip())
        
        # If no paragraphs, use fixed-size
        if not chunks and content:
            chunks = [content[i:i+chunk_size] for i in range(0, len(content), chunk_size)]
        
        return chunks


# Singleton
file_ingest_service = FileIngestService()


def ingest_path(path: str) -> Dict[str, Any]:
    """Convenience function to ingest file or folder."""
    p = Path(path)
    if p.is_dir():
        return file_ingest_service.ingest_folder(path)
    else:
        return file_ingest_service.ingest_file(path)
