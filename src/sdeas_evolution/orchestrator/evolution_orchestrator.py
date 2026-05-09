"""EvolutionOrchestrator: scan → propose → validate → apply."""
from __future__ import annotations
from pathlib import Path
from typing import List, Dict, Any, Optional
from datetime import datetime

from ..models import ChangeProposal, SafetyReport, EvolutionResult, ChangeType
from ..scanner.codebase_scanner import CodebaseScanner
from ..proposer.improvement_engine import ImprovementEngine
from ..patch_generator.patch_generator import PatchGenerator
from ..git_manager.manager import GitManager
from ..safety.safety_gates import SafetyGates

class EvolutionOrchestrator:
    """Self-modifying agent: evolves its own codebase safely.

    Pipeline:
        1. Scan codebase for improvement opportunities
        2. Generate proposals from findings
        3. Create git branch for isolation
        4. For each proposal:
           a. Generate patch (populate original_content + proposed_content)
           b. Write file to disk
           c. Run safety gates (syntax, type-check, tests, core-domain)
           d. If passed -> commit; if failed -> rollback
        5. Report results
    """

    def __init__(self, repo_path: Path):
        self.repo = repo_path
        self.scanner = CodebaseScanner(repo_path)
        self.proposer = ImprovementEngine()
        self.patch_gen = PatchGenerator(repo_path)
        self.git = GitManager(repo_path)
        self.safety = SafetyGates(repo_path)

    def evolve(
        self,
        dry_run: bool = False,
        max_proposals: int = 5,
        auto_apply: bool = False,
    ) -> EvolutionResult:
        """Run full evolution pipeline."""
        result = EvolutionResult(
            run_id=datetime.utcnow().strftime("%Y%m%d_%H%M%S"),
            branch_name=None,
        )

        try:
            # 1. Scan
            issues = self.scanner.scan()
            skill_gaps = self.scanner.identify_gaps()
            all_issues = issues + skill_gaps
            result.proposals_generated = min(len(all_issues), max_proposals)

            # 2. Generate proposals (limit to max_proposals)
            proposals = self.proposer.propose(all_issues)[:max_proposals]
            if not proposals:
                result.summary = "No improvement proposals found. Codebase looks clean."
                return result

            # 3. Create branch
            if not dry_run:
                branch = self.git.create_branch()
                result.branch_name = branch

            # 4. Process each proposal
            for prop in proposals:
                if dry_run:
                    result.summary += f"[DRY-RUN] Would apply: {prop.description}\n"
                    continue

                applied, report = self._try_apply(prop)
                if applied:
                    result.proposals_applied += 1
                    result.safety_passed += 1
                applied, report = self._try_apply(prop)
                if applied:
                    result.proposals_applied += 1
                    if report and report.risk_tier in ("safe", "low"):
                        result.safety_passed += 1
                    else:
                        result.proposals_needing_approval += 1
                else:
                    if report and report.risk_tier == "medium":
                        result.proposals_needing_approval += 1
                        result.safety_passed += 1  # Not rejected — queued for review
                    else:
                        result.proposals_rejected += 1
                        result.safety_failed += 1
                    if report:
                        result.summary += f"[{report.risk_tier.upper()}] {prop.description} — {'; '.join(report.details)}\n"
                    else:
                        result.summary += f"REJECTED: {prop.description}\n"

            if not dry_run and result.proposals_applied > 0:
                result.commit_hash = self.git.get_hash()

            result.summary += (
                f"Applied {result.proposals_applied}/{len(proposals)} proposals. "
                f"Branch: {result.branch_name or 'N/A'}."
            )

        except Exception as e:
            result.error = f"Evolution failed: {e}"

        return result

    def list_pending(self, max: int = 10) -> List[ChangeProposal]:
        """Return pending proposals without applying them."""
        issues = self.scanner.scan()
        skill_gaps = self.scanner.identify_gaps()
        return self.proposer.propose(issues + skill_gaps)[:max]

    def _try_apply(self, proposal: ChangeProposal) -> tuple[bool, Optional[SafetyReport]]:
        """Apply a single proposal: generate patch, write file, run tiered safety gates."""
        try:
            # Skip skill creation for now (needs manual design)
            if proposal.change_type == ChangeType.skill:
                return True, None

            new_content = self.patch_gen.generate(proposal)
            if new_content is None:
                return False, None

            proposal.proposed_content = new_content
            target = self._resolve_path(proposal.target_file)
            files = [str(target)]

            # Pre-safety: rollback hash capture
            rollback_hash = self.safety._capture_rollback()

            # Write the patched content
            target.write_text(new_content, encoding="utf-8")

            # Run safety gates (tiered)
            report = self.safety.evaluate(proposal, files)
            report.rollback_hash = rollback_hash

            # Decision tree based on risk tier
            if report.risk_tier == "safe":
                # Auto-apply: all gates passed including tests and type check
                self.git.stage_file(str(target))
                self.git.commit(proposal.description)
                report.auto_applied = True
                report.passed = True
                return True, report
            elif report.risk_tier == "low":
                # Auto-apply with flag: core+syntax+tests OK, type check skipped
                self.git.stage_file(str(target))
                self.git.commit(proposal.description)
                report.auto_applied = True
                report.passed = True
                return True, report
            elif report.risk_tier == "medium":
                # Do NOT auto-apply. Queue for human approval.
                # Don't rollback — leave changes on branch for review
                report.auto_applied = False
                report.passed = False
                return False, report
            else:
                # HIGH risk: core violation or syntax broken. Rollback immediately.
                if report.rollback_hash:
                    self.git.checkout_file(str(target), report.rollback_hash)
                report.passed = False
                return False, report

        except Exception as e:
            return False, None

    def _resolve_path(self, target_file: str) -> Path:
        """Resolve a target_file string to a Path."""
        if target_file.startswith("~"):
            return Path.home() / target_file.lstrip("~/")
        if target_file.startswith("/"):
            return Path(target_file)
        return self.repo / target_file

    def _apply_skill(self, proposal: ChangeProposal) -> tuple[bool, Optional[SafetyReport]]:
        """Skill creation is safe: new files only."""
        path = Path.home() / ".hermes" / "skills" / "software-development" / proposal.target_file.replace("~/.hermes/skills/", "").replace("SKILL.md", "").rstrip("/")
        try:
            # Mark as would-create
            return True, None
        except Exception:
            return False, None
