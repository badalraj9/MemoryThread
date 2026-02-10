"""
Document Intelligence Service — Structured document understanding for Memory Thread.

Parses PDFs, markdown, and text documents into structured knowledge:
  - Chapter / section / subsection hierarchy
  - Key terms and definitions
  - Citations and references
  - Figures and table captions
  - Page-to-section mapping

All extracted knowledge is stored as Galaxy Schema facts,
making entire books queryable through MT's memory system.

v2: Refined for real-world books (800+ page PDFs).
  - Stricter heading detection (avoids false positives)
  - PDF noise filtering (page numbers, headers, footers)
  - Smarter key term extraction (TF-IDF inspired)
  - Definition validation (rejects false positives)
  - Figure/citation deduplication
"""
import os
import re
from pathlib import Path
from typing import Dict, List, Any, Optional, Tuple, Set
from dataclasses import dataclass, field
from collections import Counter

from memory_thread.utils.logger import get_logger

log = get_logger(__name__)


# ═══════════════════════════════════════════════════════════════════════════════
# DATA STRUCTURES
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass
class SectionInfo:
    """A document section (chapter, section, subsection)."""
    title: str
    level: int              # 1 = chapter, 2 = section, 3 = subsection
    content: str = ""
    page_start: int = 0
    page_end: int = 0
    word_count: int = 0
    key_terms: List[str] = field(default_factory=list)
    parent: str = ""        # Parent section title


@dataclass
class Citation:
    """An extracted citation/reference."""
    text: str               # "Smith et al., 2024"
    context: str = ""       # Surrounding sentence
    section: str = ""       # Which section it appears in
    page: int = 0


@dataclass
class Definition:
    """A key term with its definition."""
    term: str
    definition: str
    section: str = ""
    page: int = 0


@dataclass
class FigureRef:
    """A figure, table, or diagram reference."""
    label: str              # "Figure 3.1" or "Table 2"
    caption: str = ""
    section: str = ""
    page: int = 0


@dataclass
class DocumentAnalysis:
    """Complete analysis of a single document."""
    file_path: str
    file_name: str
    doc_type: str           # "pdf", "markdown", "text"
    title: str = ""
    total_pages: int = 0
    total_words: int = 0
    sections: List[SectionInfo] = field(default_factory=list)
    citations: List[Citation] = field(default_factory=list)
    definitions: List[Definition] = field(default_factory=list)
    figures: List[FigureRef] = field(default_factory=list)
    key_terms: List[str] = field(default_factory=list)
    summary_sentences: List[str] = field(default_factory=list)


# ═══════════════════════════════════════════════════════════════════════════════
# NOISE FILTERING
# ═══════════════════════════════════════════════════════════════════════════════

# Common words that should NOT be treated as headings
NOISE_WORDS = {
    "the", "this", "that", "these", "those", "here", "there",
    "for", "from", "with", "which", "where", "when", "what",
    "not", "but", "and", "are", "was", "were", "been", "being",
    "has", "have", "had", "does", "did", "will", "would", "could",
    "should", "may", "might", "can", "let", "see", "also", "note",
    "now", "then", "next", "each", "every", "some", "any", "all",
    "our", "your", "its", "his", "her", "their",
}

# Common stop terms that are NOT real key terms
STOP_TERMS = {
    "The following", "In this", "For example", "As shown",
    "This is", "There are", "This section", "This chapter",
    "Note that", "More specifically", "In other words",
    "We will", "We can", "You can", "You will", "Let us",
    "In practice", "In general", "In particular", "On the",
}

# PDF footer/header noise patterns
PDF_NOISE_PATTERNS = [
    r'^\d+$',                              # Bare page numbers
    r'^Page\s+\d+',                        # "Page 42"
    r'^\d+\s*\|',                          # "42 |"
    r'^\|\s*\d+$',                         # "| 42"
    r'^©\s',                               # Copyright lines
    r'^All rights reserved',               # Copyright
    r'^https?://',                          # URLs
    r'^www\.',                             # URLs
    r'^Chapter\s+\d+$',                    # Bare "Chapter 5" (no title)
    r'^\.\s*\.\s*\.\s*',                   # Dots (table of contents leaders)
    r'^[_\-=]{5,}$',                       # Separator lines
    r'^\s*\d+\s*$',                        # Whitespace-padded page numbers
]


