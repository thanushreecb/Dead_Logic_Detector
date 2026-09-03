"""
agent3_reasoner.py — Groq Logic Reasoner Node (FINAL STABLE)
"""
import os
import json
import re
from typing import TypedDict, List
from state import AgentState, DeadVariable, Verdict

try:
    from groq import Groq
    _groq_available = True
except ImportError:
    _groq_available = False

MAX_RETRIES = 2

# ── Schema ───────────────────────────────────────────
class SingleVerdict(TypedDict):
    variable: str
    severity: str
    explanation: str
    suggestion: str
    confidence: str

# ── STRICT PROMPT ────────────────────────────────────
SYSTEM_PROMPT = """You are a precise static analysis assistant specializing in dead logic detection.
I will provide a list of variables flagged as potentially dead. For EACH variable, confirm if it is truly dead and assign a calibrated severity.

════════════════════════════════════════
SEVERITY CLASSIFICATION RULES (read carefully):
════════════════════════════════════════

HIGH — The variable is unambiguously dead:
  • Assigned once and NEVER read, used in an expression, passed to a function, or returned anywhere in the function
  • Part of a calculation chain (a → b → c) where NO variable in the chain reaches a return/print/side-effect
  • Examples: `x = 10` and x never appears again; `total = a + b` where total is never used

MEDIUM — Probably dead, but warrants a second look:
  • The variable NAME suggests it was debug scaffolding (e.g. names containing: trace, debug, internal, api_version, token, tag, scaffold, temp, tmp, log)
  • The variable is used only within another dead chain (indirect deadness)
  • The assignment is inside a try/except or conditional path that makes it hard to be certain

LOW — Possibly intentional, least confident:
  • The variable is only consumed by another variable that is itself dead (dead-chain leaf)
  • The variable name suggests future use or placeholder (e.g. TODO, placeholder, reserved)
  • The variable appears in a loop or generator context where deadness is subtle

════════════════════════════════════════
CONFIDENCE FIELD:
════════════════════════════════════════
  HIGH   = you are certain about this verdict
  MEDIUM = you are fairly sure but there is some ambiguity
  LOW    = you are guessing; the context is insufficient

════════════════════════════════════════
STRICT OUTPUT RULES:
════════════════════════════════════════
- Return ONLY valid JSON — no preamble, no explanation, no markdown fences
- Every variable provided MUST appear in the results array
- DO NOT skip any variable even if you are unsure — use LOW severity + LOW confidence if uncertain

Format:
{
  "results": [
    {
      "variable": "name",
      "severity": "HIGH",
      "explanation": "One sentence explaining why this variable is dead and what it was supposed to do.",
      "suggestion": "One concrete action: either delete the assignment or explain what to fix.",
      "confidence": "HIGH"
    }
  ]
}
"""

# ── TREE WALK ────────────────────────────────────────
def _walk(node):
    yield node
    for child in node.children:
        yield from _walk(child)

# ── CONTEXT FETCH — now returns once, not per-variable ───────────────────
def _fetch_full_function_once(state: AgentState) -> str:
    """
    Returns the first function body that contains any dead variable.
    Called ONCE per batch — not per variable — to avoid token explosion.
    """
    tree   = state['raw_tree']
    root   = tree.root_node
    source = state['source']
    lines  = source.splitlines()
    dead_vars = state["dead_vars"]

    # Collect all dead variable names for membership check
    dead_names = {d.name for d in dead_vars}

    for node in _walk(root):
        if node.type == "function_definition":
            func_start = node.start_point[0]
            func_end   = node.end_point[0] + 1
            func_body  = "\n".join(lines[func_start:func_end])
            # Only include function if it contains at least one dead var
            if any(name in func_body for name in dead_names):
                numbered = "\n".join(
                    f"{i+1}: {lines[i]}" for i in range(func_start, func_end)
                )
                # Cap at 1200 chars — enough for 70b, avoids token explosion
                if len(numbered) > 1200:
                    numbered = numbered[:1200] + "\n... (truncated)"
                return numbered

    # Fallback: top of file
    fallback = "\n".join(f"{i+1}: {lines[i]}" for i in range(min(40, len(lines))))
    return fallback

# ── NAMING PATTERN HINT ──────────────────────────────
DEBUG_PATTERNS = [
    "trace", "debug", "internal", "api_version", "token",
    "tag", "scaffold", "tmp", "temp", "log", "stub", "mock"
]

def _severity_hint(var_name: str, reason: str) -> str:
    name_lower = var_name.lower()
    if any(p in name_lower for p in DEBUG_PATTERNS):
        return "HINT: Variable name matches debug/scaffold pattern → lean toward MEDIUM severity."
    if "chain" in reason.lower() or "intermediate" in reason.lower():
        return "HINT: Part of a dead calculation chain → HIGH if the entire chain is dead, LOW if only a leaf."
    return ""

def _resolve_provider_reasoner() -> str:
    """
    Try Groq first. If key missing or Groq unavailable, fall back to Gemini.
    Returns 'groq', 'gemini', or 'none'.
    """
    groq_key = os.environ.get("GROQ_API_KEY")
    if groq_key and _groq_available:
        try:
            # Lightweight check: just instantiate client, don't call API yet
            Groq(api_key=groq_key)
            return "groq"
        except Exception:
            print("[Agent 3] Groq init failed — falling back to Gemini")

    if os.environ.get("GEMINI_API_KEY"):
        return "gemini"

    return "none"

