"""
agent1_5_branch.py — Impossible Branch Detector (NEW — most novel node)

Sits between Agent 1 and Agent 2 in the pipeline.
Takes nested conditions extracted by Agent 1 and asks the LLM:
"Can these conditions EVER be true simultaneously?"

This is the semantic invariant detection that no static tool handles.
Examples it catches:
  if age > 65:
      if age < 18:        ← impossible, age can't be both
  
  if status == "active":
      if status == "deleted":  ← impossible, mutually exclusive strings

  if x > 100:
      if x < 0:           ← impossible numeric range

Without an API key, falls back to heuristic pattern matching
for common cases (numeric range contradictions, mutual exclusion).
"""

import os
import re
import json 
from functools import lru_cache
from state import AgentState, ImpossibleBranch

# Cache for LLM calls
_llm_cache = {}

# ── Heuristic patterns (no API needed) ────────────────────────────────────

def _heuristic_impossible(outer: list[str], inner: str) -> tuple[bool, str]:
    """
    Detect obvious impossible conditions without an LLM.
    Returns (is_impossible, reason).
    """
    all_conds = outer + [inner]

    # Pattern 1: numeric contradictions on same variable
    # e.g. "x > 65" and "x < 18"  →  impossible
    gt_pattern = re.compile(r'(\w+)\s*[>]=?\s*(\d+(?:\.\d+)?)')
    lt_pattern = re.compile(r'(\w+)\s*[<]=?\s*(\d+(?:\.\d+)?)')

    lower_bounds: dict[str, float] = {}  # var → minimum value
    upper_bounds: dict[str, float] = {}  # var → maximum value

    for cond in all_conds:
        for m in gt_pattern.finditer(cond):
            var, val = m.group(1), float(m.group(2))
            lower_bounds[var] = max(lower_bounds.get(var, float('-inf')), val)
        for m in lt_pattern.finditer(cond):
            var, val = m.group(1), float(m.group(2))
            upper_bounds[var] = min(upper_bounds.get(var, float('inf')), val)

    for var in set(lower_bounds) & set(upper_bounds):
        lo, hi = lower_bounds[var], upper_bounds[var]
        if lo >= hi:
            return (True,
                f"'{var}' cannot satisfy both {var} > {lo} and {var} < {hi} simultaneously")

    # Pattern 2: same variable compared to two different string literals
    # e.g. status == "active" and status == "deleted"
    eq_pattern = re.compile(r'(\w+)\s*==\s*["\']([^"\']+)["\']')
    eq_checks: dict[str, list[str]] = {}
    for cond in all_conds:
        for m in eq_pattern.finditer(cond):
            var, val = m.group(1), m.group(2)
            eq_checks.setdefault(var, []).append(val)

    for var, vals in eq_checks.items():
        if len(vals) > 1 and len(set(vals)) > 1:
            return (True,
                f"'{var}' cannot equal both '{vals[0]}' and '{vals[1]}' simultaneously")

    # Pattern 3: x == val and x != val
    neq_pattern = re.compile(r'(\w+)\s*!=\s*["\']([^"\']+)["\']')
    neq_checks: dict[str, list[str]] = {}
    for cond in all_conds:
        for m in neq_pattern.finditer(cond):
            var, val = m.group(1), m.group(2)
            neq_checks.setdefault(var, []).append(val)
    for var, neq_vals in neq_checks.items():
        if var in eq_checks:
            for val in eq_checks[var]:
                if val in neq_vals:
                    return (True,
                        f"'{var}' cannot simultaneously equal and not equal '{val}'")
    
    const_eq: dict[str, float] = {}
    const_pattern = re.compile(r'(\w+)\s*==\s*(\d+(?:\.\d+)?)')
    for cond in all_conds:
        for m in const_pattern.finditer(cond):
            var, val = m.group(1), float(m.group(2))
            const_eq[var] = val

    for var, const_val in const_eq.items():
        # Check if any condition contradicts this constant
        for cond in all_conds:
            for m in gt_pattern.finditer(cond):
                if m.group(1) == var and const_val <= float(m.group(2)):
                    return (True,
                        f"'{var}' is constant {const_val} but condition requires {var} > {m.group(2)}")
            for m in lt_pattern.finditer(cond):
                if m.group(1) == var and const_val >= float(m.group(2)):
                    return (True,
                        f"'{var}' is constant {const_val} but condition requires {var} < {m.group(2)}")

    return (False, "")


