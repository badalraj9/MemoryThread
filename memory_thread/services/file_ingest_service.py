"""
File Ingestion Service - Load files into Memory Thread.

Stores originals in Vault, chunks content, embeds, and stores in memory.
"""

import os
import json
from pathlib import Path
from typing import Dict, List, Any, Optional
import uuid
import re

from memory_thread.services.vault_service import vault_service
from memory_thread.utils.logger import get_logger

log = get_logger(__name__)

SUPPORTED_EXTENSIONS = {
    ".py",
    ".js",
    ".ts",
    ".jsx",
    ".tsx",
    ".go",
    ".rs",
    ".java",
    ".c",
    ".cpp",
    ".h",
    ".md",
    ".txt",
    ".rst",
    ".yaml",
    ".yml",
    ".json",
    ".jsonl",
    ".xml",
    ".html",
    ".css",
    ".sh",
    ".bash",
    ".zsh",
    ".ps1",
    ".bat",
    ".sql",
    ".graphql",
    ".log",
    ".pdf",
    ".csv",
    ".tsv",
}


def _resolve_namespace() -> str:
    """Resolve namespace from environment or project config."""
    mt_namespace = os.environ.get("MT_NAMESPACE")
    if mt_namespace:
        return mt_namespace

    config_path = Path(".mt") / "config.json"
    if config_path.exists():
        try:
            with open(config_path) as f:
                config = json.load(f)
                return config.get("namespace", "default")
        except Exception:
            pass

    return "default"


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

            ns = _resolve_namespace()
            self._client = MemoryClient(namespace=ns, use_db=True)
        return self._client

    def ingest_file(self, path: str) -> Dict[str, Any]:
        """
        Ingest a single file.

        Returns:
            {vault_id, chunks_created, file_type}
        """
        from memory_thread.services.classify_service import classify_memory

        file_path = Path(path)

        if not file_path.exists():
            raise FileNotFoundError(f"File not found: {path}")

        ext = file_path.suffix.lower()
        if ext not in SUPPORTED_EXTENSIONS:
            log.warning(f"Unsupported file type: {ext}")

        vault_result = self.vault.store(path)
        vault_id = vault_result["vault_id"]

        content = self._extract_content(file_path, ext)

        chunks = self._chunk_content(content, ext)

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
            memory_type, confidence, _ = classify_memory(file_meta)
            client.remember(
                content=file_meta, source="file", confidence=1.0, memory_type=memory_type
            )

        all_memories = []

        for i, chunk in enumerate(chunks):
            tagged_chunk = f"[{file_path.name}:{i + 1}/{len(chunks)}]\n{chunk}"
            memory_type, confidence, _ = classify_memory(tagged_chunk)

            all_memories.append(
                {
                    "content": tagged_chunk,
                    "source": "file",
                    "confidence": confidence,
                    "memory_type": memory_type,
                }
            )

        for batch_start in range(0, len(all_memories), 50):
            batch = all_memories[batch_start : batch_start + 50]
            for mem in batch:
                client.remember(
                    content=mem["content"],
                    source=mem["source"],
                    confidence=mem["confidence"],
                    memory_type=mem["memory_type"],
                )

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
                            memory_type="fact",
                        )
                        doc_facts += 1
                    log.info(f"Document intelligence: {doc_facts} facts from {file_path.name}")
            except Exception as e:
                log.warning(f"Document intelligence failed (non-critical): {e}")

        log_facts = 0
        if ext == ".log":
            try:
                from memory_thread.services.log_intelligence import log_intelligence

                log_analysis = log_intelligence.analyze_file(str(file_path))
                if log_analysis:
                    facts = log_intelligence.to_galaxy_facts(log_analysis)
                    for fact in facts:
                        client.remember(
                            content=fact["content"],
                            source="system",
                            confidence=1.0,
                            memory_type="fact",
                        )
                        log_facts += 1
                    log.info(f"Log intelligence: {log_facts} facts from {file_path.name}")
            except Exception as e:
                log.warning(f"Log intelligence failed (non-critical): {e}")

        data_facts = 0
        if ext in {".json", ".jsonl", ".csv", ".tsv"}:
            try:
                from memory_thread.services.data_intelligence import data_intelligence

                data_analysis = data_intelligence.analyze_file(str(file_path))
                if data_analysis:
                    facts = data_intelligence.to_galaxy_facts(data_analysis)
                    for fact in facts:
                        client.remember(
                            content=fact["content"],
                            source="system",
                            confidence=1.0,
                            memory_type="fact",
                        )
                        data_facts += 1
                    log.info(f"Data intelligence: {data_facts} facts from {file_path.name}")
            except Exception as e:
                log.warning(f"Data intelligence failed (non-critical): {e}")

        log.info(f"Ingested {file_path.name}: {len(chunks)} chunks")

        return {
            "vault_id": vault_id,
            "vault_path": vault_result["vault_path"],
            "original_name": file_path.name,
            "file_type": ext,
            "chunks_created": len(chunks),
            "doc_facts": doc_facts,
            "log_facts": log_facts,
            "data_facts": data_facts,
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

        skip_dirs = {
            "__pycache__",
            ".git",
            ".venv",
            "venv",
            "node_modules",
            ".egg-info",
            "dist",
            "build",
            ".tox",
            ".mypy_cache",
            ".pytest_cache",
            "memory_thread.egg-info",
        }

        all_chunks = []

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

        code_facts = 0
        try:
            from memory_thread.services.code_intelligence import code_intelligence

            project = code_intelligence.analyze_project(str(folder))

            if project.total_files > 0:
                client = self._get_client()

                summary = code_intelligence.project_summary_fact(project)
                client.remember(
                    content=summary, source="system", confidence=1.0, memory_type="fact"
                )
                code_facts += 1

                dep_graph = code_intelligence.dependency_graph_fact(project)
                if dep_graph and len(dep_graph.splitlines()) > 1:
                    client.remember(
                        content=dep_graph, source="system", confidence=1.0, memory_type="fact"
                    )
                    code_facts += 1

                call_graph = code_intelligence.call_graph_fact(project)
                if call_graph:
                    client.remember(
                        content=call_graph, source="system", confidence=1.0, memory_type="fact"
                    )
                    code_facts += 1

                for file_analysis in project.files:
                    facts = code_intelligence.to_galaxy_facts(file_analysis)
                    for fact in facts:
                        client.remember(
                            content=fact["content"],
                            source="system",
                            confidence=1.0,
                            memory_type="fact",
                        )
                        code_facts += 1

                log.info(
                    f"Code intelligence: {code_facts} structured facts from {project.total_files} files"
                )
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

        try:
            with open(path, "r", encoding="utf-8", errors="ignore") as f:
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

        if ext in {".py", ".js", ".ts", ".go", ".rs", ".java"}:
            return self._chunk_code(content, ext)

        return self._chunk_text(content)

    def _chunk_code(self, content: str, ext: str) -> List[str]:
        """Chunk code by logical units using AST when possible."""
        if ext == ".py":
            try:
                from memory_thread.services.code_intelligence import code_intelligence

                code_intel = code_intelligence
                facts = code_intel.to_galaxy_facts({"content": content, "path": "temp.py"})
                if facts:
                    return [f["content"] for f in facts]
            except Exception:
                pass

        pattern = r"((?:^(?:def |class |async def ).*?(?=^(?:def |class |async def )|\Z)))"
        matches = re.findall(pattern, content, re.MULTILINE | re.DOTALL)
        if matches:
            return [m.strip() for m in matches if m.strip()]

        return self._chunk_text(content, chunk_size=500)

    def _chunk_text(self, content: str, chunk_size: int = 500) -> List[str]:
        """Chunk text by paragraph or fixed size."""
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

        if not chunks and content:
            chunks = [content[i : i + chunk_size] for i in range(0, len(content), chunk_size)]

        return chunks


file_ingest_service = FileIngestService()


def ingest_path(path: str) -> Dict[str, Any]:
    """Convenience function to ingest file or folder."""
    p = Path(path)
    if p.is_dir():
        return file_ingest_service.ingest_folder(path)
    else:
        return file_ingest_service.ingest_file(path)
