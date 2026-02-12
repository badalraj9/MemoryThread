"""
Code Intelligence Service — AST-based code understanding for Memory Thread.

Parses Python source files into structured knowledge:
  - Classes, functions, decorators, docstrings
  - Import relationships (file → imports → module)
  - Call graphs (function → calls → function)
  - Project structure (directory tree)

All extracted knowledge is stored as Galaxy Schema facts,
making codebases queryable through MT's memory system.
"""
import ast
import os
from pathlib import Path
from typing import Dict, List, Any, Optional, Set, Tuple
from dataclasses import dataclass, field

from memory_thread.utils.logger import get_logger

log = get_logger(__name__)


# ═══════════════════════════════════════════════════════════════════════════════
# DATA STRUCTURES
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass
class ClassInfo:
    """Extracted class metadata."""
    name: str
    file_path: str
    methods: List[str] = field(default_factory=list)
    bases: List[str] = field(default_factory=list)
    decorators: List[str] = field(default_factory=list)
    docstring: str = ""
    line_start: int = 0
    line_end: int = 0


@dataclass
class FunctionInfo:
    """Extracted function metadata."""
    name: str
    file_path: str
    class_name: Optional[str] = None
    args: List[str] = field(default_factory=list)
    return_annotation: str = ""
    calls: List[str] = field(default_factory=list)
    decorators: List[str] = field(default_factory=list)
    docstring: str = ""
    line_start: int = 0
    line_end: int = 0
    is_async: bool = False


@dataclass
class ImportInfo:
    """Extracted import relationship."""
    source_file: str
    module: str
    names: List[str] = field(default_factory=list)
    is_relative: bool = False
    line_number: int = 0


@dataclass
class CallRelation:
    """Function call relationship."""
    caller: str        # "ClassName.method" or "function_name"
    callee: str        # What's being called
    file_path: str
    line_number: int = 0


@dataclass
class CodeAnalysis:
    """Complete analysis of a single file."""
    file_path: str
    file_name: str
    language: str
    classes: List[ClassInfo] = field(default_factory=list)
    functions: List[FunctionInfo] = field(default_factory=list)
    imports: List[ImportInfo] = field(default_factory=list)
    calls: List[CallRelation] = field(default_factory=list)
    global_vars: List[str] = field(default_factory=list)
    lines_of_code: int = 0
    docstring: str = ""  # Module-level docstring


@dataclass
class ProjectAnalysis:
    """Complete analysis of a project."""
    root_path: str
    files: List[CodeAnalysis] = field(default_factory=list)
    tree: str = ""  # Directory tree as string
    total_files: int = 0
    total_classes: int = 0
    total_functions: int = 0
    total_lines: int = 0
    languages: Dict[str, int] = field(default_factory=dict)


# ═══════════════════════════════════════════════════════════════════════════════
# AST VISITORS
# ═══════════════════════════════════════════════════════════════════════════════

class CallCollector(ast.NodeVisitor):
    """Collects all function/method calls in a function body."""
    
    def __init__(self):
        self.calls: List[str] = []
    
    def visit_Call(self, node: ast.Call):
        if isinstance(node.func, ast.Name):
            self.calls.append(node.func.id)
        elif isinstance(node.func, ast.Attribute):
            # self.method() or obj.method()
            parts = []
            current = node.func
            while isinstance(current, ast.Attribute):
                parts.append(current.attr)
                current = current.value
            if isinstance(current, ast.Name):
                parts.append(current.id)
            parts.reverse()
            self.calls.append(".".join(parts))
        self.generic_visit(node)


# ═══════════════════════════════════════════════════════════════════════════════
# CODE INTELLIGENCE SERVICE
# ═══════════════════════════════════════════════════════════════════════════════

