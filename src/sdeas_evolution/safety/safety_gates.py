"""SafetyGates: validate proposals before application."""
from __future__ import annotations
import os
import subprocess
from pathlib import Path
from typing import Optional
from ..models import ChangeProposal, SafetyReport

class SafetyGates:
    """Enforce safety rules before applying changes:

    1. Core domain read-only (core/ domain cannot be modified)
    2. Syntax valid (Python code must parse)
    3. Type check passes (mypy or pyright, if available)
    4. Tests pass (pytest on affected or full suite)
    5. Rollback hash captured before any modification
    """

    def __init__(self, repo_path: Path):
        self.repo = repo_path

    def evaluate(self, proposal: ChangeProposal, files_to_modify: list[str]) -> SafetyReport:
        """Run all safety checks, return report."""
        report = SafetyReport(proposal_id=proposal.proposal_id)

        # Gate 0: Capture rollback hash
        try:
            report.rollback_hash = self._capture_rollback()
        except Exception as e:
            report.details.append(f"Rollback capture failed: {e}")
            return report

        # Gate 1: Core domain check
        report.no_core_modified = self._check_core_domain(files_to_modify)
        if not report.no_core_modified:
            report.details.append("CORE_DOMAIN_VIOLATION: core/ files cannot be modified")

        # Gate 2: Syntax check
        for f in files_to_modify:
            if f.endswith(".py"):
                ok, msg = self._check_syntax(f)
                if not ok:
                    report.syntax_valid = False
                    report.details.append(f"SYNTAX_ERROR in {f}: {msg}")
        if report.syntax_valid is False:
            pass  # already set
        else:
            report.syntax_valid = True

        # Gate 3: Type check (best effort)
        report.type_check_passed, report.type_check_output = self._run_type_check()

        # Gate 4: Tests (best effort)
        report.test_check_passed, report.test_check_output = self._run_tests()

        # Final verdict
        report.passed = (
            report.no_core_modified
            and report.syntax_valid
            and report.type_check_passed
            and report.test_check_passed
        )
        return report

    def _capture_rollback(self) -> str:
        result = subprocess.run(
            ["git", "-C", str(self.repo), "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            raise RuntimeError("Cannot capture rollback hash")
        return result.stdout.strip()

    def _check_core_domain(self, files: list[str]) -> bool:
        """Return False if any file is under a `core/` directory."""
        for f in files:
            # Normalize path separators
            normalized = f.replace("\\", "/")
            parts = normalized.split("/")
            if "core" in parts:
                return False
        return True

    def _check_syntax(self, filepath: str) -> tuple[bool, str]:
        import ast
        full = self.repo / filepath
        if not full.exists():
            return True, "File does not exist yet"
        try:
            text = full.read_text(encoding="utf-8")
            ast.parse(text)
            return True, "OK"
        except SyntaxError as e:
            return False, str(e)
        except Exception as e:
            return False, str(e)

    def _run_type_check(self) -> tuple[bool, str]:
        """Try mypy or pyright. Return (passed, output)."""
        for cmd, name in [("mypy", "mypy"), ("pyright", "pyright")]:
            if self._has_cmd(cmd):
                result = subprocess.run(
                    [cmd, str(self.repo)],
                    capture_output=True,
                    text=True,
                    timeout=60,
                )
                passed = result.returncode == 0
                return passed, f"{name}:\n{result.stdout}\n{result.stderr}"
        return True, "No type checker installed (skipped)"

    def _run_tests(self) -> tuple[bool, str]:
        """Run pytest on the repo. Return (passed, output)."""
        if not self._has_cmd("pytest"):
            return True, "pytest not installed (skipped)"
        result = subprocess.run(
            ["pytest", str(self.repo), "-v", "--tb=short", "-q"],
            capture_output=True,
            text=True,
            timeout=120,
        )
        passed = result.returncode == 0
        return passed, result.stdout + "\n" + result.stderr

    def _has_cmd(self, cmd: str) -> bool:
        return any(
            os.path.exists(os.path.join(p, cmd))
            for p in os.environ.get("PATH", "").split(os.pathsep)
        )
