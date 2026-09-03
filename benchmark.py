# benchmark.py
"""
Benchmark: Dead Logic Detector vs Pylint vs Vulture
"""

import subprocess
import json
import re
import os
import sys
import html
from dataclasses import dataclass

# ── Data model ────────────────────────────────────────────────────────────

@dataclass
class Finding:
    tool:     str
    line:     int
    category: str
    variable: str
    message:  str
    severity: str


# ── Resolve API key (same priority order as pipeline.py) ─────────────────

def _get_api_key() -> str | None:
    return (
        os.environ.get("GROQ_API_KEY")
        or os.environ.get("GEMINI_API_KEY")
        or os.environ.get("ANTHROPIC_API_KEY")
    )


# ── 1. Run YOUR tool ──────────────────────────────────────────────────────

def run_your_tool(target_file: str) -> list[Finding]:
    findings = []
    try:
        # Use pipeline.run() — NOT build_pipeline() directly
        # This ensures API key is passed and all agents fire correctly
        from pipeline import run as pipeline_run

        api_key = _get_api_key()
        if api_key:
            provider = (
                "Groq"     if os.environ.get("GROQ_API_KEY")   else
                "Gemini"   if os.environ.get("GEMINI_API_KEY") else
                "Anthropic"
            )
            print(f"[Benchmark] DeadLogic using {provider} API")
        else:
            print("[Benchmark] DeadLogic running in heuristic mode (no API key)")

        final_state = pipeline_run(target_file, api_key=api_key)

        # ── Dead variables ─────────────────────────────────────────────
        for v in final_state.get("verdicts", []):
            findings.append(Finding(
                tool="DeadLogic",
                line=v.line,
                category="dead_variable",
                variable=v.variable,
                message=v.explanation,
                severity=v.severity,
            ))

        # ── Shadowed assignments ───────────────────────────────────────
        for s in final_state.get("shadowed_vars", []):
            expl = (s.explanation if s.explanation
                    else f"First write to '{s.name}' overwritten at line {s.overwrite_line} before being read.")
            findings.append(Finding(
                tool="DeadLogic",
                line=s.first_write_line,
                category="shadowed",
                variable=s.name,
                message=expl,
                severity="MEDIUM",
            ))

        # ── Impossible branches ────────────────────────────────────────
        for b in final_state.get("impossible_branches", []):
            findings.append(Finding(
                tool="DeadLogic",
                line=b.line,
                category="impossible_branch",
                variable=b.inner_condition[:40],
                message=b.explanation,
                severity="HIGH",
            ))

        print(f"[Benchmark] DeadLogic → {len(findings)} findings "
              f"({sum(1 for f in findings if f.category=='dead_variable')} dead, "
              f"{sum(1 for f in findings if f.category=='shadowed')} shadowed, "
              f"{sum(1 for f in findings if f.category=='impossible_branch')} impossible)")

    except Exception as e:
        print(f"[Benchmark] DeadLogic ERROR: {e}")
        import traceback; traceback.print_exc()

    return findings


# ── 2. Run Pylint ─────────────────────────────────────────────────────────

PYLINT_DEAD_CODES = {
    "W0612": ("dead_variable", "LOW"),
    "W0611": ("dead_variable", "LOW"),
    "W0613": ("dead_variable", "LOW"),
    "W0641": ("dead_variable", "LOW"),
    "W0621": ("shadowed",      "LOW"),
    "W0622": ("shadowed",      "LOW"),
    "W1304": ("dead_variable", "LOW"),
}

def run_pylint(target_file: str) -> list[Finding]:
    findings = []
    try:
        result = subprocess.run(
            [
                sys.executable, "-m", "pylint",
                target_file,
                "--output-format=json",
                "--disable=all",
                "--enable=W0612,W0611,W0613,W0641,W0621,W0622,W1304",
            ],
            capture_output=True, text=True, timeout=60
        )

        raw = result.stdout.strip()
        if not raw:
            print("[Benchmark] Pylint → no output")
            return findings

        messages = json.loads(raw)
        for m in messages:
            code = m.get("message-id", "")
            if code in PYLINT_DEAD_CODES:
                category, severity = PYLINT_DEAD_CODES[code]
                var_match = re.search(r"'([^']+)'", m.get("message", ""))
                var_name  = var_match.group(1) if var_match else "?"
                findings.append(Finding(
                    tool="Pylint",
                    line=m.get("line", 0),
                    category=category,
                    variable=var_name,
                    message=m.get("message", ""),
                    severity=severity,
                ))

        print(f"[Benchmark] Pylint → {len(findings)} findings")

    except FileNotFoundError:
        print("[Benchmark] Pylint not installed — pip install pylint")
    except Exception as e:
        print(f"[Benchmark] Pylint ERROR: {e}")

    return findings