class CodeIntelligenceService:
    """
    AST-based code analysis → Galaxy Schema facts.
    
    Parses Python files into structured knowledge that agents can query:
      - "What classes are in sdk.py?"
      - "What does chat() call?"
      - "What files import tms_service?"
      - "Show me the project structure"
    """
    
    LANGUAGE_MAP = {
        ".py": "python",
        ".js": "javascript", ".ts": "typescript",
        ".jsx": "jsx", ".tsx": "tsx",
        ".go": "go", ".rs": "rust",
        ".java": "java", ".c": "c", ".cpp": "cpp",
    }
    
    def analyze_file(self, path: str) -> Optional[CodeAnalysis]:
        """
        Analyze a single source file → CodeAnalysis.
        
        Currently supports full AST parsing for Python.
        Other languages get basic structure extraction.
        """
        file_path = Path(path)
        if not file_path.exists():
            return None
        
        ext = file_path.suffix.lower()
        language = self.LANGUAGE_MAP.get(ext, "unknown")
        
        try:
            content = file_path.read_text(encoding="utf-8", errors="ignore")
        except Exception as e:
            log.error(f"Failed to read {path}: {e}")
            return None
        
        analysis = CodeAnalysis(
            file_path=str(file_path.resolve()),
            file_name=file_path.name,
            language=language,
            lines_of_code=len(content.splitlines()),
        )
        
        if ext == ".py":
            self._analyze_python(content, analysis)
        else:
            # Basic analysis for non-Python files
            self._analyze_generic(content, analysis)
        
        return analysis
    
    def analyze_project(self, root_path: str) -> ProjectAnalysis:
        """
        Analyze an entire project directory → ProjectAnalysis.
        
        Walks the directory tree, analyzes each supported file,
        and builds a project-level summary.
        """
        root = Path(root_path)
        project = ProjectAnalysis(root_path=str(root.resolve()))
        
        # Build directory tree
        project.tree = self._build_tree(root)
        
        # Skip common non-code directories
        skip_dirs = {
            "__pycache__", ".git", ".venv", "venv", "node_modules",
            ".egg-info", "dist", "build", ".tox", ".mypy_cache",
            ".pytest_cache", "memory_thread.egg-info"
        }
        
        for dirpath, dirnames, filenames in os.walk(root):
            # Filter out skip dirs
            dirnames[:] = [d for d in dirnames if d not in skip_dirs]
            
            for filename in filenames:
                filepath = Path(dirpath) / filename
                ext = filepath.suffix.lower()
                
                if ext in self.LANGUAGE_MAP:
                    analysis = self.analyze_file(str(filepath))
                    if analysis:
                        project.files.append(analysis)
                        project.total_files += 1
                        project.total_classes += len(analysis.classes)
                        project.total_functions += len(analysis.functions)
                        project.total_lines += analysis.lines_of_code
                        
                        lang = analysis.language
                        project.languages[lang] = project.languages.get(lang, 0) + 1
        
        return project
    
    # ───────────────────────────────────────────────────────────────────────
    # PYTHON AST PARSING
    # ───────────────────────────────────────────────────────────────────────
    
    def _analyze_python(self, content: str, analysis: CodeAnalysis):
        """Full AST-based analysis for Python files."""
        try:
            tree = ast.parse(content)
        except SyntaxError as e:
            log.warning(f"Syntax error in {analysis.file_name}: {e}")
            self._analyze_generic(content, analysis)
            return
        
        # Module docstring
        analysis.docstring = ast.get_docstring(tree) or ""
        
        # Extract imports
        analysis.imports = self._extract_imports(tree, analysis.file_path)
        
        # Extract classes and their methods
        for node in ast.iter_child_nodes(tree):
            if isinstance(node, ast.ClassDef):
                class_info = self._extract_class(node, analysis.file_path)
                analysis.classes.append(class_info)
                
                # Extract methods within the class
                for item in node.body:
                    if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        func_info = self._extract_function(item, analysis.file_path, class_name=node.name)
                        analysis.functions.append(func_info)
                        
                        # Collect calls
                        for call in func_info.calls:
                            analysis.calls.append(CallRelation(
                                caller=f"{node.name}.{func_info.name}",
                                callee=call,
                                file_path=analysis.file_path,
                                line_number=item.lineno,
                            ))
            
            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                func_info = self._extract_function(node, analysis.file_path)
                analysis.functions.append(func_info)
                
                for call in func_info.calls:
                    analysis.calls.append(CallRelation(
                        caller=func_info.name,
                        callee=call,
                        file_path=analysis.file_path,
                        line_number=node.lineno,
                    ))
            
            elif isinstance(node, ast.Assign):
                # Global variable assignments
                for target in node.targets:
                    if isinstance(target, ast.Name):
                        analysis.global_vars.append(target.id)
    
    def _extract_imports(self, tree: ast.AST, file_path: str) -> List[ImportInfo]:
        """Extract all import statements from AST."""
        imports = []
        
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    imports.append(ImportInfo(
                        source_file=file_path,
                        module=alias.name,
                        names=[alias.asname or alias.name],
                        is_relative=False,
                        line_number=node.lineno,
                    ))
            
            elif isinstance(node, ast.ImportFrom):
                module = node.module or ""
                names = [alias.name for alias in node.names]
                imports.append(ImportInfo(
                    source_file=file_path,
                    module=module,
                    names=names,
                    is_relative=node.level > 0,
                    line_number=node.lineno,
                ))
        
        return imports
    
    def _extract_class(self, node: ast.ClassDef, file_path: str) -> ClassInfo:
        """Extract class metadata from AST node."""
        methods = []
        for item in node.body:
            if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                methods.append(item.name)
        
        bases = []
        for base in node.bases:
            if isinstance(base, ast.Name):
                bases.append(base.id)
            elif isinstance(base, ast.Attribute):
                bases.append(ast.unparse(base))
        
        decorators = []
        for dec in node.decorator_list:
            if isinstance(dec, ast.Name):
                decorators.append(dec.id)
            elif isinstance(dec, ast.Attribute):
                decorators.append(ast.unparse(dec))
            else:
                decorators.append(ast.unparse(dec))
        
        return ClassInfo(
            name=node.name,
            file_path=file_path,
            methods=methods,
            bases=bases,
            decorators=decorators,
            docstring=ast.get_docstring(node) or "",
            line_start=node.lineno,
            line_end=node.end_lineno or node.lineno,
        )
    
    def _extract_function(
        self, node, file_path: str, class_name: Optional[str] = None
    ) -> FunctionInfo:
        """Extract function metadata + call graph from AST node."""
        # Arguments
        args = []
        for arg in node.args.args:
            if arg.arg != "self" and arg.arg != "cls":
                annotation = ""
                if arg.annotation:
                    try:
                        annotation = ast.unparse(arg.annotation)
                    except Exception:
                        pass
                args.append(f"{arg.arg}: {annotation}" if annotation else arg.arg)
        
        # Return annotation
        return_ann = ""
        if node.returns:
            try:
                return_ann = ast.unparse(node.returns)
            except Exception:
                pass
        
        # Decorators
        decorators = []
        for dec in node.decorator_list:
            try:
                decorators.append(ast.unparse(dec))
            except Exception:
                pass
        
        # Collect function calls within this function
        collector = CallCollector()
        collector.visit(node)
        
        return FunctionInfo(
            name=node.name,
            file_path=file_path,
            class_name=class_name,
            args=args,
            return_annotation=return_ann,
            calls=collector.calls,
            decorators=decorators,
            docstring=ast.get_docstring(node) or "",
            line_start=node.lineno,
            line_end=node.end_lineno or node.lineno,
            is_async=isinstance(node, ast.AsyncFunctionDef),
        )
    
    # ───────────────────────────────────────────────────────────────────────
    # GENERIC FILE ANALYSIS (non-Python)
    # ───────────────────────────────────────────────────────────────────────
    
    def _analyze_generic(self, content: str, analysis: CodeAnalysis):
        """Basic analysis for non-Python files — regex-based."""
        import re
        
        lines = content.splitlines()
        analysis.lines_of_code = len(lines)
        
        # Try to find function-like patterns
        func_patterns = {
            "javascript": r'(?:function\s+(\w+)|(?:const|let|var)\s+(\w+)\s*=\s*(?:async\s*)?\()',
            "typescript": r'(?:function\s+(\w+)|(?:const|let)\s+(\w+)\s*=\s*(?:async\s*)?\()',
            "go": r'func\s+(?:\(\w+\s+\*?\w+\)\s+)?(\w+)\(',
            "rust": r'(?:pub\s+)?fn\s+(\w+)',
            "java": r'(?:public|private|protected)?\s+\w+\s+(\w+)\s*\(',
            "c": r'(?:\w+\s+)+(\w+)\s*\([^)]*\)\s*\{',
        }
        
        pattern = func_patterns.get(analysis.language)
        if pattern:
            for i, line in enumerate(lines, 1):
                match = re.search(pattern, line)
                if match:
                    name = next(g for g in match.groups() if g)
                    analysis.functions.append(FunctionInfo(
                        name=name,
                        file_path=analysis.file_path,
                        line_start=i,
                    ))
        
        # Extract imports based on language
        import_patterns = {
            "javascript": r'(?:import\s+.*?from\s+[\'"](.+?)[\'"]|require\([\'"](.+?)[\'"]\))',
            "typescript": r'import\s+.*?from\s+[\'"](.+?)[\'"]',
            "go": r'import\s+["\s](.+?)"',
            "rust": r'use\s+([\w:]+)',
            "java": r'import\s+([\w.]+)',
        }
        
        imp_pattern = import_patterns.get(analysis.language)
        if imp_pattern:
            for i, line in enumerate(lines, 1):
                match = re.search(imp_pattern, line)
                if match:
                    module = next(g for g in match.groups() if g)
                    analysis.imports.append(ImportInfo(
                        source_file=analysis.file_path,
                        module=module,
                        line_number=i,
                    ))
    
    # ───────────────────────────────────────────────────────────────────────
    # PROJECT TREE
    # ───────────────────────────────────────────────────────────────────────
    
    def _build_tree(self, root: Path, prefix: str = "", max_depth: int = 5, _depth: int = 0) -> str:
        """Build a visual directory tree string."""
        if _depth >= max_depth:
            return ""
        
        skip_dirs = {
            "__pycache__", ".git", ".venv", "venv", "node_modules",
            ".egg-info", "dist", "build", ".tox", ".mypy_cache",
            ".pytest_cache", "memory_thread.egg-info",
        }
        
        entries = sorted(root.iterdir(), key=lambda x: (not x.is_dir(), x.name))
        entries = [e for e in entries if e.name not in skip_dirs and not e.name.startswith(".")]
        
        tree = ""
        for i, entry in enumerate(entries):
            is_last = i == len(entries) - 1
            connector = "└── " if is_last else "├── "
            
            if entry.is_dir():
                tree += f"{prefix}{connector}{entry.name}/\n"
                extension = "    " if is_last else "│   "
                tree += self._build_tree(entry, prefix + extension, max_depth, _depth + 1)
            else:
                ext = entry.suffix.lower()
                if ext in self.LANGUAGE_MAP or ext in {".md", ".txt", ".yaml", ".yml", ".json", ".toml"}:
                    tree += f"{prefix}{connector}{entry.name}\n"
        
        return tree
    
    # ───────────────────────────────────────────────────────────────────────
    # GALAXY SCHEMA CONVERSION
    # ───────────────────────────────────────────────────────────────────────
    
    def to_galaxy_facts(self, analysis: CodeAnalysis) -> List[Dict[str, str]]:
        """
        Convert a CodeAnalysis into Galaxy Schema facts.
        
        Each fact is a structured string that can be stored via
        client.ingest_fact() or client.remember().
        """
        facts = []
        fp = analysis.file_name
        
        # Module-level fact
        module_fact = f"[MODULE] {fp} ({analysis.language}, {analysis.lines_of_code} lines)"
        if analysis.docstring:
            module_fact += f"\n  Purpose: {analysis.docstring[:200]}"
        facts.append({"content": module_fact, "type": "module", "source": analysis.file_path})
        
        # Class facts
        for cls in analysis.classes:
            class_fact = (
                f"[CLASS] {cls.name} in {fp}\n"
                f"  Bases: {', '.join(cls.bases) or 'none'}\n"
                f"  Methods: {', '.join(cls.methods)}\n"
                f"  Lines: {cls.line_start}-{cls.line_end}"
            )
            if cls.docstring:
                class_fact += f"\n  Doc: {cls.docstring[:150]}"
            if cls.decorators:
                class_fact += f"\n  Decorators: {', '.join(cls.decorators)}"
            facts.append({"content": class_fact, "type": "class", "source": analysis.file_path})
        
        # Function facts
        for func in analysis.functions:
            qualified = f"{func.class_name}.{func.name}" if func.class_name else func.name
            async_tag = "async " if func.is_async else ""
            func_fact = (
                f"[FUNCTION] {async_tag}{qualified} in {fp}\n"
                f"  Args: ({', '.join(func.args) or 'none'})"
            )
            if func.return_annotation:
                func_fact += f" -> {func.return_annotation}"
            if func.calls:
                # Deduplicate and limit
                unique_calls = list(dict.fromkeys(func.calls))[:15]
                func_fact += f"\n  Calls: {', '.join(unique_calls)}"
            if func.docstring:
                func_fact += f"\n  Doc: {func.docstring[:150]}"
            func_fact += f"\n  Lines: {func.line_start}-{func.line_end}"
            facts.append({"content": func_fact, "type": "function", "source": analysis.file_path})
        
        # Import facts (grouped per file)
        if analysis.imports:
            import_lines = [f"[IMPORTS] {fp} depends on:"]
            for imp in analysis.imports:
                if imp.names:
                    import_lines.append(f"  {imp.module} ({', '.join(imp.names)})")
                else:
                    import_lines.append(f"  {imp.module}")
            facts.append({"content": "\n".join(import_lines), "type": "imports", "source": analysis.file_path})
        
        return facts
    
    def project_summary_fact(self, project: ProjectAnalysis) -> str:
        """Generate a project-level summary fact."""
        lang_str = ", ".join(f"{lang}: {count}" for lang, count in sorted(project.languages.items(), key=lambda x: -x[1]))
        
        summary = (
            f"[PROJECT] {Path(project.root_path).name}\n"
            f"  Files: {project.total_files}\n"
            f"  Classes: {project.total_classes}\n"
            f"  Functions: {project.total_functions}\n"
            f"  Lines: {project.total_lines}\n"
            f"  Languages: {lang_str}\n"
            f"\n  Directory Structure:\n"
        )
        
        # Indent tree
        for line in project.tree.splitlines():
            summary += f"    {line}\n"
        
        return summary
    
    def dependency_graph_fact(self, project: ProjectAnalysis) -> str:
        """Generate a dependency graph fact from all file imports."""
        graph_lines = ["[DEPENDENCY GRAPH]"]
        
        for file_analysis in project.files:
            if file_analysis.imports:
                src = file_analysis.file_name
                deps = set()
                for imp in file_analysis.imports:
                    # Simplify module paths
                    module = imp.module.split(".")[-1] if imp.module else ""
                    if module:
                        deps.add(module)
                if deps:
                    graph_lines.append(f"  {src} -> {', '.join(sorted(deps))}")
        
        return "\n".join(graph_lines)
    
    def call_graph_fact(self, project: ProjectAnalysis) -> str:
        """Generate a cross-file call graph fact."""
        graph_lines = ["[CALL GRAPH]"]
        
        for file_analysis in project.files:
            if file_analysis.calls:
                seen = set()
                for call in file_analysis.calls:
                    key = f"{call.caller} -> {call.callee}"
                    if key not in seen:
                        seen.add(key)
                        graph_lines.append(f"  {file_analysis.file_name}: {call.caller}() -> {call.callee}()")
        
        # Only return if we have meaningful data
        if len(graph_lines) > 1:
            return "\n".join(graph_lines[:100])  # Cap at 100 edges
        return ""


# Singleton
code_intelligence = CodeIntelligenceService()
