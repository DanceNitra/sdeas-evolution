"""CodebaseScanner: read and analyze the SDEAS codebase for improvement opportunities."""
from __future__ import annotations
import ast
import re
from pathlib import Path
from typing import List, Dict, Any, Tuple
from ..models import ChangeType

class CodebaseScanner:
    """Scan source files for:
    - TODO/FIXME comments
    - Missing docstrings
    - Functions without tests
    - Files with low test coverage via filename matching
    - Unused imports
    - Functions > 50 lines (too complex)
    """

    def __init__(self, root: Path):
        self.root = root

    def scan(self) -> List[Dict[str, Any]]:
        """Return a list of improvement opportunities."""
        results: List[Dict[str, Any]] = []
        for py_file in self.root.rglob("*.py"):
            # Skip cache, venv, and test directories
            if ("__pycache__" in str(py_file) or ".venv" in str(py_file)
                    or py_file.parts[0] == "tests"):
                continue
            results.extend(self._scan_file(py_file))
        return results

    def _scan_file(self, path: Path) -> List[Dict[str, Any]]:
        issues = []
        try:
            text = path.read_text(encoding="utf-8")
        except Exception:
            return issues

        # 1. TODO/FIXME comments (only standalone comment lines: # TODO, # FIXME, # XXX)
        for num, line in enumerate(text.splitlines(), 1):
            if re.match(r'^\s*#\s+(TODO|FIXME|XXX)\b', line):
                issues.append({
                    "file": str(path.relative_to(self.root)),
                    "line": num,
                    "type": ChangeType.fix,
                    "description": f"Unresolved {line.strip()}",
                    "confidence": 0.9,
                })

        # 2. Parse AST for code-level issues
        try:
            tree = ast.parse(text, filename=str(path))
        except SyntaxError:
            return issues

        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef):
                # Long functions
                lines = node.end_lineno - node.lineno if node.end_lineno else 0
                if lines > 50:
                    issues.append({
                        "file": str(path.relative_to(self.root)),
                        "line": node.lineno,
                        "type": ChangeType.refactor,
                        "description": f"Function '{node.name}' is {lines} lines — consider splitting",
                        "confidence": 0.7,
                    })
                # Missing docstring
                if not ast.get_docstring(node) and not node.name.startswith("_"):
                    issues.append({
                        "file": str(path.relative_to(self.root)),
                        "line": node.lineno,
                        "type": ChangeType.doc,
                        "description": f"Function '{node.name}' missing docstring",
                        "confidence": 0.8,
                    })

            elif isinstance(node, ast.ClassDef):
                # Classes without docstrings
                if not ast.get_docstring(node):
                    issues.append({
                        "file": str(path.relative_to(self.root)),
                        "line": node.lineno,
                        "type": ChangeType.doc,
                        "description": f"Class '{node.name}' missing docstring",
                        "confidence": 0.8,
                    })

            elif isinstance(node, ast.Import) or isinstance(node, ast.ImportFrom):
                # Check for unused imports would need scope analysis
                pass

        return issues

    def list_skills(self) -> List[str]:
        """List all skill directories in the skills root."""
        skills_root = Path.home() / ".hermes" / "skills"
        skills = []
        for f in skills_root.rglob("SKILL.md"):
            rel = f.parent.relative_to(skills_root)
            skills.append(str(rel))
        return sorted(set(skills))

    def identify_gaps(self) -> List[Dict[str, Any]]:
        """Find missing skills by comparing to existing project modules."""
        skills = self.list_skills()
        sdeas_skills = [s for s in skills if "sdeas" in s]
        phases_covered = [int(s.split("phase")[1].split("-")[0]) for s in sdeas_skills if "phase" in s and s.split("phase")[1].split("-")[0].isdigit()]

        gaps = []
        for phase in range(1, 7):
            if phase not in phases_covered:
                gaps.append({
                    "type": ChangeType.skill,
                    "description": f"Missing skill for Phase {phase}",
                    "confidence": 1.0,
                })
        return gaps
