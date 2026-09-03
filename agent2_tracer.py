"""
agent2_tracer.py — Data Flow Tracer Node
LangGraph node: reads AST from state, writes DFG + dead_vars + live_vars.
"""

import re
import networkx as nx
from z3 import *
from functools import lru_cache

from state import AgentState, Assignment, DeadVariable, ShadowedVar

OUTPUT_SENTINEL = "__OUTPUT__"
INPUT_SENTINEL  = "__INPUT__"

# Cache for symbolic checks
_symbolic_cache = {}


# ── Helpers ────────────────────────────────────────────────────────────────

def _walk(node):
    yield node
    for child in node.children:
        yield from _walk(child)


def _text(node, src: bytes) -> str:
    return src[node.start_byte:node.end_byte].decode("utf-8", errors="replace")


BUILTINS = {
    "True","False","None","print","range","len","type",
    "int","str","float","list","dict","set","tuple",
    "enumerate","zip","map","filter","sorted","reversed",
    "open","super","self","cls",
}

KEYWORDS = {
    "if","else","elif","for","while","in","not","and","or",
    "True","False","None","return","def","class","import",
    "from","as","pass","break","continue","lambda","with",
}


def _refs(node, src: bytes) -> list[str]:
    return [
        _text(n, src) for n in _walk(node)
        if n.type == "identifier" and _text(n, src) not in BUILTINS
    ]


def _regex_names(text: str) -> list[str]:
    return [m for m in re.findall(r'\b([a-zA-Z_]\w*)\b', text)
            if m not in KEYWORDS]


# ── Symbolic Execution Helpers ─────────────────────────────────────────────

def _symbolic_check_condition(condition: str, context_vars: dict) -> str:
    """
    Use Z3 to check if a condition is always true, always false, or satisfiable.
    Returns: 'always_true', 'always_false', 'satisfiable', or 'unknown'
    """
    cache_key = (condition, tuple(sorted(context_vars.items())))
    if cache_key in _symbolic_cache:
        return _symbolic_cache[cache_key]
    
    try:
        solver = Solver()
        # Create symbolic variables for context
        sym_vars = {}
        for var in context_vars:
            if var not in ['True', 'False', 'None']:
                sym_vars[var] = Int(var)  # Assume integers for simplicity

        # Parse condition (basic support for ==, !=, <, >, <=, >=)
        cond_expr = _parse_condition_to_z3(condition, sym_vars)
        if cond_expr is None:
            result = 'unknown'
        else:
            # Check if always true
            solver.push()
            solver.add(Not(cond_expr))
            if solver.check() == unsat:
                result = 'always_true'
            else:
                solver.pop()
                # Check if always false
                solver.push()
                solver.add(cond_expr)
                if solver.check() == unsat:
                    result = 'always_false'
                else:
                    solver.pop()
                    # Check if satisfiable
                    if solver.check() == sat:
                        result = 'satisfiable'
                    else:
                        result = 'unknown'
        
        _symbolic_cache[cache_key] = result
        return result
    except:
        _symbolic_cache[cache_key] = 'unknown'
        return 'unknown'


def _parse_condition_to_z3(cond: str, sym_vars: dict):
    """Basic parser for conditions to Z3 expressions."""
    cond = cond.strip()
    if '==' in cond:
        left, right = cond.split('==', 1)
        l = _parse_expr(left.strip(), sym_vars)
        r = _parse_expr(right.strip(), sym_vars)
        return l == r if l and r else None
    elif '!=' in cond:
        left, right = cond.split('!=', 1)
        l = _parse_expr(left.strip(), sym_vars)
        r = _parse_expr(right.strip(), sym_vars)
        return l != r if l and r else None
    elif '<=' in cond:
        left, right = cond.split('<=', 1)
        l = _parse_expr(left.strip(), sym_vars)
        r = _parse_expr(right.strip(), sym_vars)
        return l <= r if l and r else None
    elif '>=' in cond:
        left, right = cond.split('>=', 1)
        l = _parse_expr(left.strip(), sym_vars)
        r = _parse_expr(right.strip(), sym_vars)
        return l >= r if l and r else None
    elif '<' in cond:
        left, right = cond.split('<', 1)
        l = _parse_expr(left.strip(), sym_vars)
        r = _parse_expr(right.strip(), sym_vars)
        return l < r if l and r else None
    elif '>' in cond:
        left, right = cond.split('>', 1)
        l = _parse_expr(left.strip(), sym_vars)
        r = _parse_expr(right.strip(), sym_vars)
        return l > r if l and r else None
    return None


