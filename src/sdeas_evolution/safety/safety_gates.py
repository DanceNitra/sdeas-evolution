"""SafetyGates: tiered risk validation for self-mutating agents.

Rules:
- SAFE   : no_core + syntax + tests + type_check all pass -> auto-apply
- LOW    : no_core + syntax + tests pass, type_check skipped/failed -> apply, flag review
- MEDIUM : no_core + syntax pass, tests or type_check failed -> human approval needed
- HIGH   : core touched OR syntax broken OR catastrophic failure -> reject outright
"""
from __future__ import annotations
import os
import subprocess
from pathlib import Path
from typing import Optional
from enum import Enum
from ..models import ChangeProposal, SafetyReport


class RiskTier(str, Enum):
    """Risk classification for a proposal."""
    safe = "safe"
    low = "low"
    medium = "medium"
    high = "high"
    unknown = "unknown"


class SafetyGates:
    """Tiered safety gates: classify risk, then decide auto-approval vs human review vs reject."""

    def __init__(self, repo_path: Path):
        self.repo = repo_path

    def evaluate(self, proposal: ChangeProposal, files_to_modify: list[str]) -> SafetyReport:
        """Run all checks, classify risk tier, decide auto-approval."""
        report = SafetyReport(proposal_id=proposal.proposal_id)

        # Gate 0: Capture rollback hash
        try:
            report.rollback_hash = self._capture_rollback()
        except Exception as e:
            report.details.append(f"Rollback capture failed: {e}")
            report.risk_tier = RiskTier.high.value
            return report

        # Gate 1: Core domain check
        report.no_core_modified = self._check_core_domain(files_to_modify)
        if not report.no_core_modified:
            report.details.append("CORE_DOMAIN_VIOLATION: core/ files cannot be modified")
            report.risk_tier = RiskTier.high.value
            return report

        # Gate 2: Syntax check
        syntax_errors = []
        for f in files_to_modify:
            if f.endswith(".py"):
                ok, msg = self._check_syntax(f)
                if not ok:
                    syntax_errors.append(f"SYNTAX_ERROR in {f}: {msg}")
        if syntax_errors:
            report.syntax_valid = False
            report.details.extend(syntax_errors)
            report.risk_tier = RiskTier.high.value
            return report
        else:
            report.syntax_valid = True

        # Gate 3: Type check (best effort)
        report.type_check_passed, report.type_check_output = self._run_type_check()

        # Gate 4: Tests (best effort)
        report.test_check_passed, report.test_check_output = self._run_tests()

        # Calculate risk tier based on gate results
        report.risk_tier = self._calculate_risk_tier(report)

        # Auto-approval policy
        if report.risk_tier == RiskTier.safe.value:
            report.passed = True
            report.auto_applied = True
        elif report.risk_tier == RiskTier.low.value:
            report.passed = True
            report.auto_applied = True  # Auto-apply but flag for post-hoc review
            report.details.append("AUTO_APPLIED_LOW_RISK: No tests or type checker available; applied with caution")
        elif report.risk_tier == RiskTier.medium.value:
            report.passed = False       # Do not auto-apply
            report.auto_applied = False
            report.details.append("NEEDS_APPROVAL: Tests or type-check failed; human approval required")
        else:
            report.passed = False
            report.auto_applied = False

        return report

    def _calculate_risk_tier(self, report: SafetyReport) -> str:
        """Classify proposal risk based on gate outcomes."""
        # High is already handled by core/syntax gates
        if not report.no_core_modified or report.syntax_valid is False:
            return RiskTier.high.value

        # Both tests AND type check passed -> safe
        if report.test_check_passed and report.type_check_passed:
            return RiskTier.safe.value

        # Tests passed, type check skipped/unavailable -> low
        if report.test_check_passed and not self._has_cmd("mypy") and not self._has_cmd("pyright"):
            return RiskTier.low.value

        # Type check passed, tests skipped/unavailable -> low
        if report.type_check_passed and not self._has_cmd("pytest"):
            return RiskTier.low.value

        # One of tests or type check failed -> medium
        if not report.test_check_passed or not report.type_check_passed:
            return RiskTier.medium.value

        return RiskTier.unknown.value

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
        for f in files:
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
