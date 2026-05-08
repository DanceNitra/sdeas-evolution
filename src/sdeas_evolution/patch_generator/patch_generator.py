"""PatchGenerator: create concrete file modifications from ChangeProposals."""
from __future__ import annotations
import ast
import re
from pathlib import Path
from typing import Optional
from ..models import ChangeProposal, ChangeType

class PatchGenerator:
    """Generate actual file content patches for supported proposal types.

    Currently supported:
    - doc: insert docstrings for functions/classes
    - refactor: flag long functions (content not auto-modified)
    - fix: resolve simple TODOs to pass stubs
    """

    def __init__(self, repo_path: Path):
        self.repo = repo_path

    def generate(self, proposal: ChangeProposal) -> Optional[str]:
        """Return the new file content if patch is applicable, else None."""
        target = self._resolve_path(proposal.target_file)
        if not target.exists():
            return None

        content = target.read_text(encoding="utf-8")
        proposal.original_content = content

        new_content = None
        if proposal.change_type == ChangeType.doc:
            new_content = self._patch_docstring(content, proposal.description)
        if proposal.change_type == ChangeType.fix:
            new_content = self._patch_todo(content, proposal.description)

        if new_content is not None:
            proposal.proposed_content = new_content
        return new_content

    def _resolve_path(self, target_file: str) -> Path:
        if target_file.startswith("~"):
            return Path.home() / target_file.lstrip("~/")
        if target_file.startswith("/"):
            return Path(target_file)
        return self.repo / target_file

    def _patch_docstring(self, content: str, description: str) -> Optional[str]:
        """Insert a generated docstring into a function or class."""
        # Parse description to extract target name
        m_func = re.search(r"function '([^']+)'", description)
        m_cls = re.search(r"class '([^']+)'", description)
        target_name = (m_func or m_cls).group(1) if (m_func or m_cls) else None
        if not target_name:
            return None

        lines = content.splitlines(keepends=True)
        try:
            tree = ast.parse(content)
        except SyntaxError:
            return None

        # Find the definition line
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and m_func:
                if node.name == target_name:
                    return self._insert_docstring(lines, node, target_name)
            if isinstance(node, ast.ClassDef) and m_cls:
                if node.name == target_name:
                    return self._insert_docstring(lines, node, target_name, is_class=True)
        return None

    def _insert_docstring(
        self, lines: list[str], node: ast.AST, name: str, is_class: bool = False
    ) -> str:
        """Insert a generated docstring after the definition line."""
        # Determine indent from first body element or default
        body_start = getattr(node, "body", [])
        if body_start:
            first_body = body_start[0]
            if hasattr(first_body, "lineno"):
                indent_line = lines[first_body.lineno - 1]
                indent = len(indent_line) - len(indent_line.lstrip())
            else:
                indent = 4
        else:
            indent = 4

        ds = self._make_docstring(name, node, is_class)
        insert_idx = node.lineno  # zero-based: line after def/class

        # Insert after the colon line (handle multi-line signatures)
        # Find the line containing the colon
        colon_idx = node.lineno - 1
        while colon_idx < len(lines) and ":" not in lines[colon_idx]:
            colon_idx += 1
        insert_idx = colon_idx + 1

        # Build indented docstring strings
        indent_str = " " * indent
        ds_lines = [f'{indent_str}"""{ds}"""\n']

        new_lines = lines[:insert_idx] + ds_lines + lines[insert_idx:]
        return "".join(new_lines)

    def _make_docstring(self, name: str, node: ast.AST, is_class: bool) -> str:
        """Generate a minimal docstring from the AST node."""
        if is_class:
            return f"TODO: document {name} class."

        # Extract parameters for function
        params = []
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            args = node.args
            for arg in args.args:
                params.append(arg.arg)
            for arg in args.kwonlyargs:
                params.append(arg.arg)
            if args.vararg:
                params.append(f"*{args.vararg.arg}")
            if args.kwarg:
                params.append(f"**{args.kwarg.arg}")
            # Exclude self/cls
            params = [p for p in params if p not in ("self", "cls")]

        if params:
            return f"TODO: document {name} — args: {', '.join(params)}."
        return f"TODO: document {name}."

    def _patch_todo(self, content: str, description: str) -> Optional[str]:
        """Resolve a simple TODO/FIXME comment to a pass statement.

        Matches exact lines that are standalone comments (not inside strings).
        """
        lines = content.splitlines(keepends=True)
        # Extract the TODO text from the description (the quoted part after "Unresolved ")
        todo_text = None
        m = re.search(r'Unresolved "(.+?)"', description)
        if m:
            todo_text = m.group(1).strip()

        for i, line in enumerate(lines):
            # Only match actual comment lines (start with # after whitespace)
            stripped = line.lstrip()
            if not stripped.startswith("#"):
                continue
            # Must contain the specific TODO text from the description
            if todo_text and todo_text in line:
                indent = len(line) - len(line.lstrip())
                lines[i] = " " * indent + "pass  # TODO — implement\n"
                return "".join(lines)
            # Fallback: generic TODO/FIXME in a comment line
            if "TODO" in line or "FIXME" in line:
                indent = len(line) - len(line.lstrip())
                lines[i] = " " * indent + "pass  # TODO — implement\n"
                return "".join(lines)
        return None