def _parse_expr(expr: str, sym_vars: dict):
    """Parse simple expressions to Z3."""
    expr = expr.strip()
    if expr in sym_vars:
        return sym_vars[expr]
    try:
        return int(expr)
    except:
        return None


# ── LangGraph node function ────────────────────────────────────────────────

def trace_node(state: AgentState) -> AgentState:
    """
    Agent 2 — Data Flow Tracer
    Input  state keys : source, assignments, output_nodes, raw_tree
    Output state keys : dfg, dead_vars, live_vars
    """
    print("[Agent 2] Building data flow graph...")

    src_bytes   = state["source"].encode("utf-8", errors="replace")
    root        = state["raw_tree"].root_node
    assignments = state["assignments"]
    outputs     = state["output_nodes"]

    G = nx.DiGraph()
    G.add_node(OUTPUT_SENTINEL)
    G.add_node(INPUT_SENTINEL)

    # Pre-walk tree to collect all relevant nodes for efficiency
    all_nodes = list(_walk(root))
    
    # Step 1 — function parameters are always live
    func_params: set[str] = set()
    for node in all_nodes:
        if node.type == "function_definition":
            params = node.child_by_field_name("parameters")
            if params:
                for pn in _walk(params):
                    if pn.type == "identifier":
                        p = _text(pn, src_bytes)
                        func_params.add(p)
                        G.add_node(p)
                        G.add_edge(INPUT_SENTINEL, p)

    # Step 2 — assignments: RHS names → LHS name
    assign_dict = {a.line: a for a in assignments}
    for node in all_nodes:
        if node.type in ("assignment", "augmented_assignment") and node.start_point[0] + 1 in assign_dict:
            assign = assign_dict[node.start_point[0] + 1]
            G.add_node(assign.name)
            right = node.child_by_field_name("right")
            if right:
                rhs_refs = _refs(right, src_bytes)
                for ref in rhs_refs:
                    if ref != assign.name:
                        G.add_node(ref)
                        G.add_edge(ref, assign.name)

    # Step 3 & 4 — outputs and calls → OUTPUT_SENTINEL
    output_lines = {o.line: o for o in outputs}
    for node in all_nodes:
        if node.start_point[0] + 1 in output_lines:
            output = output_lines[node.start_point[0] + 1]
            if (output.kind == "return" and node.type == "return_statement") or \
               (node.type == "call" and _text(node.child_by_field_name("function") or node, src_bytes) in SIDE_EFFECT_NAMES):
                used = _refs(node, src_bytes)
                for name in used:
                    G.add_node(name)
                    G.add_edge(name, OUTPUT_SENTINEL)
        elif node.type == "call":
            args = node.child_by_field_name("arguments")
            if args:
                for name in _refs(args, src_bytes):
                    if G.has_node(name):
                        G.add_edge(name, OUTPUT_SENTINEL)

    # Step 4.5 — prune unreachable nodes in the graph
    G = _prune_graph(G)

    # Step 5 — classify dead vs live
    dead_vars:  list[DeadVariable] = []
    live_vars:  list[str]          = []
    assigned    = {a.name: a for a in assignments}

    for var, assign in assigned.items():
        if var in func_params or var in (OUTPUT_SENTINEL, INPUT_SENTINEL):
            live_vars.append(var)
            continue

        if G.has_node(var) and nx.has_path(G, var, OUTPUT_SENTINEL):
            live_vars.append(var)
        else:
            dead_vars.append(DeadVariable(
                name=var,
                line=assign.line,
                value_text=assign.value_text,
                reason=_dead_reason(var, G),
                confidence=_confidence(var, assign, G),
            ))

    print(f"[Agent 2] {len(live_vars)} live, {len(dead_vars)} dead variables found")

    # ── Step 6: detect shadowed assignments ──────────────────────────────
    shadowed = _find_shadowed_assignments(state["assignments"], root, src_bytes)
    print(f"[Agent 2] {len(shadowed)} shadowed assignments found")

    # ── Step 7: LLM explainability for shadowed vars ──────────────────────
    import os
    api_key = state.get("api_key") or os.environ.get("GEMINI_API_KEY") or os.environ.get("ANTHROPIC_API_KEY")
    if api_key and shadowed:
        shadowed = _explain_shadowed(shadowed, state["source"], api_key)

    return {
        **state,
        "dfg":          G,
        "dead_vars":    dead_vars,
        "live_vars":    live_vars,
        "shadowed_vars": shadowed,
    }


