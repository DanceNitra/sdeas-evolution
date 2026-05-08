"""ImprovementEngine: generate change proposals from scan results."""
from __future__ import annotations
import re
from typing import List, Dict, Any, Optional
from ..models import ChangeProposal, ChangeType

class ImprovementEngine:
    """Generate concrete change proposals from scan findings.

    Two modes:
    1. Pattern-based (no LLM): handles TODOs, docstrings, simple refactors
    2. LLM-aided: uses the adapter layer for deeper changes (when available)
    """

    def __init__(self, llm_adapter: Optional[Any] = None):
        self.llm = llm_adapter

    def propose(self, issues: List[Dict[str, Any]]) -> List[ChangeProposal]:
        """Convert scan findings into concrete proposals."""
        proposals = []
        for issue in issues:
            prop = self._pattern_propose(issue)
            if prop:
                proposals.append(prop)
        return proposals

    def _pattern_propose(self, issue: Dict[str, Any]) -> Optional[ChangeProposal]:
        """Generate a proposal using regex/pattern matching."""
        desc = issue["description"]
        issue_type = issue.get("type", ChangeType.fix)

        # Pattern: missing docstring on function
        m = re.search(r"Function '(.+)' missing docstring", desc)
        if m:
            return ChangeProposal(
                target_file=issue.get("file", ""),
                change_type=ChangeType.doc,
                description=f"Add docstring to function '{m.group(1)}'",
                reasoning="All public functions should have docstrings per project standards.",
                confidence=0.9,
            )

        # Pattern: missing docstring on class
        m = re.search(r"Class '(.+)' missing docstring", desc)
        if m:
            return ChangeProposal(
                target_file=issue.get("file", ""),
                change_type=ChangeType.doc,
                description=f"Add docstring to class '{m.group(1)}'",
                reasoning="All classes should have docstrings.",
                confidence=0.9,
            )

        # Pattern: long function
        m = re.search(r"Function '(.+)' is (\d+) lines", desc)
        if m:
            return ChangeProposal(
                target_file=issue.get("file", ""),
                change_type=ChangeType.refactor,
                description=f"Refactor long function '{m.group(1)}' ({m.group(2)} lines)",
                reasoning="Functions over 50 lines violate clean code guidelines.",
                confidence=0.7,
            )

        # Pattern: unresolved TODO
        if "TODO" in desc or "FIXME" in desc:
            return ChangeProposal(
                target_file=issue.get("file", ""),
                change_type=ChangeType.fix,
                description=desc,
                reasoning="Unresolved TODO comments indicate incomplete implementation.",
                confidence=0.9,
            )

        # Pattern: missing skill
        m = re.search(r"Missing skill for Phase (\d+)", desc)
        if m:
            phase = int(m.group(1))
            return ChangeProposal(
                target_file=f"~/.hermes/skills/software-development/sdeas-phase{phase}/SKILL.md",
                change_type=ChangeType.skill,
                description=f"Create skill for Phase {phase}",
                reasoning="Skills provide procedural memory for recurring tasks.",
                confidence=1.0,
            )

        return None

    def generate_docstring(self, func_def: str) -> str:
        """Generate a minimal docstring for a function signature."""
        lines = func_def.strip().splitlines()
        if not lines:
            return '"""TODO: fill docstring."""'

        # Simple: just return a template
        return '"""TODO: document this function."""'
