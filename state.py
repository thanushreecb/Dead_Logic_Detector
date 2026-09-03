"""
state.py — Shared AgentState
This is the "memory" of the agentic pipeline.
Every agent reads from and writes to this object.
LangGraph passes it between nodes automatically.
"""

from typing import TypedDict, Optional
from dataclasses import dataclass, field


# ── Per-variable data structures ──────────────────────────────────────────

@dataclass
class Assignment:
    name: str
    line: int
    value_text: str


@dataclass
class OutputNode:
    kind: str      # 'return' | 'print' | 'side_effect'
    line: int
    text: str


@dataclass
class DeadVariable:
    name: str
    line: int
    value_text: str
    reason: str
    confidence: str    # HIGH | MEDIUM | LOW


@dataclass
class ShadowedVar:
    """A variable whose first write is overwritten before it is ever read."""
    name: str
    first_write_line: int
    first_write_value: str
    overwrite_line: int
    func: str
    explanation: str = ""   # LLM-generated explanation
    suggestion: str = ""    # LLM-generated suggestion


@dataclass
class ImpossibleBranch:
    """A branch whose conditions can never be true simultaneously."""
    outer_conditions: list
    inner_condition: str
    line: int
    func: str
    explanation: str   # LLM-generated plain-English explanation
    suggestion: str = "Remove the inner if block — it can never execute."
    confidence: str = "HIGH"


@dataclass
class Verdict:
    variable: str
    line: int
    severity: str      # HIGH | MEDIUM | LOW
    explanation: str
    suggestion: str
    confidence: str
    retried: bool = False


# ── The main state TypedDict (LangGraph requires TypedDict) ────────────────

class AgentState(TypedDict):
    # ── Inputs
    filepath: str
    api_key: Optional[str]

    # ── Agent 1 outputs
    source: str
    assignments: list          # list[Assignment]
    output_nodes: list         # list[OutputNode]
    raw_tree: object           # tree-sitter tree (passed by ref)
    call_graph: object         # networkx DiGraph (Option C hook)
    nested_conditions: list    # list[dict] — for Agent 1.5

    # ── Agent 2 outputs
    dfg: object                # networkx DiGraph
    dead_vars: list            # list[DeadVariable]
    live_vars: list            # list[str]
    shadowed_vars: list        # list[ShadowedVar] — NEW

    # ── Agent 1.5 outputs
    impossible_branches: list  # list[ImpossibleBranch] — NEW

    # ── Agent 3 outputs
    verdicts: list             # list[Verdict]
    retry_count: int           # how many times Agent 3 has retried
    needs_retry: bool          # confidence gate flag

    # ── Agent 4 output
    report_html: str
    report_path: str

    # ── Pipeline metadata
    error: Optional[str]