# ── Helpers ────────────────────────────────────────────────────────────────

def _rhs_refs(assign: Assignment, root, src_bytes: bytes) -> list[str]:
    target_line = assign.line - 1
    for node in _walk(root):
        if node.type in ("assignment", "augmented_assignment"):
            if node.start_point[0] == target_line:
                right = node.child_by_field_name("right")
                if right:
                    return _refs(right, src_bytes)
    return _regex_names(assign.value_text)


def _find_output_node(output, root, src_bytes: bytes):
    target_line = output.line - 1
    for node in _walk(root):
        if node.start_point[0] == target_line:
            if output.kind == "return" and node.type == "return_statement":
                return node
            if node.type == "call":
                fn = node.child_by_field_name("function")
                if fn and _text(fn, src_bytes) in SIDE_EFFECT_NAMES:
                    return node
    return None

SIDE_EFFECT_NAMES = {
    "print","write","send","emit","log","save",
    "append","insert","update","delete",
}

CONSTANT_RE = re.compile(
    r'^(\d+(\.\d+)?|"[^"]*"|\'[^\']*\'|True|False|None|\[\]|\{\}|\(\))$'
)

def _confidence(name: str, assign: Assignment, G: nx.DiGraph) -> str:
    out = list(G.successors(name)) if G.has_node(name) else []
    if CONSTANT_RE.match(assign.value_text.strip()) or not out:
        return "HIGH"
    return "MEDIUM"


def _dead_reason(name: str, G: nx.DiGraph) -> str:
    out = list(G.successors(name)) if G.has_node(name) else []
    if not out:
        return f"'{name}' is assigned but never read by any other expression"
    return (f"'{name}' is used in intermediate calculations "
            f"but no path leads to a return, print, or side-effecting call")


def _prune_graph(G: nx.DiGraph) -> nx.DiGraph:
    """
    Prune the data flow graph by removing nodes that have no path to OUTPUT_SENTINEL.
    This eliminates dead branches in the graph.
    """
    reachable = set(nx.descendants(G, INPUT_SENTINEL))
    reachable.add(INPUT_SENTINEL)
    reachable.add(OUTPUT_SENTINEL)
    
    # Only keep nodes that are reachable from input or lead to output
    to_remove = []
    for node in G.nodes():
        if node not in reachable and not nx.has_path(G, node, OUTPUT_SENTINEL):
            to_remove.append(node)
    
    G_pruned = G.copy()
    G_pruned.remove_nodes_from(to_remove)
    return G_pruned