# ── 3. Run Vulture ────────────────────────────────────────────────────────

def run_vulture(target_file: str) -> list[Finding]:
    findings = []
    try:
        result = subprocess.run(
            [sys.executable, "-m", "vulture", target_file, "--min-confidence", "60"],
            capture_output=True, text=True, timeout=60
        )

        pattern = re.compile(r".+:(\d+):\s+(.+?)\s+\((\d+)%\s+confidence\)")
        for line in result.stdout.splitlines():
            m = pattern.match(line)
            if m:
                lineno     = int(m.group(1))
                message    = m.group(2)
                confidence = int(m.group(3))

                severity = (
                    "HIGH"   if confidence >= 90 else
                    "MEDIUM" if confidence >= 70 else
                    "LOW"
                )

                var_match = re.search(r"'([^']+)'", message)
                var_name  = var_match.group(1) if var_match else "?"

                findings.append(Finding(
                    tool="Vulture",
                    line=lineno,
                    category="dead_variable",
                    variable=var_name,
                    message=message,
                    severity=severity,
                ))

        print(f"[Benchmark] Vulture → {len(findings)} findings")

    except FileNotFoundError:
        print("[Benchmark] Vulture not installed — pip install vulture")
    except Exception as e:
        print(f"[Benchmark] Vulture ERROR: {e}")

    return findings


# ── 4. Match findings across tools ───────────────────────────────────────

def match_findings(
    your_findings:    list[Finding],
    pylint_findings:  list[Finding],
    vulture_findings: list[Finding],
    source_lines:     list[str],
) -> list[dict]:
    all_lines = sorted(set(
        [f.line for f in your_findings]    +
        [f.line for f in pylint_findings]  +
        [f.line for f in vulture_findings]
    ))

    def findings_for(findings, line):
        return [f for f in findings if f.line == line]

    rows = []
    for line in all_lines:
        code = source_lines[line - 1].strip() if line <= len(source_lines) else ""
        rows.append({
            "line":    line,
            "code":    code,
            "yours":   findings_for(your_findings,    line),
            "pylint":  findings_for(pylint_findings,  line),
            "vulture": findings_for(vulture_findings, line),
        })
    return rows


# ── 5. Stats ──────────────────────────────────────────────────────────────

def compute_stats(rows: list[dict], your_findings: list[Finding]) -> dict:
    total = len(rows)

    # Count unique lines caught per tool
    caught_yours   = sum(1 for r in rows if r["yours"])
    caught_pylint  = sum(1 for r in rows if r["pylint"])
    caught_vulture = sum(1 for r in rows if r["vulture"])

    only_yours = sum(
        1 for r in rows
        if r["yours"] and not r["pylint"] and not r["vulture"]
    )
    missed_by_yours = sum(
        1 for r in rows
        if not r["yours"] and (r["pylint"] or r["vulture"])
    )

    # Category breakdown for DeadLogic
    dead_count      = sum(1 for f in your_findings if f.category == "dead_variable")
    shadow_count    = sum(1 for f in your_findings if f.category == "shadowed")
    impossible_count = sum(1 for f in your_findings if f.category == "impossible_branch")

    return {
        "total_flagged_lines":  total,
        "caught_deadlogic":     caught_yours,
        "caught_pylint":        caught_pylint,
        "caught_vulture":       caught_vulture,
        "only_deadlogic":       only_yours,
        "missed_by_deadlogic":  missed_by_yours,
        "deadlogic_dead_vars":  dead_count,
        "deadlogic_shadowed":   shadow_count,
        "deadlogic_impossible": impossible_count,
    }


