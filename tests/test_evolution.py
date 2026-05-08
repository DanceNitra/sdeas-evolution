"""Tests for Phase 6: evolution pipeline."""
from __future__ import annotations
import subprocess
import pytest
from pathlib import Path

from sdeas_evolution import (
    CodebaseScanner,
    ImprovementEngine,
    GitManager,
    SafetyGates,
    EvolutionOrchestrator,
    ChangeType,
    ChangeProposal,
)

# ── CodebaseScanner ──

def test_scanner_finds_todos(tmp_path: Path) -> None:
    py = tmp_path / "test.py"
    py.write_text('x = 1\n# TODO: fix this\ndef foo():\n    pass\n')
    scanner = CodebaseScanner(tmp_path)
    issues = scanner.scan()
    todo_issues = [i for i in issues if "TODO" in i["description"]]
    assert len(todo_issues) >= 1
    assert todo_issues[0]["type"] == ChangeType.fix


def test_scanner_finds_long_functions(tmp_path: Path) -> None:
    py = tmp_path / "test.py"
    lines = ["def foo():"]
    lines += ["    x = " + str(i) for i in range(60)]
    lines += ["    pass"]
    py.write_text("\n".join(lines))
    scanner = CodebaseScanner(tmp_path)
    issues = scanner.scan()
    long_fns = [i for i in issues if "lines" in i["description"]]
    assert len(long_fns) >= 1


def test_scanner_finds_missing_docstrings(tmp_path: Path) -> None:
    py = tmp_path / "test.py"
    py.write_text("def foo():\n    pass\n")
    scanner = CodebaseScanner(tmp_path)
    issues = scanner.scan()
    missing = [i for i in issues if "missing docstring" in i["description"]]
    assert len(missing) >= 1

# ── ImprovementEngine ──

def test_engine_proposes_docstring() -> None:
    engine = ImprovementEngine()
    issues = [{"type": ChangeType.doc, "description": "Function 'foo' missing docstring", "file": "test.py"}]
    props = engine.propose(issues)
    assert len(props) == 1
    assert props[0].change_type == ChangeType.doc
    assert "docstring" in props[0].description


def test_engine_proposes_todo() -> None:
    engine = ImprovementEngine()
    issues = [{"type": ChangeType.fix, "description": "Unresolved TODO: refactor this", "file": "test.py"}]
    props = engine.propose(issues)
    assert len(props) == 1
    assert props[0].change_type == ChangeType.fix


def test_engine_skips_unknown_issue() -> None:
    engine = ImprovementEngine()
    issues = [{"type": ChangeType.fix, "description": "Something vague", "file": "test.py"}]
    props = engine.propose(issues)
    assert len(props) == 0

# ── GitManager ──

@pytest.fixture
def git_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
    (repo / "README.md").write_text("# repo\n")
    subprocess.run(["git", "add", "."], cwd=repo, check=True)
    subprocess.run(["git", "commit", "-m", "initial", "-q"], cwd=repo, check=True)
    return repo


def test_git_create_branch(git_repo: Path) -> None:
    gm = GitManager(git_repo)
    branch = gm.create_branch("test-branch")
    assert branch == "test-branch"
    assert gm.current_branch() == "test-branch"


def test_git_stage_and_commit(git_repo: Path) -> None:
    gm = GitManager(git_repo)
    gm.create_branch("test-branch")
    (git_repo / "a.py").write_text("x = 1\n")
    gm.stage_files(["a.py"])
    gm.commit("add a")
    assert "add a" in gm.status() or gm.status() == ""


def test_git_rollback(git_repo: Path) -> None:
    gm = GitManager(git_repo)
    gm.create_branch("test-branch")
    (git_repo / "b.py").write_text("y = 2\n")
    gm.stage_files(["b.py"])
    hash_before = gm.commit("add b")
    gm.rollback()
    assert hash_before != gm.get_hash()

# ── SafetyGates ──

def test_safety_passes_for_safe_file(git_repo: Path) -> None:
    safety = SafetyGates(git_repo)
    prop = ChangeProposal(
        target_file="app/feature.py",
        change_type=ChangeType.refactor,
        description="Refactor foo",
        reasoning="Safety check test",
    )
    (git_repo / "app").mkdir()
    (git_repo / "app" / "feature.py").write_text("x = 1\n")
    report = safety.evaluate(prop, ["app/feature.py"])
    assert report.no_core_modified
    # Type-check and tests may be skipped if tools missing
    assert report.rollback_hash is not None


def test_safety_blocks_core_domain(git_repo: Path) -> None:
    safety = SafetyGates(git_repo)
    prop = ChangeProposal(
        target_file="core/password_hasher.py",
        change_type=ChangeType.fix,
        description="Fix hashing",
        reasoning="Security fix",
    )
    report = safety.evaluate(prop, ["core/password_hasher.py"])
    assert not report.no_core_modified
    assert not report.passed


def test_safety_catches_syntax_error(git_repo: Path) -> None:
    safety = SafetyGates(git_repo)
    prop = ChangeProposal(
        target_file="bad.py",
        change_type=ChangeType.fix,
        description="Broken code",
        reasoning="Syntax test",
    )
    (git_repo / "bad.py").write_text("def foo(:\n")
    report = safety.evaluate(prop, ["bad.py"])
    assert not report.syntax_valid
    assert not report.passed

# ── EvolutionOrchestrator ──

def test_evolution_dry_run(git_repo: Path) -> None:
    orchestrator = EvolutionOrchestrator(git_repo)
    result = orchestrator.evolve(dry_run=True, max_proposals=3)
    assert result.proposals_generated >= 0
    assert result.branch_name is None or result.branch_name.startswith("sdeas-evolution")


def test_evolution_list_pending(git_repo: Path) -> None:
    orchestrator = EvolutionOrchestrator(git_repo)
    proposals = orchestrator.list_pending(max=5)
    assert isinstance(proposals, list)


def test_evolution_finds_skill_gaps(git_repo: Path) -> None:
    orchestrator = EvolutionOrchestrator(git_repo)
    gaps = orchestrator.scanner.identify_gaps()
    assert isinstance(gaps, list)


def test_safety_capture_rollback(git_repo: Path) -> None:
    safety = SafetyGates(git_repo)
    prop = ChangeProposal(
        target_file="app/test.py",
        change_type=ChangeType.refactor,
        description="Test",
        reasoning="Rollback test",
    )
    (git_repo / "app").mkdir(exist_ok=True)
    (git_repo / "app" / "test.py").write_text("x = 1\n")
    report = safety.evaluate(prop, ["app/test.py"])
    assert report.rollback_hash is not None
    assert len(report.rollback_hash) == 40  # sha1
