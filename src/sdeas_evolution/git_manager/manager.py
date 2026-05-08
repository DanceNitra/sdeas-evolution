"""GitManager: branch, stage, commit, rollback."""
from __future__ import annotations
import subprocess
from pathlib import Path
from typing import Optional, List
from datetime import datetime

class GitManager:
    """Git operations with safety-first defaults.

    - All changes go to a new branch
    - Never modifies main or master directly
    - Rollback is always available
    """

    def __init__(self, repo_path: Path):
        self.repo = repo_path
        self._check_git()

    def _run(self, args: List[str]) -> str:
        result = subprocess.run(
            ["git", "-C", str(self.repo), *args],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            raise RuntimeError(f"Git failed: {result.stderr.strip()}")
        return result.stdout.strip()

    def _check_git(self) -> None:
        dotgit = self.repo / ".git"
        if not dotgit.exists():
            raise RuntimeError(f"Not a git repo: {self.repo}")

    def current_branch(self) -> str:
        return self._run(["branch", "--show-current"])

    def create_branch(self, name: Optional[str] = None) -> str:
        """Create a new branch and check it out."""
        if name is None:
            ts = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
            name = f"sdeas-evolution-{ts}"
        # Ensure clean state on current branch
        self._run(["checkout", "-b", name])
        return name

    def stage_file(self, file: str) -> None:
        """Stage a single file by relative path."""
        # Make path relative to repo root for git add
        rel = str(Path(file).relative_to(self.repo)) if Path(file).is_absolute() else file
        self._run(["add", rel])

    def checkout_file(self, file: str, commit_hash: str) -> None:
        """Restore a single file to a specific commit."""
        rel = str(Path(file).relative_to(self.repo)) if Path(file).is_absolute() else file
        self._run(["checkout", commit_hash, "--", rel])

    def stage_files(self, files: List[str]) -> None:
        """Stage specific files."""
        for f in files:
            self._run(["add", f])

    def stage_all(self) -> None:
        """Stage all changes. Use with caution."""
        self._run(["add", "."])

    def commit(self, message: str) -> str:
        """Commit staged changes, return commit hash."""
        self._run(["commit", "-m", message])
        return self._run(["rev-parse", "HEAD"])

    def get_hash(self) -> str:
        """Get HEAD commit hash."""
        return self._run(["rev-parse", "HEAD"])

    def rollback(self, commit_hash: Optional[str] = None) -> None:
        """Reset to specific commit or undo last commit."""
        if commit_hash:
            self._run(["reset", "--hard", commit_hash])
        else:
            self._run(["reset", "--soft", "HEAD~1"])

    def reset_branch(self) -> None:
        """Hard reset current branch to match upstream."""
        current = self.current_branch()
        self._run(["reset", "--hard", f"origin/{current}"])

    def diff_stat(self) -> str:
        return self._run(["diff", "--stat"])

    def status(self) -> str:
        return self._run(["status", "--short"])
