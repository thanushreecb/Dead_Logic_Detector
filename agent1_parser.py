"""
agent1_parser.py — Parser Node (v3)
LangGraph node: reads filepath from state, produces:
  - assignments        : every variable write
  - output_nodes       : return / print / side-effect calls
  - nested_conditions  : nested if-groups for Agent 1.5
  - call_graph         : function→function DiGraph (Option C hook)
"""

import tree_sitter_python as tsp
from tree_sitter import Language, Parser
import networkx as nx
from typing import Optional

from state import AgentState, Assignment, OutputNode

PY_LANGUAGE = Language(tsp.language())
_parser = Parser(PY_LANGUAGE)

SIDE_EFFECT_CALLS = {
    "print", "write", "send", "emit", "log", "save",
    "append", "insert", "update", "delete", "remove",
    "exit", "sys.exit",
}


# ── Low-level helpers ──────────────────────────────────────────────────────

def _text(node, src: bytes) -> str:
    return src[node.start_byte:node.end_byte].decode("utf-8", errors="replace")


def _walk(node):
    yield node
    for child in node.children:
        yield from _walk(child)


# ── Call graph ─────────────────────────────────────────────────────────────

def _build_call_graph(root, src_bytes: bytes) -> nx.DiGraph:
    G = nx.DiGraph()
    current_func: Optional[str] = None
    for node in _walk(root):
        if node.type == "function_definition":
            n = node.child_by_field_name("name")
            if n:
                current_func = _text(n, src_bytes)
                G.add_node(current_func)
        elif node.type == "call" and current_func:
            fn = node.child_by_field_name("function")
            if fn:
                callee = _text(fn, src_bytes)
                if "." not in callee:
                    G.add_edge(current_func, callee)
    return G


# ── Constant tracker ───────────────────────────────────────────────────────

def _extract_local_constants(body_nodes, src_bytes: bytes) -> dict:
    """
    Scan a function body for simple numeric/string constant assignments
    that appear BEFORE any if-statement.
    e.g. x = 100  →  {"x": 100}
    Used to synthesize virtual outer conditions like "x == 100"
    so Agent 1.5 can detect: x = 100 then if x < 0 → impossible.
    """
    constants = {}
    import re
    for node in body_nodes:
        if node.type == "if_statement":
            # Stop collecting once we hit the first if — 
            # constants defined after ifs are scope-ambiguous
            break
        if node.type == "assignment":
            left  = node.child_by_field_name("left")
            right = node.child_by_field_name("right")
            if left and right and left.type == "identifier":
                var_name  = _text(left,  src_bytes)
                val_text  = _text(right, src_bytes).strip()
                # Only track pure numeric literals or simple expressions
                try:
                    val = eval(val_text, {"__builtins__": {}})
                    if isinstance(val, (int, float)):
                        constants[var_name] = val
                except Exception:
                    pass
    return constants


# ── Nested condition extractor ─────────────────────────────────────────────

