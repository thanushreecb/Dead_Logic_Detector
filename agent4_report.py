"""
agent4_report.py — Report Generator Node
LangGraph node: reads verdicts from state, writes report_html + report_path.
"""

import html
import os
from state import AgentState, Verdict

SEV = {
    "HIGH":   ("#fff0f0", "#c0392b", "🔴"),
    "MEDIUM": ("#fffbe6", "#b07d00", "🟡"),
    "LOW":    ("#f0f8ff", "#2471a3", "🔵"),
}


def report_node(state: AgentState) -> AgentState:
    print("[Agent 4] Generating HTML report...")

    verdicts   = state["verdicts"]
    source     = state["source"]
    filename   = os.path.basename(state["filepath"])
    out_path   = state["filepath"].replace(".py", "_report.html")
    shadowed   = state.get("shadowed_vars", [])
    impossible = state.get("impossible_branches", [])

    dead_lines     = {v.line: v for v in verdicts}
    shadow_lines   = {s.first_write_line: s for s in shadowed}
    impossible_lines = {b.line: b for b in impossible}
    lines          = source.splitlines()

    # ── Annotated source ──────────────────────────────────────────────────
    src_rows = []
    for i, line in enumerate(lines, start=1):
        escaped = html.escape(line) if line.strip() else "&nbsp;"

        if i in dead_lines:
            v  = dead_lines[i]
            bg, border, icon = SEV.get(v.severity, ("#fff","#999","⚪"))
            retry = ' <span class="retry">retried</span>' if v.retried else ""
            src_rows.append(
                f'<div class="ln dead" style="background:{bg};border-left:3px solid {border}">'
                f'<span class="lnum">{i:>4}</span>'
                f'<span class="badge" style="color:{border}">{icon} {v.severity}</span>'
                f'<code>{escaped}</code>'
                f'<span class="tip">{html.escape(v.explanation)}{retry}</span>'
                f'</div>'
            )
        elif i in shadow_lines:
            s = shadow_lines[i]
            src_rows.append(
                f'<div class="ln dead" style="background:#fef9e7;border-left:3px solid #d4ac0d">'
                f'<span class="lnum">{i:>4}</span>'
                f'<span class="badge" style="color:#d4ac0d">🟠 SHADOW</span>'
                f'<code>{escaped}</code>'
                f'<span class="tip">First write to \'{html.escape(s.name)}\' is overwritten '
                f'at line {s.overwrite_line} before being read — this assignment is wasted.</span>'
                f'</div>'
            )
        elif i in impossible_lines:
            b = impossible_lines[i]
            src_rows.append(
                f'<div class="ln dead" style="background:#f4ecf7;border-left:3px solid #8e44ad">'
                f'<span class="lnum">{i:>4}</span>'
                f'<span class="badge" style="color:#8e44ad">🟣 IMPOSSIBLE</span>'
                f'<code>{escaped}</code>'
                f'<span class="tip">{html.escape(b.explanation)}</span>'
                f'</div>'
            )
        else:
            src_rows.append(
                f'<div class="ln"><span class="lnum">{i:>4}</span>'
                f'<code>{escaped}</code></div>'
            )

    # ── Summary table rows ────────────────────────────────────────────────
    table_rows = []
    for v in sorted(verdicts, key=lambda x: x.line):
        bg, border, icon = SEV.get(v.severity, ("#fff","#999","⚪"))
        retry = '<span class="retry">retried</span>' if v.retried else ""
        table_rows.append(
            f'<tr style="border-left:3px solid {border}">'
            f'<td>{v.line}</td><td><code>{html.escape(v.variable)}</code></td>'
            f'<td><span style="color:{border};font-weight:600">{icon} {v.severity}</span></td>'
            f'<td>{html.escape(v.explanation)} {retry}</td>'
            f'<td>{html.escape(v.suggestion)}</td></tr>\n'
        )
    table_rows = "".join(table_rows)

    # ── Shadowed vars table ───────────────────────────────────────────────
    shadow_rows = ""
    for s in sorted(shadowed, key=lambda x: x.first_write_line):
        # Use LLM explanation if available, else fall back to template
        expl = (s.explanation if s.explanation
                else f"Overwritten at line {s.overwrite_line} — first write is never read")
        sugg = (s.suggestion if s.suggestion
                else "Remove the first assignment or use the value before overwriting.")
        shadow_rows += (
            f'<tr style="border-left:3px solid #d4ac0d">'
            f'<td>{s.first_write_line}</td>'
            f'<td><code>{html.escape(s.name)}</code></td>'
            f'<td>{html.escape(s.first_write_value[:60])}</td>'
            f'<td>{html.escape(expl)}</td>'
            f'<td>{html.escape(sugg)}</td>'
            f'</tr>\n'
        )

    # ── Impossible branches table ─────────────────────────────────────────
    branch_rows = ""
    for b in sorted(impossible, key=lambda x: x.line):
        branch_rows += (
            f'<tr style="border-left:3px solid #8e44ad">'
            f'<td>{b.line}</td>'
            f'<td><code>{html.escape(b.inner_condition[:50])}</code></td>'
            f'<td>{html.escape(str(b.outer_conditions))}</td>'
            f'<td>{html.escape(b.explanation)}</td>'
            f'<td>{html.escape(b.suggestion)}</td>'
            f'<td><span style="color:#8e44ad;font-weight:600">{b.confidence}</span></td>'
            f'</tr>\n'
        )

    high   = sum(1 for v in verdicts if v.severity == "HIGH")
    medium = sum(1 for v in verdicts if v.severity == "MEDIUM")
    low    = sum(1 for v in verdicts if v.severity == "LOW")
    retried_count = sum(1 for v in verdicts if v.retried)
    total_issues = len(verdicts) + len(shadowed) + len(impossible)

    shadow_section = ""
    if shadowed:
        shadow_section = f"""
<h2>Shadowed assignments</h2>
<p class="hint">First writes overwritten before being read — the initial assignment is wasted.</p>
<table>
  <thead><tr><th>Line</th><th>Variable</th><th>First value</th><th>Issue</th><th>Fix</th></tr></thead>
  <tbody>{shadow_rows}</tbody>
</table>"""

    branch_section = ""
    if impossible:
        branch_section = f"""
<h2>Impossible branches</h2>
<p class="hint">Conditions that can never be true simultaneously — the branch body is unreachable.</p>
<table>
  <thead><tr><th>Line</th><th>Condition</th><th>Outer conditions</th><th>Explanation</th><th>Suggestion</th><th>Confidence</th></tr></thead>
  <tbody>{branch_rows}</tbody>
</table>"""

    report = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>Dead Logic Report — {html.escape(filename)}</title>