# ── LLM-based detection ────────────────────────────────────────────────────

# ── Two separate prompts: detection vs explainability ─────────────────────
# Detection: used when heuristic is unsure — "is this impossible?"
# Explain:   always called when API available — "explain this in plain English"
# This separation is intentional: heuristic handles detection for obvious
# cases (fast, free), LLM always handles the human-facing explanation.

DETECT_SYSTEM = """You are a static analysis assistant detecting impossible code branches.
Given nested Python if-conditions, determine if the inner condition can EVER be
true when all outer conditions are already true.

Respond ONLY with valid JSON (no markdown):
{
  "impossible": true | false,
  "confidence": "HIGH" | "MEDIUM" | "LOW",
  "technical_reason": "one sentence technical reason"
}"""

EXPLAIN_SYSTEM = """You are a code review assistant helping developers understand dead code.
A static analyser has confirmed that a nested if-branch is logically impossible —
its conditions can never all be true simultaneously.

Given the conditions and technical reason, produce a developer-friendly explanation.
Respond ONLY with valid JSON (no markdown):
{
  "explanation": "One plain-English sentence explaining why this branch is unreachable, using the variable names from the code.",
  "suggestion": "One sentence telling the developer what to do — e.g. remove the inner if block, or fix the logic."
}"""

def _resolve_provider(api_key: str) -> str:
    """
    Determine which provider to use based on key prefix.
    Groq keys start with 'gsk_'
    Anthropic keys start with 'sk-ant'
    Gemini keys are everything else (long alphanumeric)
    """
    if not api_key:
        return "none"
    if api_key.startswith("gsk_"):
        return "groq"
    if api_key.startswith("sk-ant"):
        return "anthropic"
    # Check env vars as tiebreaker
    if os.environ.get("GROQ_API_KEY"):
        return "groq"
    if os.environ.get("GEMINI_API_KEY"):
        return "gemini"
    return "gemini"  # default fallback

def _call_llm(system: str, prompt: str, api_key: str) -> dict:
    cache_key = (system, prompt)
    if cache_key in _llm_cache:
        return _llm_cache[cache_key]

    provider = _resolve_provider(api_key)
    text = ""

    if provider == "groq":
        # Always use the actual key from env if available
        groq_key = os.environ.get("GROQ_API_KEY") or api_key
        from groq import Groq
        client = Groq(api_key=groq_key)
        response = client.chat.completions.create(
            model="openai/gpt-oss-120b",   # upgraded from 8b
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": prompt}
            ],
            temperature=0.1,   # lower = more deterministic JSON
            max_tokens=512,
        )
        text = response.choices[0].message.content.strip()

    elif provider == "gemini":
        gemini_key = os.environ.get("GEMINI_API_KEY") or api_key
        from google import genai
        from google.genai import types
        client = genai.Client(api_key=gemini_key)
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            config=types.GenerateContentConfig(
                system_instruction=system,
                response_mime_type="application/json",
            ),
            contents=prompt,
        )
        text = response.text.strip()

    elif provider == "anthropic":
        import anthropic
        client = anthropic.Anthropic(api_key=api_key)
        response = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=512,
            system=system,
            messages=[{"role": "user", "content": prompt}],
        )
        text = response.content[0].text.strip()

    else:
        raise ValueError("No valid API key / provider found")

    # Clean and parse
    text = re.sub(r"```json|```", "", text).strip()
    # Extract first JSON object robustly
    match = re.search(r"\{.*?\}", text, re.DOTALL)
    if not match:
        raise ValueError(f"No JSON in LLM response: {text[:200]}")

    result = json.loads(match.group(0))
    _llm_cache[cache_key] = result
    return result