def _extract_nested_conditions(root, src_bytes: bytes) -> list[dict]:
    """
    Collect every nested if-condition with its chain of outer conditions.
    Also synthesizes virtual conditions from constant assignments so
    Agent 1.5 can detect: x = 100 → if x < 0 (impossible via constant folding).

    Returns: [{ outer: [str], inner: str, line: int, func: str }]

    Fix 1: Records ALL if-statements that have an outer context, including
           top-level ifs that contain nested ifs (previously skipped).
    Fix 2: Recurses into elif/else branches with correct outer conditions.
    Fix 3: Adds virtual outer conditions from constant assignments so
           constant-folding impossible branches are detected.
    Fix 4: Also emits single if-statements (no nesting) with virtual
           outer conditions from constants, enabling x=100 + if x<0 detection.
    """
    results = []
    current_func = "__module__"

    def walk_conds(node, outer: list, constants: dict):
        nonlocal current_func

        # ── Enter function — reset outer conditions and collect constants ──
        if node.type == "function_definition":
            n = node.child_by_field_name("name")
            current_func = _text(n, src_bytes) if n else "unknown"
            body = node.child_by_field_name("body")
            if body:
                # Collect constants from the function body before any if
                local_consts = _extract_local_constants(body.children, src_bytes)
                # Build virtual outer conditions from constants
                # e.g. x = 100  →  virtual outer: "x == 100"
                virtual_outers = [
                    f"{var} == {val}" for var, val in local_consts.items()
                ]
                for child in body.children:
                    walk_conds(child, virtual_outers, local_consts)
            return

        # ── if_statement ───────────────────────────────────────────────────
        if node.type == "if_statement":
            cond = node.child_by_field_name("condition")
            if cond:
                cond_text = _text(cond, src_bytes)

                # FIX 1: Always record if there are outer conditions,
                # whether they come from real nesting OR virtual constants
                if outer:
                    results.append({
                        "outer": outer[:],
                        "inner": cond_text,
                        "line":  cond.start_point[0] + 1,
                        "func":  current_func,
                    })

                # FIX 2: Recurse into the consequence (if body)
                consequence = node.child_by_field_name("consequence")
                if consequence:
                    for child in consequence.children:
                        walk_conds(child, outer + [cond_text], constants)

                # FIX 2: Recurse into elif / else with the ORIGINAL outer
                # (not outer + cond_text, because elif is a sibling not a child)
                alternative = node.child_by_field_name("alternative")
                if alternative:
                    # alternative is an elif_clause or else_clause
                    if alternative.type == "elif_clause":
                        elif_cond = alternative.child_by_field_name("condition")
                        if elif_cond:
                            elif_text = _text(elif_cond, src_bytes)
                            if outer:
                                results.append({
                                    "outer": outer[:],
                                    "inner": elif_text,
                                    "line":  elif_cond.start_point[0] + 1,
                                    "func":  current_func,
                                })
                            elif_body = alternative.child_by_field_name("consequence")
                            if elif_body:
                                for child in elif_body.children:
                                    walk_conds(child, outer + [elif_text], constants)
                        # Chain to next elif/else
                        next_alt = alternative.child_by_field_name("alternative")
                        if next_alt:
                            walk_conds(next_alt, outer, constants)
                    else:
                        # plain else clause — recurse with same outer
                        for child in alternative.children:
                            walk_conds(child, outer, constants)
            return

        # ── Default: recurse into children ────────────────────────────────
        for child in node.children:
            walk_conds(child, outer, constants)

    walk_conds(root, [], {})
    return results


# ── LangGraph node ─────────────────────────────────────────────────────────

def parse_node(state: AgentState) -> AgentState:
    print("[Agent 1] Parsing:", state["filepath"])

    with open(state["filepath"], "rb") as f:
        src_bytes = f.read()

    source = src_bytes.decode("utf-8", errors="replace")
    tree   = _parser.parse(src_bytes)
    root   = tree.root_node

    assignments:  list[Assignment] = []
    output_nodes: list[OutputNode] = []

    for node in _walk(root):

        if node.type == "assignment":
            left  = node.child_by_field_name("left")
            right = node.child_by_field_name("right")
            if left and right:
                for n in _walk(left):
                    if n.type == "identifier":
                        assignments.append(Assignment(
                            name=_text(n, src_bytes),
                            line=n.start_point[0] + 1,
                            value_text=_text(right, src_bytes),
                        ))

        elif node.type == "augmented_assignment":
            left  = node.child_by_field_name("left")
            right = node.child_by_field_name("right")
            if left and right and left.type == "identifier":
                assignments.append(Assignment(
                    name=_text(left, src_bytes),
                    line=left.start_point[0] + 1,
                    value_text=_text(right, src_bytes),
                ))

        elif node.type == "return_statement":
            output_nodes.append(OutputNode(
                kind="return",
                line=node.start_point[0] + 1,
                text=_text(node, src_bytes),
            ))

        elif node.type == "call":
            func_node = node.child_by_field_name("function")
            if func_node:
                fname = _text(func_node, src_bytes)
                if any(fname == s or fname.endswith("." + s)
                       for s in SIDE_EFFECT_CALLS):
                    kind = "print" if fname == "print" else "side_effect"
                    output_nodes.append(OutputNode(
                        kind=kind,
                        line=node.start_point[0] + 1,
                        text=_text(node, src_bytes),
                    ))

    call_graph        = _build_call_graph(root, src_bytes)
    nested_conditions = _extract_nested_conditions(root, src_bytes)

    print(f"[Agent 1] {len(assignments)} assignments, "
          f"{len(output_nodes)} outputs, "
          f"{len(nested_conditions)} nested condition groups, "
          f"{call_graph.number_of_nodes()} functions in call graph")

    return {
        **state,
        "source":              source,
        "assignments":         assignments,
        "output_nodes":        output_nodes,
        "raw_tree":            tree,
        "call_graph":          call_graph,
        "nested_conditions":   nested_conditions,
        "shadowed_vars":       [],
        "impossible_branches": [],
        "error":               None,
    }