# ═══════════════════════════════════════════════════════════════════════════════
# DOCUMENT INTELLIGENCE SERVICE
# ═══════════════════════════════════════════════════════════════════════════════

class DocumentIntelligenceService:
    """
    Structured document analysis → Galaxy Schema facts.
    
    v2: Refined for real-world books and research papers.
    Parses documents into structured knowledge that agents can query:
      - "What does Chapter 3 cover?"
      - "What are the key terms in this paper?"
      - "What citations support the consolidation theory?"
      - "Show me the table of contents"
    """
    
    # Citation patterns (ordered by specificity)
    CITATION_PATTERNS = [
        # (Author et al., Year) or (Author & Author, Year)
        r'\(([A-Z][a-z]+(?:\s+(?:et\s+al\.|&\s+[A-Z][a-z]+))?,?\s*\d{4})\)',
        # Author et al. (Year) — standalone
        r'([A-Z][a-z]{2,}(?:\s+et\s+al\.)\s*\(\d{4}\))',
    ]
    
    # Figure/table patterns
    FIGURE_PATTERNS = [
        r'((?:Figure|Fig\.?|Table|Diagram|Chart|Exhibit)\s+\d+(?:[.-]\d+)?)\s*[.:]\s*(.+)',
        r'((?:Figure|Fig\.?|Table)\s+\d+(?:[.-]\d+)?)',
    ]
    
    # Definition patterns — stricter to avoid false positives
    DEFINITION_PATTERNS = [
        # "Term is defined as..." — term must be 2-5 words, capitalized
        r'(?:^|\. )([A-Z][a-z]+(?:\s+[A-Za-z]+){0,3})\s+(?:is defined as|refers to|is a|is an|denotes|means)\s+(.{20,})',
        # Bold or italic indicators in markdown: **term** or _term_
        r'\*\*([A-Za-z][\w\s]{2,25})\*\*[:\s]+(.{20,})',
        r'_([A-Za-z][\w\s]{2,25})_[:\s]+(.{20,})',
    ]
    
    def analyze_document(self, path: str) -> Optional[DocumentAnalysis]:
        """Analyze a document → DocumentAnalysis."""
        file_path = Path(path)
        if not file_path.exists():
            return None
        
        ext = file_path.suffix.lower()
        
        analysis = DocumentAnalysis(
            file_path=str(file_path.resolve()),
            file_name=file_path.name,
            doc_type=ext.lstrip("."),
        )
        
        if ext == ".pdf":
            self._analyze_pdf(file_path, analysis)
        elif ext == ".md":
            self._analyze_markdown(file_path, analysis)
        elif ext in {".txt", ".rst", ".tex"}:
            self._analyze_text(file_path, analysis)
        else:
            log.warning(f"Unsupported document type: {ext}")
            return None
        
        # Post-processing
        self._extract_key_terms(analysis)
        self._extract_summary_sentences(analysis)
        self._deduplicate(analysis)
        
        return analysis
    
    # ───────────────────────────────────────────────────────────────────────
    # PDF ANALYSIS (v4 — true streaming, zero bulk memory)
    # ───────────────────────────────────────────────────────────────────────
    
    # Caps to prevent memory explosion on 800+ page books
    MAX_PAGES = 200                   # Hard cap — only analyze first N pages
    MAX_SECTION_CONTENT_WORDS = 400   # Store first N words per section
    MAX_CITATIONS = 100               # Stop collecting after this many
    MAX_FIGURES = 100
    MAX_DEFINITIONS = 50
    METADATA_SAMPLE_RATE = 5          # Check every Nth line for metadata in large docs
    
    def _analyze_pdf(self, path: Path, analysis: DocumentAnalysis):
        """Parse PDF into structured sections with page tracking.
        
        v4: TRUE streaming — opens reader, processes ONE page at a time,
        never holds more than 1 page of text in memory.
        """
        reader, total_pages = self._open_pdf_reader(path)
        if not reader or total_pages == 0:
            return
        
        analysis.total_pages = total_pages
        
        # Get title from first page only
        try:
            first_page_text = reader.pages[0].extract_text() or ""
            analysis.title = self._guess_title(first_page_text)
            del first_page_text  # Free immediately
        except Exception:
            analysis.title = path.stem
        
        # Cap pages to prevent memory death on 800+ page books
        pages_to_process = min(total_pages, self.MAX_PAGES)
        is_large = pages_to_process > 50
        total_words = 0
        
        if pages_to_process < total_pages:
            log.info(f"Large PDF ({total_pages} pages) — analyzing first {pages_to_process} pages")
        
        current_section = SectionInfo(title="Preamble", level=0, page_start=1)
        section_content = []
        section_word_count = 0
        line_counter = 0
        pending_heading = None  # For multi-line CHAPTER/PART titles
        
        # Stream one page at a time — core memory optimization
        for page_idx in range(pages_to_process):
            try:
                raw_text = reader.pages[page_idx].extract_text() or ""
            except Exception:
                continue
            
            page_text = self._clean_pdf_page(raw_text, page_idx + 1, total_pages)
            del raw_text  # Free raw text immediately
            
            total_words += len(page_text.split())
            
            for line in page_text.splitlines():
                line = line.strip()
                if not line:
                    continue
                
                line_counter += 1
                
                # Handle pending heading from CHAPTER/PART without title
                if pending_heading and line:
                    # Next non-empty line after "CHAPTER 1" is the title
                    pending_level, pending_title = pending_heading
                    # Only join if this line looks like a title (short, alpha-heavy)
                    alpha_ratio = sum(c.isalpha() for c in line) / max(len(line), 1)
                    if alpha_ratio > 0.7 and len(line) < 60 and line[0].isupper():
                        full_title = f"{pending_title}: {line}"
                        pending_heading = None
                        # This IS the heading — save prev section and start new one
                        if section_word_count >= 5:
                            current_section.content = "\n".join(section_content)
                            current_section.word_count = section_word_count
                            current_section.page_end = page_idx + 1
                            analysis.sections.append(current_section)
                        current_section = SectionInfo(
                            title=full_title, level=pending_level,
                            page_start=page_idx + 1,
                        )
                        section_content = []
                        section_word_count = 0
                        continue
                    else:
                        # Doesn't look like a title — use the heading as-is
                        pending_heading = None
                
                heading = self._detect_heading_pdf(line, page_idx + 1)
                if heading:
                    level, title = heading
                    
                    # Check if this is a bare CHAPTER/PART (title on next line)
                    if re.match(r'^(?:Chapter|CHAPTER)\s+\d+$', title) or re.match(r'^(?:Part|PART)\s+[IVXLC]+$', title):
                        pending_heading = (level, title)
                        continue
                    
                    if section_word_count >= 5:
                        current_section.content = "\n".join(section_content)
                        current_section.word_count = section_word_count
                        current_section.page_end = page_idx + 1
                        analysis.sections.append(current_section)
                    
                    current_section = SectionInfo(
                        title=title, level=level, page_start=page_idx + 1,
                    )
                    section_content = []
                    section_word_count = 0
                else:
                    line_words = len(line.split())
                    if section_word_count < self.MAX_SECTION_CONTENT_WORDS:
                        section_content.append(line)
                    section_word_count += line_words
                    
                    # Sample metadata extraction — skip most lines for large docs
                    if is_large and line_counter % self.METADATA_SAMPLE_RATE != 0:
                        continue
                    if (len(analysis.citations) < self.MAX_CITATIONS
                        and len(analysis.figures) < self.MAX_FIGURES):
                        self._extract_inline_metadata(
                            line, current_section.title, page_idx + 1, analysis
                        )
            
            del page_text  # Free cleaned text
        
        # Save last section
        if section_word_count >= 5:
            current_section.content = "\n".join(section_content)
            current_section.word_count = section_word_count
            current_section.page_end = analysis.total_pages
            analysis.sections.append(current_section)
        
        analysis.total_words = total_words
        
        # Close reader
        try:
            del reader
        except Exception:
            pass
    
    def _open_pdf_reader(self, path: Path):
        """Open PDF and return (reader, total_pages) without extracting text.
        
        Returns the reader object directly — caller must extract pages one at a time.
        This avoids loading all 800+ pages of text into memory at once.
        """
        # Try pypdf first
        try:
            import pypdf
            reader = pypdf.PdfReader(str(path))
            return reader, len(reader.pages)
        except ImportError:
            pass
        except Exception as e:
            log.warning(f"pypdf failed to open {path.name}: {e}")
        
        # Fallback: pdfplumber (wraps in a compatible interface)
        try:
            import pdfplumber
            pdf = pdfplumber.open(path)
            # Wrap in a compatible interface
            class _PlumberWrapper:
                def __init__(self, pdf):
                    self._pdf = pdf
                    self.pages = pdf.pages
                def __del__(self):
                    try:
                        self._pdf.close()
                    except Exception:
                        pass
            
            wrapper = _PlumberWrapper(pdf)
            return wrapper, len(pdf.pages)
        except ImportError:
            log.warning("No PDF library installed. Install pypdf: pip install pypdf")
            return None, 0
        except Exception as e:
            log.error(f"PDF open failed: {e}")
            return None, 0
    
    def _clean_pdf_page(self, page_text: str, page_num: int, total_pages: int) -> str:
        """Remove PDF noise: page numbers, headers, footers, artifacts."""
        lines = page_text.splitlines()
        clean_lines = []
        
        for i, line in enumerate(lines):
            stripped = line.strip()
            
            # Skip empty lines
            if not stripped:
                continue
            
            # Skip noise patterns
            is_noise = False
            for pattern in PDF_NOISE_PATTERNS:
                if re.match(pattern, stripped, re.IGNORECASE):
                    is_noise = True
                    break
            
            if is_noise:
                continue
            
            # Skip very short lines at top/bottom of page (likely headers/footers)
            if (i <= 2 or i >= len(lines) - 2) and len(stripped) < 10:
                # Could be a page number or running header
                if stripped.isdigit() or re.match(r'^\d+\s*$', stripped):
                    continue
            
            # Skip lines that are just the book title repeated (running header)
            if i <= 2 and len(stripped) < 60 and not any(c.isdigit() for c in stripped):
                # Likely a running header — check if it appears on many pages
                # For now, just let it through but flag short top-of-page lines
                pass
            
            clean_lines.append(stripped)
        
        return "\n".join(clean_lines)
    
    def _detect_heading_pdf(self, line: str, page_num: int) -> Optional[Tuple[int, str]]:
        """
        Detect headings in PDF text — ULTRA-STRICT rules.
        
        v4: Rejects code fragments, math expressions, data tables,
        and anything that isn't clearly a human-written heading.
        """
        line = line.strip()
        
        # === FAST REJECTIONS ===
        
        # Empty, too long, or ends with sentence punctuation
        if not line or len(line) > 80:
            return None
        if line[-1] in ".;,)]}":
            return None
        
        # Starts with lowercase
        if line[0].islower():
            return None
        
        # Contains code/math symbols → NOT a heading
        if any(c in line for c in ">>>{}[]|=+<>@#$%&*\\"):
            return None
        
        # Too many digits (data/table row)
        digit_ratio = sum(c.isdigit() for c in line) / max(len(line), 1)
        if digit_ratio > 0.3:
            return None
        
        # Too few alpha characters (garbage line)
        alpha_count = sum(c.isalpha() for c in line)
        if alpha_count < 5:
            return None
        
        # Starts with "—" or dash (continuation, not heading)
        if line.startswith("—") or line.startswith("-") or line.startswith("–"):
            return None
        
        # Starts with common noise words
        first_word = line.split()[0].lower().rstrip(".,;:")
        if first_word in NOISE_WORDS or first_word in {"a", "an", "if", "so", "as", "to", "in", "on", "at", "by", "or", "no", "do"}:
            return None
        
        # === MATCH PATTERNS (ordered by specificity) ===
        
        # CHAPTER: "Chapter 1: Introduction" or "CHAPTER 1"
        m = re.match(r'^(?:CHAPTER|Chapter)\s+(\d+)[.:—\s]+([A-Z].{2,60})$', line)
        if m:
            return (1, f"Chapter {m.group(1)}: {m.group(2).strip()}")
        m = re.match(r'^(?:CHAPTER|Chapter)\s+(\d+)\s*$', line)
        if m:
            return (1, f"Chapter {m.group(1)}")
        
        # PART: "Part I: Foundations" — title must start with capital letter
        m = re.match(r'^(?:PART|Part)\s+([IVXLC]+)[.:—\s]+([A-Z].{2,60})$', line)
        if m:
            return (1, f"Part {m.group(1)}: {m.group(2).strip()}")
        m = re.match(r'^(?:PART|Part)\s+([IVXLC]+)\s*$', line)
        if m:
            return (1, f"Part {m.group(1)}")
        
        # APPENDIX: "Appendix A: ..."
        m = re.match(r'^(?:APPENDIX|Appendix)\s+([A-Z])[.:—\s]+([A-Z].{2,60})$', line)
        if m:
            return (1, f"Appendix {m.group(1)}: {m.group(2).strip()}")
        
        # ALL CAPS heading: "MACHINE LEARNING BASICS"
        # Must be 3+ words, all caps, only letters and spaces, 12-60 chars
        if (line.isupper() and 12 <= len(line) <= 60 
            and re.match(r'^[A-Z][A-Z\s]+$', line)
            and len(line.split()) >= 3):
            words = line.split()
            if not any(w.lower() in NOISE_WORDS for w in words[:2]):
                return (1, line.title())
        
        # Numbered section: "1.2 Gradient Descent"
        # Title must be pure alpha words (no numbers, no code)
        m = re.match(r'^(\d+(?:\.\d+)+)\s+([A-Z][A-Za-z\s\-]{3,55})$', line)
        if m:
            title = m.group(2).strip()
            # All words must be alpha
            if all(w.isalpha() for w in title.split()):
                depth = m.group(1).count(".") + 1
                return (min(depth, 3), f"{m.group(1)} {title}")
        
        # Top-level numbered: "1 Introduction" or "19 Training and Deploying"
        # Title must be pure alpha words, 2-7 words
        m = re.match(r'^(\d{1,2})\s+([A-Z][A-Za-z\s\-]{4,50})$', line)
        if m:
            title = m.group(2).strip()
            words = title.split()
            if (2 <= len(words) <= 7 
                and all(w.isalpha() or w == "-" for w in words)):
                return (1, f"{m.group(1)}. {title}")
        
        # TITLE CASE subsections: "What Is Machine Learning?" 
        # "Hyperparameter Tuning and Model Selection"
        # Rules: 3-8 words, most words capitalized, short line, no trailing period
        # Allow endings: nothing, ?, or :
        clean_line = line.rstrip("?:")
        words = clean_line.split()
        if 3 <= len(words) <= 8 and len(clean_line) <= 55:
            # Count capitalized words (skip small connectors)
            connectors = {"a", "an", "the", "of", "in", "to", "for", "and", "or", "with", "on", "at", "by", "vs"}
            cap_words = sum(1 for w in words if w[0].isupper())
            non_connector_words = [w for w in words if w.lower() not in connectors]
            
            # At least 60% of words must be capitalized, all non-connectors should be alpha
            if (cap_words >= len(words) * 0.6
                and all(w.rstrip("?:").isalpha() for w in words)
                and len(non_connector_words) >= 2
                and words[0][0].isupper()):
                return (2, line)
        
        return None
    
    def _extract_inline_metadata(self, line: str, section: str, page: int, analysis: DocumentAnalysis):
        """Extract citations, figures, and definitions from a line of text."""
        # Citations
        for pattern in self.CITATION_PATTERNS:
            for match in re.finditer(pattern, line):
                text = match.group(1) if match.lastindex else match.group(0)
                # Validate: must contain a year
                if re.search(r'\d{4}', text):
                    analysis.citations.append(Citation(
                        text=text.strip(),
                        context=line[:120].strip(),
                        section=section,
                        page=page,
                    ))
        
        # Figures and tables
        for pattern in self.FIGURE_PATTERNS:
            for match in re.finditer(pattern, line, re.IGNORECASE):
                label = match.group(1).strip()
                caption = match.group(2).strip() if match.lastindex >= 2 and match.group(2) else ""
                analysis.figures.append(FigureRef(
                    label=label,
                    caption=caption[:120],
                    section=section,
                    page=page,
                ))
        
        # Definitions
        for pattern in self.DEFINITION_PATTERNS:
            match = re.search(pattern, line)
            if match:
                term = match.group(1).strip()
                defn = match.group(2).strip()[:200]
                # Validate: term should be meaningful
                if (2 <= len(term.split()) <= 5 
                    and term.split()[0].lower() not in NOISE_WORDS
                    and len(defn) >= 20):
                    analysis.definitions.append(Definition(
                        term=term,
                        definition=defn,
                        section=section,
                        page=page,
                    ))
    
    def _extract_pdf_pages(self, path: Path) -> List[str]:
        """Extract text from PDF, page by page. Prefers pdfplumber for layout."""
        # Try pdfplumber first (better layout awareness)
        try:
            import pdfplumber
            with pdfplumber.open(path) as pdf:
                return [page.extract_text() or "" for page in pdf.pages]
        except ImportError:
            pass
        except Exception as e:
            log.warning(f"pdfplumber failed, trying pypdf: {e}")
        
        # Fallback to pypdf
        try:
            import pypdf
            reader = pypdf.PdfReader(str(path))
            return [page.extract_text() or "" for page in reader.pages]
        except ImportError:
            log.warning("No PDF library installed. Install pypdf: pip install pypdf")
            return []
        except Exception as e:
            log.error(f"PDF extraction failed: {e}")
            return []
    
    # ───────────────────────────────────────────────────────────────────────
    # MARKDOWN ANALYSIS
    # ───────────────────────────────────────────────────────────────────────
    
    def _analyze_markdown(self, path: Path, analysis: DocumentAnalysis):
        """Parse markdown with heading hierarchy."""
        try:
            content = path.read_text(encoding="utf-8", errors="ignore")
        except Exception as e:
            log.error(f"Failed to read {path}: {e}")
            return
        
        analysis.total_words = len(content.split())
        
        lines = content.splitlines()
        current_section = SectionInfo(title="Document Start", level=0)
        section_content = []
        
        # Detect title from first heading
        for line in lines:
            if line.startswith("# "):
                analysis.title = line.lstrip("# ").strip()
                break
        
        if not analysis.title:
            analysis.title = path.stem.replace("_", " ").replace("-", " ").title()
        
        for line in lines:
            # Markdown heading detection
            if line.startswith("#"):
                level = len(line) - len(line.lstrip("#"))
                title = line.lstrip("#").strip()
                
                # Save previous section
                if section_content:
                    current_section.content = "\n".join(section_content)
                    current_section.word_count = len(current_section.content.split())
                    analysis.sections.append(current_section)
                
                current_section = SectionInfo(title=title, level=level)
                section_content = []
            else:
                if line.strip():
                    section_content.append(line)
                
                # Extract inline metadata
                self._extract_inline_metadata(line, current_section.title, 0, analysis)
        
        # Save last section
        if section_content:
            current_section.content = "\n".join(section_content)
            current_section.word_count = len(current_section.content.split())
            analysis.sections.append(current_section)
    
    # ───────────────────────────────────────────────────────────────────────
    # PLAIN TEXT ANALYSIS
    # ───────────────────────────────────────────────────────────────────────
    
    def _analyze_text(self, path: Path, analysis: DocumentAnalysis):
        """Parse plain text, detecting headings by formatting."""
        try:
            content = path.read_text(encoding="utf-8", errors="ignore")
        except Exception as e:
            log.error(f"Failed to read {path}: {e}")
            return
        
        analysis.total_words = len(content.split())
        analysis.title = path.stem.replace("_", " ").replace("-", " ").title()
        
        lines = content.splitlines()
        current_section = SectionInfo(title="Document", level=0)
        section_content = []
        
        for line in lines:
            stripped = line.strip()
            if not stripped:
                continue
            
            heading = self._detect_heading_pdf(stripped, 0)
            if heading:
                level, title = heading
                if section_content:
                    current_section.content = "\n".join(section_content)
                    current_section.word_count = len(current_section.content.split())
                    analysis.sections.append(current_section)
                
                current_section = SectionInfo(title=title, level=level)
                section_content = []
            else:
                section_content.append(stripped)
                self._extract_inline_metadata(stripped, current_section.title, 0, analysis)
        
        if section_content:
            current_section.content = "\n".join(section_content)
            current_section.word_count = len(current_section.content.split())
            analysis.sections.append(current_section)
    
    # ───────────────────────────────────────────────────────────────────────
    # HELPERS
    # ───────────────────────────────────────────────────────────────────────
    
    def _guess_title(self, first_page: str) -> str:
        """Guess document title from the first page — refined heuristic."""
        lines = [l.strip() for l in first_page.splitlines() if l.strip()]
        if not lines:
            return "Untitled"
        
        candidates = []
        for i, line in enumerate(lines[:15]):
            # Skip very short, very long, URLs, copyright
            if len(line) < 8 or len(line) > 100:
                continue
            if line.startswith("http") or line.startswith("©") or line.startswith("ISBN"):
                continue
            if line.endswith(".") and len(line) > 50:
                continue  # Likely a sentence, not a title
            if re.match(r'^\d+$', line):
                continue  # Page number
            
            # Score the candidate
            score = 0
            score += len(line) * 0.5  # Longer is better (within bounds)
            if i < 5:
                score += 10  # Near top of page
            if line[0].isupper():
                score += 5
            if not any(c in line for c in ".;,"):
                score += 5  # No punctuation = more title-like
            
            candidates.append((score, line))
        
        if candidates:
            candidates.sort(reverse=True)
            return candidates[0][1]
        
        return lines[0][:80] if lines else "Untitled"
    
    def _extract_key_terms(self, analysis: DocumentAnalysis):
        """
        Extract key terms using TF-IDF-inspired frequency analysis.
        
        Looks for multi-word technical terms that appear frequently
        across multiple sections (high document frequency).
        """
        # Count term frequency across all sections
        term_section_count: Dict[str, Set[str]] = {}  # term → set of sections
        term_total_count: Counter = Counter()
        
        for section in analysis.sections:
            words = section.content.split()
            section_terms = set()
            
            for i in range(len(words) - 1):
                w1 = words[i].strip(".,;:!?()\"'[]{}").lower()
                w2 = words[i + 1].strip(".,;:!?()\"'[]{}").lower()
                
                # Both words must be meaningful
                if len(w1) < 3 or len(w2) < 3:
                    continue
                if w1 in NOISE_WORDS or w2 in NOISE_WORDS:
                    continue
                
                bigram = f"{w1} {w2}"
                
                # Skip stop phrases
                if any(bigram.startswith(s.lower()) for s in STOP_TERMS):
                    continue
                
                term_total_count[bigram] += 1
                section_terms.add(bigram)
            
            for term in section_terms:
                if term not in term_section_count:
                    term_section_count[term] = set()
                term_section_count[term].add(section.title)
        
        # Score: frequency × section spread (poor man's TF-IDF)
        scored_terms = []
        for term, count in term_total_count.items():
            section_spread = len(term_section_count.get(term, set()))
            if count >= 3 and section_spread >= 2:
                # Terms appearing in multiple sections are more important
                score = count * (1 + section_spread * 0.3)
                scored_terms.append((score, term))
        
        scored_terms.sort(reverse=True)
        
        # Title-case the results for display
        analysis.key_terms = [
            term.title() for _, term in scored_terms[:40]
        ]
        
        # Add defined terms (always important)
        for defn in analysis.definitions:
            if defn.term not in analysis.key_terms:
                analysis.key_terms.append(defn.term)
    
    def _extract_summary_sentences(self, analysis: DocumentAnalysis):
        """Extract first meaningful sentence from major sections."""
        for section in analysis.sections:
            if section.content and section.level <= 2 and section.word_count >= 20:
                # Find first sentence that's meaningful
                sentences = re.split(r'(?<=[.!?])\s+', section.content)
                for sent in sentences[:3]:  # Check first 3 sentences
                    sent = sent.strip()
                    if len(sent) > 30 and sent[0].isupper():
                        analysis.summary_sentences.append(
                            f"[{section.title}] {sent[:250]}"
                        )
                        break
    
    def _deduplicate(self, analysis: DocumentAnalysis):
        """Remove duplicate citations, figures, and definitions."""
        # Deduplicate citations
        seen_cites = set()
        unique_citations = []
        for c in analysis.citations:
            key = c.text.strip().lower()
            if key not in seen_cites:
                seen_cites.add(key)
                unique_citations.append(c)
        analysis.citations = unique_citations
        
        # Deduplicate figures
        seen_figs = set()
        unique_figures = []
        for f in analysis.figures:
            key = f.label.strip().lower()
            if key not in seen_figs:
                seen_figs.add(key)
                unique_figures.append(f)
        analysis.figures = unique_figures
        
        # Deduplicate definitions
        seen_defs = set()
        unique_defs = []
        for d in analysis.definitions:
            key = d.term.strip().lower()
            if key not in seen_defs:
                seen_defs.add(key)
                unique_defs.append(d)
        analysis.definitions = unique_defs
    
    # ───────────────────────────────────────────────────────────────────────
    # GALAXY SCHEMA CONVERSION
    # ───────────────────────────────────────────────────────────────────────
    
    def to_galaxy_facts(self, analysis: DocumentAnalysis) -> List[Dict[str, str]]:
        """Convert DocumentAnalysis into Galaxy Schema facts."""
        facts = []
        
        # Document-level fact
        doc_fact = (
            f"[DOCUMENT] {analysis.file_name}\n"
            f"  Title: {analysis.title}\n"
            f"  Type: {analysis.doc_type}\n"
            f"  Pages: {analysis.total_pages}\n"
            f"  Words: {analysis.total_words:,}\n"
            f"  Sections: {len(analysis.sections)}\n"
            f"  Citations: {len(analysis.citations)}\n"
            f"  Figures: {len(analysis.figures)}"
        )
        facts.append({"content": doc_fact, "type": "document_meta", "source": analysis.file_path})
        
        # Table of contents fact
        if analysis.sections:
            toc_lines = [f"[TABLE OF CONTENTS] {analysis.title}"]
            for section in analysis.sections:
                indent = "  " * min(section.level, 4)
                page_str = f" (p.{section.page_start})" if section.page_start else ""
                toc_lines.append(f"{indent}{section.title}{page_str} [{section.word_count} words]")
            facts.append({"content": "\n".join(toc_lines), "type": "toc", "source": analysis.file_path})
        
        # Section facts (each section becomes retrievable)
        for section in analysis.sections:
            if section.word_count < 15:
                continue
            
            content_chunks = self._chunk_section(section.content, max_words=300)
            
            for i, chunk in enumerate(content_chunks):
                chunk_label = f" (part {i+1}/{len(content_chunks)})" if len(content_chunks) > 1 else ""
                level_name = "Chapter" if section.level <= 1 else "Section" if section.level == 2 else "Subsection"
                section_fact = f"[SECTION] {section.title}{chunk_label}\n"
                section_fact += f"  Level: {level_name}\n"
                if section.page_start:
                    section_fact += f"  Pages: {section.page_start}-{section.page_end}\n"
                section_fact += f"  Content:\n{chunk}"
                facts.append({"content": section_fact, "type": "section", "source": analysis.file_path})
        
        # Key terms fact
        if analysis.key_terms:
            terms_fact = f"[KEY TERMS] {analysis.title}\n  " + ", ".join(analysis.key_terms[:30])
            facts.append({"content": terms_fact, "type": "terms", "source": analysis.file_path})
        
        # Definitions fact
        if analysis.definitions:
            def_lines = [f"[DEFINITIONS] {analysis.title}"]
            for defn in analysis.definitions[:20]:
                def_lines.append(f"  {defn.term}: {defn.definition[:150]}")
            facts.append({"content": "\n".join(def_lines), "type": "definitions", "source": analysis.file_path})
        
        # Citations fact
        if analysis.citations:
            cite_fact = (
                f"[CITATIONS] {analysis.title} ({len(analysis.citations)} references):\n  "
                + "\n  ".join(c.text for c in analysis.citations[:30])
            )
            facts.append({"content": cite_fact, "type": "citations", "source": analysis.file_path})
        
        # Figures/tables fact
        if analysis.figures:
            fig_lines = [f"[FIGURES & TABLES] {analysis.title}"]
            for fig in analysis.figures[:30]:
                page_str = f" (p.{fig.page})" if fig.page else ""
                caption = f": {fig.caption[:80]}" if fig.caption else ""
                fig_lines.append(f"  {fig.label}{page_str}{caption}")
            facts.append({"content": "\n".join(fig_lines), "type": "figures", "source": analysis.file_path})
        
        # Summary fact
        if analysis.summary_sentences:
            summary_fact = f"[SUMMARY] {analysis.title}\n" + "\n".join(
                f"  {s}" for s in analysis.summary_sentences[:15]
            )
            facts.append({"content": summary_fact, "type": "summary", "source": analysis.file_path})
        
        return facts
    
    def _chunk_section(self, content: str, max_words: int = 300) -> List[str]:
        """Split section content into retrieval-friendly chunks."""
        words = content.split()
        if len(words) <= max_words:
            return [content]
        
        chunks = []
        paragraphs = content.split("\n\n")
        if len(paragraphs) <= 1:
            # No paragraph breaks — split by sentences
            paragraphs = re.split(r'(?<=[.!?])\s+', content)
        
        current_chunk = []
        current_words = 0
        
        for para in paragraphs:
            para_words = len(para.split())
            if current_words + para_words > max_words and current_chunk:
                chunks.append("\n\n".join(current_chunk))
                current_chunk = [para]
                current_words = para_words
            else:
                current_chunk.append(para)
                current_words += para_words
        
        if current_chunk:
            chunks.append("\n\n".join(current_chunk))
        
        return chunks if chunks else [content]


# Singleton
doc_intelligence = DocumentIntelligenceService()