def _find_shadowed_assignments(
    assignments: list[Assignment],
    root,
    src_bytes: bytes,
) -> list:
    """
    Detect variables whose first write is overwritten before being read.

    Algorithm per function scope:
      1. Walk assignments in line order
      2. For each variable, track its write lines
      3. Between two consecutive writes, check if any READ of that variable occurs
      4. If no read between write_1 and write_2 → write_1 is shadowed (dead)

    This catches Case 1: base_discount = price*0.05 immediately overwritten.
    """
    from state import ShadowedVar

    # Group assignments by (variable_name, enclosing_function)
    # We need enclosing function to scope correctly
    func_for_line: dict[int, str] = {}
    current_func = "__module__"
    for node in _walk(root):
        if node.type == "function_definition":
            n = node.child_by_field_name("name")
            if n:
                current_func = _text(n, src_bytes)
        if node.type in ("assignment", "augmented_assignment"):
            func_for_line[node.start_point[0] + 1] = current_func

    # Group writes by (var, func)
    from collections import defaultdict
    writes: dict[tuple, list[Assignment]] = defaultdict(list)
    for a in sorted(assignments, key=lambda x: x.line):
        func = func_for_line.get(a.line, "__module__")
        writes[(a.name, func)].append(a)

    # For each variable with 2+ writes in same function, check reads between writes
    shadowed: list[ShadowedVar] = []

    for (var, func), write_list in writes.items():
        if len(write_list) < 2:
            continue

        for i in range(len(write_list) - 1):
            w1 = write_list[i]
            w2 = write_list[i + 1]

            # Check if var is read between line w1 and line w2
            read_between = _is_read_between(var, w1.line, w2.line, root, src_bytes)
            if not read_between:
                shadowed.append(ShadowedVar(
                    name=var,
                    first_write_line=w1.line,
                    first_write_value=w1.value_text,
                    overwrite_line=w2.line,
                    func=func,
                ))

    return shadowed


def _is_read_between(var: str, start_line: int, end_line: int, root, src_bytes: bytes) -> bool:
    """
    Return True if `var` appears as an identifier on the RHS of any expression
    strictly between start_line and end_line (exclusive).
    """
    for node in _walk(root):
        line = node.start_point[0] + 1
        if line <= start_line or line >= end_line:
            continue
        # A read is: identifier not on the LHS of an assignment
        if node.type == "identifier" and _text(node, src_bytes) == var:
            parent = node.parent
            if parent and parent.type == "assignment":
                left = parent.child_by_field_name("left")
                # If this identifier IS the left side, it's a write not a read
                if left and node.start_byte >= left.start_byte and node.end_byte <= left.end_byte:
                    continue
            return True
    return False


# ── Option C hook ──────────────────────────────────────────────────────────

def merge_with_call_graph(dfg: nx.DiGraph, call_graph: nx.DiGraph) -> nx.DiGraph:
    combined = nx.compose(dfg, call_graph)
    output_callers = {
        src for src, dst in call_graph.edges()
        if dst in ("print","write","send","emit","log","save")
    }
    for fn in output_callers:
        combined.add_edge(fn, OUTPUT_SENTINEL)
    return combined


# ── LLM explainability for shadowed assignments ────────────────────────────

SHADOW_EXPLAIN_SYSTEM = """You are an expert code reviewer identifying wasted assignments in Python code.
A variable has been assigned a value that is immediately overwritten before being read —
the first assignment is completely wasted and has zero effect on program behaviour.

Reason through it step by step before writing your answer:
  1. What value was assigned first, and what value overwrote it?
  2. Is there a path where the first value could ever matter? (If not, confirm it's dead.)
  3. Why do you think this happened — logic error, copy-paste, unnecessary initialisation?
  4. What is the concrete impact: does this waste CPU cycles, mislead future readers, or hide a bug?

Then produce your structured output.
Respond ONLY with valid JSON (no markdown):
{
  "explanation": "2-3 sentences. Explain what value was assigned, what overwrote it, and why the first write has zero effect. Reference the actual variable name, values, and line numbers.",
  "suggestion": "1-2 sentences. Tell the developer specifically what to remove or restructure. If it looks like a logic bug (e.g. the developer forgot to use the initial value), flag that explicitly."
}"""


