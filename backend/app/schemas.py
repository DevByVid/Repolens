from typing import List, Literal
from pydantic import BaseModel, Field


# ──────────────────────────────────────────────────────────────────────────
# Building blocks
# ──────────────────────────────────────────────────────────────────────────

class DependencyNode(BaseModel):
    source_file: str = Field(
        description="The relative path of the file that contains the import or dependency declaration."
    )
    imported_module: str = Field(
        description="The name of the internal file being imported, or the third-party package name."
    )
    is_external_package: bool = Field(
        description="True if the package is pulled from an external registry (pip, npm, etc.), False if it is a local internal project file."
    )


class SecurityFinding(BaseModel):
    target_file: str = Field(
        description="The relative file path where the security vulnerability or bug was discovered."
    )
    risk_level: str = Field(
        description="The severity rating. Must be strictly one of: CRITICAL, HIGH, MEDIUM, LOW."
    )
    issue_type: str = Field(
        description="The security classification category (e.g., SQL Injection, Hardcoded Secret)."
    )
    explanation: str = Field(
        description="A clear, concise explanation of the root cause of the bug and why it is a risk."
    )
    patch_recommendation: str = Field(
        description="A clean, secure code snippet demonstrating how to fix the issue."
    )


class ModuleInfo(BaseModel):
    name: str
    path: str
    language: str
    imports: List[str] = Field(default_factory=list)
    exports: List[str] = Field(default_factory=list)
    description: str = ""


# ──────────────────────────────────────────────────────────────────────────
# What we ask Gemini to produce. Deliberately narrow: tech_stack, entrypoints
# and modules are derived *deterministically* from the parser's ground-truth
# file list afterwards (see app/analysis.py) rather than trusted blindly from
# the model, since LLM judgment on those was unreliable.
# ──────────────────────────────────────────────────────────────────────────

class LLMCodeAnalysis(BaseModel):
    high_level_architecture: str = Field(
        description="A structural breakdown summarizing the project's overall architectural pattern and design choices."
    )
    dependency_tree: List[DependencyNode] = Field(
        description="A complete list of all identified package-to-package and file-to-file import links."
    )
    vulnerabilities: List[SecurityFinding] = Field(
        description="A list of all discovered security flaws, bugs, or dangerous code patterns."
    )


# ──────────────────────────────────────────────────────────────────────────
# The final, enriched report: what /api/analyze returns and what gets cached
# server-side under a session_id. Both /api/chat and /api/system-map read
# from this single object, so there is exactly one source of truth.
# ──────────────────────────────────────────────────────────────────────────

class ProjectAnalysisReport(BaseModel):
    session_id: str
    high_level_architecture: str
    dependency_tree: List[DependencyNode]
    vulnerabilities: List[SecurityFinding]
    tech_stack: List[str] = Field(default_factory=list)
    entrypoints: List[str] = Field(default_factory=list)
    modules: List[ModuleInfo] = Field(default_factory=list)
    file_count: int = 0
    token_estimate: int = 0


class SystemMapResponse(BaseModel):
    modules: List[ModuleInfo]
    entrypoints: List[str]
    tech_stack: List[str]
    architecture_summary: str


# ──────────────────────────────────────────────────────────────────────────
# Chat
# ──────────────────────────────────────────────────────────────────────────

class ChatTurn(BaseModel):
    role: Literal["user", "assistant"]
    content: str


class ChatRequest(BaseModel):
    session_id: str
    question: str
    history: List[ChatTurn] = Field(default_factory=list)


class ChatResponse(BaseModel):
    answer: str
    session_id: str


class EvictRequest(BaseModel):
    session_id: str