# ── 6. HTML report ────────────────────────────────────────────────────────

SEV_COLOR = {
    "HIGH":    "#c0392b",
    "MEDIUM":  "#b07d00",
    "LOW":     "#2471a3",
    "unknown": "#888",
}

CAT_LABEL = {
    "dead_variable":    "dead variable",
    "shadowed":         "shadowed",
    "impossible_branch":"impossible branch",
}

def _cell(findings: list[Finding]) -> str:
    if not findings:
        return '<td class="miss">✗ missed</td>'
    parts = []
    for f in findings:
        color = SEV_COLOR.get(f.severity, "#888")
        cat   = CAT_LABEL.get(f.category, f.category)
        parts.append(
            f'<span style="color:{color};font-weight:600">{f.severity}</span> '
            f'<span class="cat">[{cat}]</span><br>'
            f'<span class="msg">{html.escape(f.message[:140])}</span>'
        )
    return f'<td class="hit">{"<hr>".join(parts)}</td>'


def generate_html_report(
    rows:        list[dict],
    stats:       dict,
    target_file: str,
    out_path:    str,
):
    stat_cards = "".join([
        f'<div class="card"><div class="num">{stats["total_flagged_lines"]}</div>'
        f'<div class="lbl">Total flagged lines</div></div>',

        f'<div class="card"><div class="num" style="color:#1d9e75">'
        f'{stats["caught_deadlogic"]}</div>'
        f'<div class="lbl">Caught by DeadLogic</div></div>',

        f'<div class="card"><div class="num" style="color:#888">'
        f'{stats["caught_pylint"]}</div>'
        f'<div class="lbl">Caught by Pylint</div></div>',

        f'<div class="card"><div class="num" style="color:#888">'
        f'{stats["caught_vulture"]}</div>'
        f'<div class="lbl">Caught by Vulture</div></div>',

        f'<div class="card"><div class="num" style="color:#8e44ad">'
        f'{stats["only_deadlogic"]}</div>'
        f'<div class="lbl">Only DeadLogic caught</div></div>',

        f'<div class="card"><div class="num" style="color:#c0392b">'
        f'{stats["missed_by_deadlogic"]}</div>'
        f'<div class="lbl">DeadLogic missed</div></div>',
    ])

    # DeadLogic category breakdown sub-cards
    breakdown = (
        f'<p class="hint" style="margin-bottom:.75rem">DeadLogic breakdown: '
        f'<strong style="color:#c0392b">{stats["deadlogic_dead_vars"]}</strong> dead variables &nbsp;·&nbsp; '
        f'<strong style="color:#d4ac0d">{stats["deadlogic_shadowed"]}</strong> shadowed &nbsp;·&nbsp; '
        f'<strong style="color:#8e44ad">{stats["deadlogic_impossible"]}</strong> impossible branches</p>'
    )

    table_rows = ""
    for r in rows:
        only_dl = r["yours"] and not r["pylint"] and not r["vulture"]
        row_style = 'style="background:#f0fff4"' if only_dl else ""
        table_rows += (
            f'<tr {row_style}>'
            f'<td class="lnum">{r["line"]}</td>'
            f'<td><code>{html.escape(r["code"])}</code></td>'
            f'{_cell(r["yours"])}'
            f'{_cell(r["pylint"])}'
            f'{_cell(r["vulture"])}'
            f'</tr>\n'
        )

    report = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>Benchmark — DeadLogic vs Pylint vs Vulture</title>