def _call_with_retry(fn, max_retries=3):
    """Call fn(), retrying up to max_retries times on 429 with exponential backoff."""
    import time
    for attempt in range(max_retries):
        try:
            return fn()
        except Exception as e:
            if "429" in str(e) and attempt < max_retries - 1:
                wait = 2 ** (attempt + 1)
                print(f"    [rate limit] waiting {wait}s before retry {attempt+2}/{max_retries}...")
                time.sleep(wait)
            else:
                raise


def _explain_shadowed(shadowed: list, source: str, api_key: str) -> list:
    """
    Call the LLM to generate plain-English explanation + suggestion
    for each shadowed assignment. Returns updated list with filled fields.
    """
    import os, json, re as re2

    groq_key   = os.environ.get("GROQ_API_KEY")
    gemini_key = os.environ.get("GEMINI_API_KEY")

    # Groq first, Gemini fallback
    if groq_key:
        use_groq   = True
        use_gemini = False
    elif gemini_key:
        use_groq   = False
        use_gemini = True
    else:
        use_groq   = False
        use_gemini = False
    
    lines = source.splitlines()
    results = []

    for s in shadowed:
        # Build source snippet around first write + overwrite
        start = max(0, s.first_write_line - 2)
        end   = min(len(lines), s.overwrite_line + 1)
        snippet = "\n".join(f"  {i+1}: {lines[i]}" for i in range(start, end))

        prompt = (
            f"Function: {s.func}\n"
            f"Variable: {s.name}\n"
            f"First assignment (line {s.first_write_line}): {s.name} = {s.first_write_value}\n"
            f"Overwritten at line {s.overwrite_line} before being read.\n"
            f"Source context:\n{snippet}\n\n"
            f"Explain why this first assignment is wasted and what the developer should do."
        )

        def _make_call():
                if use_groq:
                    from groq import Groq
                    client = Groq(api_key=os.environ.get("GROQ_API_KEY"))
                    response = client.chat.completions.create(
                        model="openai/gpt-oss-20b",
                        messages=[
                            {"role": "system", "content": SHADOW_EXPLAIN_SYSTEM},
                            {"role": "user", "content": prompt}
                        ],
                        temperature=0.3,
                    )
                    return re2.sub(r"```json|```", "", response.choices[0].message.content).strip()
                elif use_gemini:
                    from google import genai
                    from google.genai import types
                    client   = genai.Client(api_key=api_key)
                    response = client.models.generate_content(
                        model="gemini-2.5-flash",
                        config=types.GenerateContentConfig(
                            system_instruction=SHADOW_EXPLAIN_SYSTEM,
                            response_mime_type="application/json",
                        ),
                        contents=prompt,
                    )
                    return re2.sub(r"```json|```", "", response.text).strip()
                else:
                    import anthropic
                    client   = anthropic.Anthropic(api_key=api_key)
                    response = client.messages.create(
                        model="claude-sonnet-4-20250514",
                        max_tokens=600,
                        system=SHADOW_EXPLAIN_SYSTEM,
                        messages=[{"role": "user", "content": prompt}],
                    )
                    return re2.sub(r"```json|```", "", response.content[0].text).strip()

        try:
            text   = _call_with_retry(_make_call)
            parsed = json.loads(text)
            s.explanation = parsed.get("explanation", "")
            s.suggestion  = parsed.get("suggestion", "")
            print(f"  [Agent 2] LLM explanation for shadowed '{s.name}' at line {s.first_write_line}")

        except Exception as e:
            print(f"  [Agent 2] LLM explain error for '{s.name}': {e}")
            s.explanation = f"'{s.name}' is assigned at line {s.first_write_line} but overwritten at line {s.overwrite_line} before being read."
            s.suggestion  = "Remove the first assignment or use the value before overwriting."

        results.append(s)

    return results