# ── MAIN NODE ────────────────────────────────────────
def reason_node(state: AgentState) -> AgentState:
    api_key = state.get("api_key") or os.environ.get("GROQ_API_KEY")
    dead_vars = state["dead_vars"]
    retry_count = state.get("retry_count", 0)

    if not dead_vars:
        return {**state, "verdicts": [], "needs_retry": False}

    if not api_key:
        print("[Agent 3] No API key — heuristic fallback")
        return {**state, "verdicts": [_heuristic_verdict(d) for d in dead_vars], "needs_retry": False}

    # ── Fetch function context ONCE for the whole batch ──────────────────
    function_context = _fetch_full_function_once(state)

    # ── Build prompt: function body once at top, minimal snippet per var ─
    full_context = (
        f"Here is the full function for reference (read once):\n\n"
        f"{function_context}\n\n"
        f"{'=' * 40}\n"
        f"Now analyze these {len(dead_vars)} variables from the function above. "
        f"Apply the severity rules from the system prompt carefully.\n\n"
    )
    for d in dead_vars:
        full_context += _build_context_minimal(d, state) + "\n---\n"

    batch_text = ""
    try:
        provider = _resolve_provider_reasoner()
        print(f"[Agent 3] Provider: {provider} | Sending batch of {len(dead_vars)} variables...")

        if provider == "groq":
            client = Groq(api_key=os.environ["GROQ_API_KEY"])
            response = client.chat.completions.create(
                model="openai/gpt-oss-120b",
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": full_context}
                ],
                temperature=0.2,
                max_tokens=4096,
            )
            batch_text = response.choices[0].message.content.strip()

        elif provider == "gemini":
            from google import genai
            from google.genai import types
            client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
            response = client.models.generate_content(
                model="gemini-2.5-flash",
                config=types.GenerateContentConfig(
                    system_instruction=SYSTEM_PROMPT,
                    response_mime_type="application/json",
                ),
                contents=full_context,
            )
            batch_text = response.text.strip()

        else:
            raise RuntimeError("Falling back to heuristic")

        # 🔥 CLEAN + EXTRACT JSON
        batch_text = re.sub(r"```json|```", "", batch_text).strip()

        match = re.search(r"\{.*\}", batch_text, re.DOTALL)
        if not match:
            raise ValueError("No JSON found in LLM response")

        json_str = match.group(0)
        batch_result = json.loads(json_str)

        verdict_map = {
            res["variable"]: res for res in batch_result.get("results", [])
        }

        final_verdicts = []
        low_confidence_count = 0

        for dead in dead_vars:
            res = verdict_map.get(dead.name)

            if res:
                # ── Post-process: override severity if naming pattern detected
                severity = res["severity"]
                name_lower = dead.name.lower()
                if severity == "HIGH" and any(p in name_lower for p in DEBUG_PATTERNS):
                    severity = "MEDIUM"

                final_verdicts.append(Verdict(
                    variable=dead.name,
                    line=dead.line,
                    severity=severity,
                    explanation=res["explanation"],
                    suggestion=res["suggestion"],
                    confidence=res["confidence"],
                    retried=(retry_count > 0)
                ))

                if res["confidence"] == "LOW":
                    low_confidence_count += 1
            else:
                print(f"[Agent 3] No verdict returned for '{dead.name}' — using heuristic fallback")
                final_verdicts.append(_heuristic_verdict(dead))

        needs_retry = (
            low_confidence_count > len(dead_vars) / 2
            and retry_count < MAX_RETRIES
        )

        return {
            **state,
            "verdicts": final_verdicts,
            "needs_retry": needs_retry,
            "retry_count": retry_count + 1,
        }

    except Exception as e:
        print(f"[Agent 3] Error: {e}")
        if batch_text:
            print(f"[Agent 3] Raw response preview:\n{batch_text[:500]}")
        return {
            **state,
            "verdicts": [_heuristic_verdict(d) for d in dead_vars],
            "needs_retry": False
        }

# ── MINIMAL CONTEXT BUILDER — no repeated function body ─────────────────
def _build_context_minimal(dead: DeadVariable, state: AgentState) -> str:
    """
    Per-variable context with only a tight 3-line snippet.
    Function body is already sent once at the top of the batch prompt.
    """
    lines = state["source"].splitlines()
    start = max(0, dead.line - 2)
    end   = min(len(lines), dead.line + 2)

    snippet = "\n".join(
        f"  {i+1}: {lines[i]}" for i in range(start, end)
    )

    hint = _severity_hint(dead.name, dead.reason)

    return (
        f"Variable: {dead.name}\n"
        f"Line {dead.line}: {dead.name} = {dead.value_text}\n"
        f"Flagged reason: {dead.reason}\n"
        f"{hint}\n"
        f"Snippet:\n{snippet}"
    )

# ── FALLBACK ────────────────────────────────────────
def _heuristic_verdict(dead: DeadVariable) -> Verdict:
    name_lower = dead.name.lower()
    if any(p in name_lower for p in DEBUG_PATTERNS):
        severity = "MEDIUM"
    elif "chain" in dead.reason.lower():
        severity = "LOW"
    else:
        severity = "HIGH"

    return Verdict(
        dead.name,
        dead.line,
        severity,
        dead.reason,
        "Review manually — LLM verdict unavailable.",
        "LOW"
    )

# ── ROUTER ──────────────────────────────────────────
def confidence_router(state: AgentState) -> str:
    return "retry" if state.get("needs_retry", False) else "done"