"""Phase 6: Self-Modifying Agent — data models."""
from __future__ import annotations
from datetime import datetime
from enum import Enum
from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field

class ChangeType(str, Enum):
    refactor = "refactor"
    feature = "feature"
    fix = "fix"
    test = "test"
    doc = "doc"
    skill = "skill"

class ChangeProposal(BaseModel):
    """A proposed code change."""
    proposal_id: str = Field(default_factory=lambda: datetime.utcnow().strftime("%Y%m%d_%H%M%S_%f"))
    target_file: str
    change_type: ChangeType
    description: str
    reasoning: str
    original_content: Optional[str] = None
    proposed_content: Optional[str] = None
    add_imports: List[str] = Field(default_factory=list)
    confidence: float = 0.5  # 0.0-1.0

class SafetyReport(BaseModel):
    """Results of safety gate checks."""
    proposal_id: str
    type_check_passed: bool = False
    type_check_output: str = ""
    test_check_passed: bool = False
    test_check_output: str = ""
    syntax_valid: Optional[bool] = None
    no_core_modified: Optional[bool] = True
    rollback_hash: Optional[str] = None
    passed: bool = False
    details: List[str] = Field(default_factory=list)

class EvolutionResult(BaseModel):
    """Outcome of an evolution run."""
    run_id: str
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    proposals_generated: int = 0
    proposals_applied: int = 0
    proposals_rejected: int = 0
    safety_passed: int = 0
    safety_failed: int = 0
    branch_name: Optional[str] = None
    commit_hash: Optional[str] = None
    summary: str = ""
    error: Optional[str] = None
