"""
agent3_reasoner.py — Gemini Logic Reasoner Node (BATCHED VERSION)
"""
import os
import json
from google import genai
from google.genai import types
from typing import TypedDict, List
from state import AgentState, DeadVariable, Verdict

MAX_RETRIES = 2

# ── Updated Schema for Batching ───────────────────────────────────────────
class SingleVerdict(TypedDict):
    variable: str
    severity: str    # "HIGH", "MEDIUM", "LOW"
    explanation: str
    suggestion: str
    confidence: str  # "HIGH", "MEDIUM", "LOW"

class BatchVerdictSchema(TypedDict):
    results: List[SingleVerdict]

SYSTEM_PROMPT = """You are a static analysis assistant specializing in dead logic detection.
I will provide a list of variables flagged as dead logic. 
For EACH variable, confirm if it is truly dead and provide a structured verdict.

Severity guide:
  HIGH   = clearly dead, safe to delete immediately
  MEDIUM = probably dead, but review before deleting  
  LOW    = might be intentional (e.g. debug scaffold)

Return the results as a list under the key 'results'."""

def _fetch_parent_function_context(state: AgentState, var_name: str) -> str:
    """Tool: Fetch the parent function's logic for more context."""
    tree = state['raw_tree']
    root = tree.root_node  # Get the root node from the Tree object
    source = state['source']
    lines = source.splitlines()
    
    # Find the function containing the variable
    for node in _walk(root):
        if node.type == "function_definition":
            func_start = node.start_point[0] + 1
            func_end = node.end_point[0] + 1
            func_body = "\n".join(lines[func_start-1:func_end])
            if var_name in func_body:
                return f"Parent function context:\n{func_body}"
    return "No parent function context found."

def _walk(node):
    yield node
    for child in node.children:
        yield from _walk(child)

def reason_node(state: AgentState) -> AgentState:
    api_key = state.get("api_key") or os.environ.get("GEMINI_API_KEY")
    dead_vars = state["dead_vars"]
    retry_count = state.get("retry_count", 0)

    if not dead_vars:
        return {**state, "verdicts": [], "needs_retry": False}

    if not api_key:
        print("[Agent 3] No API key — falling back to heuristic")
        return {**state, "verdicts": [_heuristic_verdict(d) for d in dead_vars], "needs_retry": False}

    client = genai.Client(api_key=api_key)
    
    # 1. Build a single combined prompt for all dead variables
    full_context = "Please analyze the following detected dead variables:\n\n"
    for d in dead_vars:
        full_context += _build_context(d, state) + "\n" + "---" + "\n"

    try:
        print(f"[Agent 3] Sending batch of {len(dead_vars)} variables to Gemini...")
        response = client.models.generate_content(
            model="gemini-3.1-pro-preview", 
            config=types.GenerateContentConfig(
                system_instruction=SYSTEM_PROMPT,
                # We expect a list of verdicts now
                response_mime_type="application/json",
                response_schema=BatchVerdictSchema
            ),
            contents=full_context
        )
        print(f"[Agent 3] replied with: {response.text[:50]}...")
        # 2. Parse the batch response
        batch_result = response.parsed  # This is a dict like {'results': [...]}
        verdict_map = {res["variable"]: res for res in batch_result["results"]}
        
        final_verdicts = []
        low_confidence_count = 0

        # 3. Map the LLM results back to our DeadVariable objects
        for dead in dead_vars:
            res = verdict_map.get(dead.name)
            if res:
                final_verdicts.append(Verdict(
                    variable=dead.name,
                    line=dead.line,
                    severity=res["severity"],
                    explanation=res["explanation"],
                    suggestion=res["suggestion"],
                    confidence=res["confidence"],
                    retried=(retry_count > 0)
                ))
                if res["confidence"] == "LOW":
                    low_confidence_count += 1
            else:
                # Fallback if Gemini missed one in the list
                final_verdicts.append(_heuristic_verdict(dead))

        needs_retry = (low_confidence_count > len(dead_vars) / 2 and retry_count < MAX_RETRIES)

        return {
            **state,
            "verdicts": final_verdicts,
            "needs_retry": needs_retry,
            "retry_count": retry_count + 1,
        }

    except Exception as e:
        print(f"  [Agent 3] Critical Batch Error: {e}")
        # If the whole batch fails (e.g. still 429), fall back for everything
        return {
            **state, 
            "verdicts": [_heuristic_verdict(d) for d in dead_vars], 
            "needs_retry": False
        }

def _build_context(dead: DeadVariable, state: AgentState) -> str:
    lines = state["source"].splitlines()
    start, end = max(0, dead.line - 2), min(len(lines), dead.line + 2)  # Reduced context
    snippet = "\n".join(f"  {i+1}: {lines[i]}" for i in range(start, end))
    parent_ctx = _fetch_parent_function_context(state, dead.name)
    # Truncate parent context if too long
    if len(parent_ctx) > 500:
        parent_ctx = parent_ctx[:500] + "..."
    return (f"Variable: {dead.name}\n"
            f"Line {dead.line}: {dead.name} = {dead.value_text}\n"
            f"Reason: {dead.reason}\n"
            f"Snippet:\n{snippet}\n"
            f"{parent_ctx}\n")

def _heuristic_verdict(dead: DeadVariable) -> Verdict:
    return Verdict(dead.name, dead.line, "MEDIUM", dead.reason, "Review manually.", "LOW")

def confidence_router(state: AgentState) -> str:
    return "retry" if state.get("needs_retry", False) else "done"