<style>
*{{box-sizing:border-box;margin:0;padding:0}}
body{{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;
     background:#f5f5f5;color:#222;padding:2rem;line-height:1.5}}
h1{{font-size:1.4rem;font-weight:600;margin-bottom:.2rem}}
.sub{{color:#666;font-size:.85rem;margin-bottom:1.5rem}}
.cards{{display:flex;gap:10px;flex-wrap:wrap;margin-bottom:.75rem}}
.card{{background:#fff;border:1px solid #e8e8e8;border-radius:8px;
      padding:.75rem 1.1rem;min-width:130px}}
.card .num{{font-size:1.5rem;font-weight:600}}
.card .lbl{{font-size:.7rem;color:#888;text-transform:uppercase;letter-spacing:.06em}}
.hint{{font-size:.75rem;color:#888;margin-bottom:.4rem}}
h2{{font-size:.85rem;font-weight:600;color:#555;text-transform:uppercase;
   letter-spacing:.07em;margin:1.5rem 0 .5rem}}
table{{width:100%;border-collapse:collapse;background:#fff;
      border:1px solid #e8e8e8;border-radius:8px;overflow:hidden;font-size:.8rem;
      margin-bottom:1rem}}
th{{background:#f8f8f8;text-align:left;padding:.5rem .75rem;font-size:.72rem;
   text-transform:uppercase;letter-spacing:.05em;color:#666;
   border-bottom:2px solid #e8e8e8}}
td{{padding:.5rem .75rem;border-top:1px solid #f0f0f0;vertical-align:top}}
td.lnum{{color:#999;font-family:monospace;width:3rem;text-align:right}}
td code{{font-family:'JetBrains Mono','Fira Code',monospace;font-size:.78rem;
        background:#f4f4f4;padding:.1em .3em;border-radius:3px}}
td.miss{{color:#bbb;font-style:italic;font-size:.78rem}}
td.hit{{font-size:.78rem;line-height:1.6}}
.cat{{color:#888;font-size:.7rem}}
.msg{{color:#555;font-size:.71rem}}
hr{{border:none;border-top:1px solid #eee;margin:.3rem 0}}
.legend{{font-size:.75rem;color:#666;margin-bottom:1rem;
        display:flex;gap:1.5rem;flex-wrap:wrap;align-items:center}}
.leg{{display:flex;align-items:center;gap:5px}}
.leg-dot{{width:10px;height:10px;border-radius:2px;flex-shrink:0}}
tr:hover td{{background:#fafafa}}
</style>
</head>
<body>
<h1>Benchmark Report — DeadLogic vs Pylint vs Vulture</h1>
<p class="sub">File: <strong>{html.escape(target_file)}</strong>
&nbsp;·&nbsp; Green rows = findings unique to DeadLogic Detector</p>

<div class="cards">{stat_cards}</div>
{breakdown}

<div class="legend">
  <span class="leg"><span class="leg-dot" style="background:#c0392b"></span>HIGH</span>
  <span class="leg"><span class="leg-dot" style="background:#b07d00"></span>MEDIUM</span>
  <span class="leg"><span class="leg-dot" style="background:#2471a3"></span>LOW</span>
  <span class="leg"><span class="leg-dot" style="background:#f0fff4;border:1px solid #b2dfdb"></span>
    Only DeadLogic caught</span>
</div>

<table>
  <thead>
    <tr>
      <th>Line</th><th>Code</th>
      <th>🔬 DeadLogic Detector</th>
      <th>Pylint</th>
      <th>Vulture</th>
    </tr>
  </thead>
  <tbody>{table_rows}</tbody>
</table>

<p style="margin-top:2rem;font-size:.75rem;color:#bbb">
  Dead Logic Detector v3 · Benchmark Suite</p>
</body>
</html>"""

    with open(out_path, "w", encoding="utf-8") as f:
        f.write(report)
    print(f"[Benchmark] Report saved → {out_path}")


# ── Entry point ───────────────────────────────────────────────────────────

def run_benchmark(target_file: str):
    print(f"\n{'='*55}")
    print(f"  Benchmarking: {target_file}")
    print(f"{'='*55}\n")

    with open(target_file, encoding="utf-8") as f:
        source_lines = f.readlines()

    your_findings    = run_your_tool(target_file)
    pylint_findings  = run_pylint(target_file)
    vulture_findings = run_vulture(target_file)

    rows  = match_findings(your_findings, pylint_findings, vulture_findings, source_lines)
    stats = compute_stats(rows, your_findings)

    print(f"\n── Stats ──────────────────────────────────────────")
    for k, v in stats.items():
        print(f"  {k:<30} {v}")

    out_path = target_file.replace(".py", "_benchmark.html")
    generate_html_report(rows, stats, target_file, out_path)
    return stats


if __name__ == "__main__":
    target = sys.argv[1] if len(sys.argv) > 1 else "sample_target.py"
    run_benchmark(target)