<style>
*{{box-sizing:border-box;margin:0;padding:0}}
body{{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;
     background:#f5f5f5;color:#222;padding:2rem;line-height:1.5}}
h1{{font-size:1.5rem;font-weight:600;margin-bottom:.2rem}}
.sub{{color:#666;font-size:.85rem;margin-bottom:1.5rem}}
.cards{{display:flex;gap:10px;margin-bottom:1.5rem;flex-wrap:wrap}}
.card{{background:#fff;border:1px solid #e8e8e8;border-radius:8px;padding:.75rem 1.1rem;min-width:110px}}
.card .num{{font-size:1.6rem;font-weight:600}}
.card .lbl{{font-size:.7rem;color:#888;text-transform:uppercase;letter-spacing:.06em}}
h2{{font-size:.85rem;font-weight:600;color:#555;text-transform:uppercase;
   letter-spacing:.07em;margin:1.5rem 0 .5rem}}
.hint{{font-size:.75rem;color:#888;margin-bottom:.4rem}}
.src{{background:#1a1a2e;border-radius:8px;padding:.6rem 0;font-size:.78rem;line-height:1.75;overflow-x:auto}}
.ln{{display:flex;align-items:baseline;padding:0 .75rem;gap:6px;position:relative}}
.ln:hover{{background:rgba(255,255,255,.04)}}
.ln.dead{{padding:.15rem .75rem;margin:1px 0;border-radius:2px}}
.lnum{{color:#3a3a5c;min-width:2.2rem;text-align:right;font-family:monospace;font-size:.72rem;user-select:none;flex-shrink:0}}
.ln code{{color:#a8b4c8;font-family:'JetBrains Mono','Fira Code',monospace;white-space:pre;flex:1}}
.ln.dead code{{color:#1a1a2e}}
.badge{{font-size:.65rem;font-weight:700;white-space:nowrap;min-width:5.5rem;flex-shrink:0}}
.tip{{display:none;position:absolute;left:40%;top:100%;background:#111;color:#eee;font-size:.72rem;
     padding:.35rem .6rem;border-radius:4px;z-index:10;max-width:360px;white-space:normal;
     pointer-events:none;border:1px solid #333}}
.ln.dead:hover .tip{{display:block}}
table{{width:100%;border-collapse:collapse;background:#fff;border:1px solid #e8e8e8;
      border-radius:8px;overflow:hidden;font-size:.82rem;margin-bottom:1rem}}
th{{background:#f8f8f8;text-align:left;padding:.5rem .75rem;font-size:.72rem;
   text-transform:uppercase;letter-spacing:.05em;color:#666;border-bottom:1px solid #e8e8e8}}
td{{padding:.55rem .75rem;border-top:1px solid #f0f0f0;vertical-align:top}}
tr:hover td{{background:#fafafa}}
td code{{background:#f0f0f0;padding:.1em .35em;border-radius:3px;font-size:.82em;font-family:monospace}}
.retry{{background:#e8f4fd;color:#1a5276;font-size:.7rem;padding:.1em .4em;border-radius:3px;margin-left:.3rem}}
.legend{{display:flex;gap:1rem;flex-wrap:wrap;font-size:.75rem;color:#666;margin-bottom:1rem}}
.leg{{display:flex;align-items:center;gap:4px}}
.leg-dot{{width:10px;height:10px;border-radius:2px;flex-shrink:0}}
</style>
</head>
<body>
<h1>Dead Logic Report</h1>
<p class="sub">File: <strong>{html.escape(filename)}</strong> &nbsp;·&nbsp; {total_issues} total issues</p>

<div class="cards">
  <div class="card"><div class="num" style="color:#c0392b">{high}</div><div class="lbl">Dead HIGH</div></div>
  <div class="card"><div class="num" style="color:#b07d00">{medium}</div><div class="lbl">Dead MED</div></div>
  <div class="card"><div class="num" style="color:#2471a3">{low}</div><div class="lbl">Dead LOW</div></div>
  <div class="card"><div class="num" style="color:#d4ac0d">{len(shadowed)}</div><div class="lbl">Shadowed</div></div>
  <div class="card"><div class="num" style="color:#8e44ad">{len(impossible)}</div><div class="lbl">Impossible</div></div>
  <div class="card"><div class="num">{len(lines)}</div><div class="lbl">Total lines</div></div>
</div>

<div class="legend">
  <span class="leg"><span class="leg-dot" style="background:#c0392b"></span>Dead variable (HIGH)</span>
  <span class="leg"><span class="leg-dot" style="background:#b07d00"></span>Dead variable (MEDIUM)</span>
  <span class="leg"><span class="leg-dot" style="background:#2471a3"></span>Dead variable (LOW)</span>
  <span class="leg"><span class="leg-dot" style="background:#d4ac0d"></span>Shadowed assignment</span>
  <span class="leg"><span class="leg-dot" style="background:#8e44ad"></span>Impossible branch</span>
</div>

<h2>Annotated source</h2>
<p class="hint">Hover over any highlighted line to see the explanation.</p>
<div class="src">{"".join(src_rows)}</div>

<h2>Dead variables</h2>
<table>
  <thead><tr><th>Line</th><th>Variable</th><th>Severity</th><th>Explanation</th><th>Suggestion</th></tr></thead>
  <tbody>{table_rows}</tbody>
</table>

{shadow_section}
{branch_section}

<p style="margin-top:2rem;font-size:.75rem;color:#bbb">
  Dead Logic Detector v3 · LangGraph + Agents 1, 1.5, 2, 3, 4</p>
</body>
</html>"""

    with open(out_path, "w", encoding="utf-8") as f:
        f.write(report)

    print(f"[Agent 4] Report saved → {out_path}")
    return {**state, "report_html": report, "report_path": out_path}

    verdicts  = state["verdicts"]
    source    = state["source"]
    filename  = os.path.basename(state["filepath"])
    out_path  = state["filepath"].replace(".py", "_report.html")

    dead_lines = {v.line: v for v in verdicts}
    lines      = source.splitlines()

    # ── Annotated source ──────────────────────────────────────────────────
    src_rows = []
    for i, line in enumerate(lines, start=1):
        escaped = html.escape(line) if line.strip() else "&nbsp;"
        if i in dead_lines:
            v  = dead_lines[i]
            bg, border, icon = SEV.get(v.severity, ("#fff","#999","⚪"))
            retry = ' <span class="retry">retried</span>' if v.retried else ""
            src_rows.append(
                f'<div class="ln dead" style="background:{bg};border-left:3px solid {border}">'
                f'<span class="lnum">{i:>4}</span>'
                f'<span class="badge" style="color:{border}">{icon} {v.severity}</span>'
                f'<code>{escaped}</code>'
                f'<span class="tip">{html.escape(v.explanation)}{retry}</span>'
                f'</div>'
            )
        else:
            src_rows.append(
                f'<div class="ln">'
                f'<span class="lnum">{i:>4}</span>'
                f'<code>{escaped}</code>'
                f'</div>'
            )

    # ── Summary table rows ────────────────────────────────────────────────
    table_rows = ""
    for v in sorted(verdicts, key=lambda x: x.line):
        bg, border, icon = SEV.get(v.severity, ("#fff","#999","⚪"))
        retry = '<span class="retry">retried</span>' if v.retried else ""
        table_rows += (
            f'<tr style="border-left:3px solid {border}">'
            f'<td>{v.line}</td>'
            f'<td><code>{html.escape(v.variable)}</code></td>'
            f'<td><span style="color:{border};font-weight:600">{icon} {v.severity}</span></td>'
            f'<td>{html.escape(v.explanation)} {retry}</td>'
            f'<td>{html.escape(v.suggestion)}</td>'
            f'</tr>\n'
        )

    high   = sum(1 for v in verdicts if v.severity == "HIGH")
    medium = sum(1 for v in verdicts if v.severity == "MEDIUM")
    low    = sum(1 for v in verdicts if v.severity == "LOW")
    retried_count = sum(1 for v in verdicts if v.retried)

    report = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>Dead Logic Report — {html.escape(filename)}</title>
<style>
*{{box-sizing:border-box;margin:0;padding:0}}
body{{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;
     background:#f5f5f5;color:#222;padding:2rem;line-height:1.5}}
h1{{font-size:1.5rem;font-weight:600;margin-bottom:.2rem}}
.sub{{color:#666;font-size:.85rem;margin-bottom:1.5rem}}
.cards{{display:flex;gap:10px;margin-bottom:1.5rem;flex-wrap:wrap}}
.card{{background:#fff;border:1px solid #e8e8e8;border-radius:8px;
      padding:.75rem 1.1rem;min-width:110px}}
.card .num{{font-size:1.6rem;font-weight:600}}
.card .lbl{{font-size:.7rem;color:#888;text-transform:uppercase;letter-spacing:.06em}}
h2{{font-size:.85rem;font-weight:600;color:#555;text-transform:uppercase;
   letter-spacing:.07em;margin:1.5rem 0 .5rem}}
.hint{{font-size:.75rem;color:#888;margin-bottom:.4rem}}
.src{{background:#1a1a2e;border-radius:8px;padding:.6rem 0;
     font-size:.78rem;line-height:1.75;overflow-x:auto}}
.ln{{display:flex;align-items:baseline;padding:0 .75rem;gap:6px;position:relative}}
.ln:hover{{background:rgba(255,255,255,.04)}}
.ln.dead{{padding:.15rem .75rem;margin:1px 0;border-radius:2px}}
.lnum{{color:#3a3a5c;min-width:2.2rem;text-align:right;font-family:monospace;
      font-size:.72rem;user-select:none;flex-shrink:0}}
.ln code{{color:#a8b4c8;font-family:'JetBrains Mono','Fira Code',monospace;
         white-space:pre;flex:1}}
.ln.dead code{{color:#1a1a2e}}
.badge{{font-size:.65rem;font-weight:700;white-space:nowrap;min-width:5rem;flex-shrink:0}}
.tip{{display:none;position:absolute;left:40%;top:100%;background:#111;
     color:#eee;font-size:.72rem;padding:.35rem .6rem;border-radius:4px;
     z-index:10;max-width:360px;white-space:normal;pointer-events:none;
     border:1px solid #333}}
.ln.dead:hover .tip{{display:block}}
table{{width:100%;border-collapse:collapse;background:#fff;
      border:1px solid #e8e8e8;border-radius:8px;overflow:hidden;font-size:.82rem}}
th{{background:#f8f8f8;text-align:left;padding:.5rem .75rem;font-size:.72rem;
   text-transform:uppercase;letter-spacing:.05em;color:#666;
   border-bottom:1px solid #e8e8e8}}
td{{padding:.55rem .75rem;border-top:1px solid #f0f0f0;vertical-align:top}}
tr:hover td{{background:#fafafa}}
td code{{background:#f0f0f0;padding:.1em .35em;border-radius:3px;
        font-size:.82em;font-family:monospace}}
.retry{{background:#e8f4fd;color:#1a5276;font-size:.7rem;
       padding:.1em .4em;border-radius:3px;margin-left:.3rem}}
.pipeline{{background:#fff;border:1px solid #e8e8e8;border-radius:8px;
          padding:1rem 1.25rem;margin-bottom:1.5rem;font-size:.82rem}}
.step{{display:inline-flex;align-items:center;gap:6px;margin-right:8px}}
.dot{{width:8px;height:8px;border-radius:50%;flex-shrink:0}}
</style>
</head>
<body>

<h1>Dead Logic Report</h1>
<p class="sub">
  File: <strong>{html.escape(filename)}</strong>
  &nbsp;·&nbsp; {len(verdicts)} issue{"s" if len(verdicts)!=1 else ""} found
  &nbsp;·&nbsp; {retried_count} verdict{"s" if retried_count!=1 else ""} retried by Agent 3
</p>

<div class="pipeline">
  <strong style="font-size:.8rem;text-transform:uppercase;letter-spacing:.06em;
                 color:#555">Pipeline</strong>&nbsp;&nbsp;
  <span class="step"><span class="dot" style="background:#1d9e75"></span>Agent 1 — Parser</span>
  →
  <span class="step"><span class="dot" style="background:#1d9e75"></span>Agent 2 — Tracer</span>
  →
  <span class="step"><span class="dot" style="background:#7f77dd"></span>Agent 3 — LLM Reasoner</span>
  {"→ <span class='step'><span class='dot' style='background:#e85d24'></span>retry loop</span> →" if retried_count > 0 else ""}
  →
  <span class="step"><span class="dot" style="background:#ef9f27"></span>Agent 4 — Report</span>
</div>

<div class="cards">
  <div class="card"><div class="num" style="color:#c0392b">{high}</div>
    <div class="lbl">High severity</div></div>
  <div class="card"><div class="num" style="color:#b07d00">{medium}</div>
    <div class="lbl">Medium severity</div></div>
  <div class="card"><div class="num" style="color:#2471a3">{low}</div>
    <div class="lbl">Low severity</div></div>
  <div class="card"><div class="num">{len(lines)}</div>
    <div class="lbl">Total lines</div></div>
</div>

<h2>Annotated source</h2>
<p class="hint">Hover over a highlighted line to see the explanation.</p>
<div class="src">
{"".join(src_rows)}
</div>

<h2>Findings</h2>
<table>
  <thead>
    <tr>
      <th>Line</th><th>Variable</th><th>Severity</th>
      <th>Explanation</th><th>Suggestion</th>
    </tr>
  </thead>
  <tbody>{table_rows}</tbody>
</table>

<p style="margin-top:2rem;font-size:.75rem;color:#bbb">
  Dead Logic Detector · LangGraph + Anthropic pipeline</p>
</body>
</html>"""

    with open(out_path, "w", encoding="utf-8") as f:
        f.write(report)

    print(f"[Agent 4] Report saved → {out_path}")
    return {**state, "report_html": report, "report_path": out_path}