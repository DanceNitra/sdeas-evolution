"""Tests for PatchGenerator and self-modifying end-to-end flow."""
from __future__ import annotations
import os
import tempfile
import subprocess
from pathlib import Path

import pytest

from sdeas_evolution.models import ChangeProposal, ChangeType
from sdeas_evolution.patch_generator.patch_generator import PatchGenerator
from sdeas_evolution.git_manager.manager import GitManager


@pytest.fixture
def temp_repo(tmp_path):
    """Create a temporary git repo with a Python file."""
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init", "-b", "main"], cwd=repo, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "test@test.com"], cwd=repo, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=repo, check=True, capture_output=True)

    # Create a Python file with a function missing a docstring
    py_file = repo / "demo.py"
    py_file.write_text(
        "def hello(name):\n    return f\"Hello, {name}!\"\n\n"
        "class Greeter:\n    def greet(self):\n        return \"Hi\"\n\n"
        "def long_function():\n    # TODO: implement\n    pass\n"
    )

    subprocess.run(["git", "add", "."], cwd=repo, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "initial"], cwd=repo, check=True, capture_output=True)
    return repo


def test_patch_generator_docstring_function(temp_repo):
    """PatchGenerator inserts a docstring into a function."""
    pg = PatchGenerator(temp_repo)
    proposal = ChangeProposal(
        target_file="demo.py",
        change_type=ChangeType.doc,
        description="Add docstring to function 'hello'",
        reasoning="All public functions should have docstrings.",
    )
    new_content = pg.generate(proposal)
    assert new_content is not None
    assert 'def hello(name):' in new_content
    assert '"""TODO: document hello' in new_content
    # Original should be captured
    assert proposal.original_content is not None
    # Proposed should be set
    assert proposal.proposed_content is not None


def test_patch_generator_docstring_class(temp_repo):
    """PatchGenerator inserts a docstring into a class."""
    pg = PatchGenerator(temp_repo)
    proposal = ChangeProposal(
        target_file="demo.py",
        change_type=ChangeType.doc,
        description="Add docstring to class 'Greeter'",
        reasoning="All classes should have docstrings.",
    )
    new_content = pg.generate(proposal)
    assert new_content is not None
    assert 'class Greeter:' in new_content
    assert '"""TODO: document Greeter class.' in new_content


def test_patch_generator_skips_unknown_change_type(temp_repo):
    """PatchGenerator returns None for unsupported change types."""
    pg = PatchGenerator(temp_repo)
    proposal = ChangeProposal(
        target_file="demo.py",
        change_type=ChangeType.refactor,
        description="Refactor function 'hello' (50 lines)",
        reasoning="Too long.",
    )
    assert pg.generate(proposal) is None


def test_patch_generator_persists_original(temp_repo):
    """PatchGenerator stores original content in the proposal."""
    pg = PatchGenerator(temp_repo)
    proposal = ChangeProposal(
        target_file="demo.py",
        change_type=ChangeType.doc,
        description="Add docstring to function 'hello'",
        reasoning="Docs needed.",
    )
    original = (temp_repo / "demo.py").read_text()
    pg.generate(proposal)
    assert proposal.original_content == original


def test_git_stage_single_file(temp_repo):
    """GitManager.stage_file stages a single file."""
    git = GitManager(temp_repo)
    branch = git.create_branch("test-stage")

    # Modify file
    demo = temp_repo / "demo.py"
    demo.write_text(demo.read_text() + "\n# modified\n")

    git.stage_file(str(demo))
    status = git.status()
    assert "demo.py" in status


def test_git_checkout_file(temp_repo):
    """GitManager.checkout_file restores a file to a prior commit."""
    git = GitManager(temp_repo)
    original_hash = git.get_hash()

    # Modify and commit
    demo = temp_repo / "demo.py"
    demo.write_text(demo.read_text() + "\n# new line\n")
    git.stage_file(str(demo))
    git.commit("modify demo")

    # File now has new line
    assert "# new line" in demo.read_text()

    # Checkout original version
    git.checkout_file(str(demo), original_hash)
    content = demo.read_text()
    assert "# new line" not in content
    assert "def hello" in content


def test_patch_generator_todo_resolution(temp_repo):
    """PatchGenerator resolves a simple TODO comment to a pass."""
    pg = PatchGenerator(temp_repo)
    proposal = ChangeProposal(
        target_file="demo.py",
        change_type=ChangeType.fix,
        description="TODO: implement long_function body",
        reasoning="Unresolved TODO.",
    )
    new_content = pg.generate(proposal)
    assert new_content is not None
    assert "pass  # TODO" in new_content
    assert "# TODO: implement" not in new_content or new_content.count("TODO") == 1
