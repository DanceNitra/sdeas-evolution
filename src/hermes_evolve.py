#!/usr/bin/env python3
"""CLI for Phase 6: Self-Modifying Agent."""
from __future__ import annotations
import json
import argparse
from pathlib import Path

from sdeas_evolution import EvolutionOrchestrator, ChangeType


def main() -> None:
    p = argparse.ArgumentParser(description="SDEAS Phase 6: Self-Modifying Agent")
    p.add_argument("--repo", type=Path, default=Path.cwd(), help="Target repository")
    p.add_argument("--dry-run", action="store_true", help="Show proposals without applying")
    p.add_argument("--pending", action="store_true", help="List pending proposals")
    p.add_argument("--evolve", action="store_true", help="Run evolution pipeline")
    p.add_argument("--max", type=int, default=5, dest="max_proposals", help="Max proposals")
    p.add_argument("--json", action="store_true", help="JSON output")
    p.add_argument("--apply", action="store_true", help="Auto-apply passed proposals")
    args = p.parse_args()

    # Find SDEAS repo root (look for sdeas_retention or similar marker)
    repo = args.repo
    while repo != repo.parent:
        if (repo / "sdeas_retention").exists() or (repo / ".git").exists():
            break
        repo = repo.parent

    if not (repo / ".git").exists():
        print("ERROR: Not a git repository. Phase 6 requires git.")
        return

    orchestrator = EvolutionOrchestrator(repo)

    if args.pending:
        proposals = orchestrator.list_pending(max=args.max_proposals)
        for prop in proposals:
            out = {
                "id": prop.proposal_id,
                "file": prop.target_file,
                "type": prop.change_type.value,
                "description": prop.description,
                "confidence": prop.confidence,
            }
            if args.json:
                print(json.dumps(out, indent=2))
            else:
                print(f"[{prop.change_type.value.upper()}] {prop.confidence:.1f} | {prop.target_file}")
                print(f"  {prop.description}")
                print(f"  Reason: {prop.reasoning}")
        return

    if args.evolve:
        result = orchestrator.evolve(
            dry_run=args.dry_run,
            max_proposals=args.max_proposals,
            auto_apply=args.apply,
        )
        if args.json:
            print(json.dumps(result.model_dump(mode="json", exclude_none=True), indent=2))
        else:
            print(f"=== Evolution Result ({result.run_id}) ===")
            print(f"Branch: {result.branch_name or 'N/A'}")
            print(f"Proposals: {result.proposals_generated} generated, {result.proposals_applied} applied, {result.proposals_rejected} rejected")
            print(f"Safety: {result.safety_passed} passed, {result.safety_failed} failed")
            if result.commit_hash:
                print(f"Commit: {result.commit_hash}")
            if result.error:
                print(f"ERROR: {result.error}")
            if result.summary:
                print(f"Summary:\n{result.summary}")
        return

    p.print_help()


if __name__ == "__main__":
    main()