def _llm_detect(outer: list[str], inner: str, api_key: str) -> dict:
    prompt = (
        f"Outer conditions (already confirmed true): {outer}\n"
        f"Inner condition to evaluate: {inner}\n"
        "Can ALL these conditions be simultaneously true in any valid Python program?\n"
        "Think step by step, then respond with JSON only."
    )
    return _call_llm(DETECT_SYSTEM, prompt, api_key)

def _llm_explain(
    outer: list[str], inner: str,
    technical_reason: str,
    func: str,
    api_key: str,
) -> dict:
    """
    Ask LLM for a plain-English explanation + fix suggestion.
    Called for ALL confirmed impossible branches (heuristic OR LLM detected).
    This is purely for explainability — detection already happened.
    """
    prompt = (
        f"Function: {func}\n"
        f"Outer conditions (already true when execution reaches this point): {outer}\n"
        f"Inner condition (the impossible one): {inner}\n"
        f"Technical reason it's impossible: {technical_reason}\n\n"
        f"Write a plain-English explanation a developer would understand, "
        f"and a concrete suggestion for what to do."
    )
    return _call_llm(EXPLAIN_SYSTEM, prompt, api_key)

# ── LangGraph node ─────────────────────────────────────────────────────────

def branch_detect_node(state: AgentState) -> AgentState:
    """
    Agent 1.5 — Impossible Branch Detector

    Two-phase approach:
      Phase 1 — Detection  : heuristic first, LLM fallback if unsure
      Phase 2 — Explanation: LLM always called (if API key available)
                             to generate developer-friendly explanation + suggestion

    Input  state keys : nested_conditions, api_key
    Output state keys : impossible_branches
    """
    nested  = state.get("nested_conditions", [])
    api_key = (
        state.get("api_key")
        or os.environ.get("GROQ_API_KEY")
        or os.environ.get("GEMINI_API_KEY")
        or os.environ.get("ANTHROPIC_API_KEY")
    )

    provider = _resolve_provider(api_key) if api_key else "none"
    print(f"[Agent 1.5] Provider resolved: {provider} | Checking {len(nested)} condition groups...")

    impossible: list[ImpossibleBranch] = []

    for group in nested:
        outer = group["outer"]
        inner = group["inner"]
        line  = group["line"]
        func  = group["func"]

        # ── Phase 1: Detection ─────────────────────────────────────────
        is_impossible, technical_reason = _heuristic_impossible(outer, inner)
        detected_by = "heuristic"

        if not is_impossible and api_key:
            # Heuristic couldn't confirm — escalate to LLM
            try:
                result       = _llm_detect(outer, inner, api_key)
                is_impossible = result.get("impossible", False)
                technical_reason = result.get("technical_reason", "Logically impossible")
                detected_by  = "LLM"
            except Exception as e:
                print(f"  [Agent 1.5] Detection LLM error line {line}: {e}")

        if not is_impossible:
            continue

        print(f"  [Agent 1.5] IMPOSSIBLE ({detected_by}) line {line}: {inner[:50]}")

        # ── Phase 2: Explainability ────────────────────────────────────
        # Always call LLM for the human-facing explanation + suggestion
        # even if heuristic already confirmed it was impossible.
        explanation = technical_reason   # fallback if no API key
        suggestion  = "Remove the inner if block — it can never execute."

        if api_key and provider!="none":
            try:
                explain = _llm_explain(
                    outer, inner, technical_reason, func, api_key
                )
                explanation = explain.get("explanation", technical_reason)
                suggestion  = explain.get("suggestion", suggestion)
                print(f"  [Agent 1.5] Explanation generated by LLM for line {line}")
            except Exception as e:
                print(f"  [Agent 1.5] Explain LLM error line {line}: {e}")

        impossible.append(ImpossibleBranch(
            outer_conditions=outer,
            inner_condition=inner,
            line=line,
            func=func,
            explanation=explanation,
            confidence="HIGH" if detected_by == "heuristic" else "MEDIUM",
        ))

    print(f"[Agent 1.5] Found {len(impossible)} impossible branches")
    return {**state, "impossible_branches": impossible}
    