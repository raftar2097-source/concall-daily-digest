#!/usr/bin/env python3
"""Render digests/state.json into docs/index.html — a static, styled,
color-coded view of the guidance ledger, meant to be served by GitHub
Pages (Settings -> Pages -> Deploy from branch -> main /docs).

Deterministic, not an LLM step (same reasoning as build_table.py): the
data is already final by the time this runs, so this is a pure
data-to-HTML render with no judgment calls left to make.

Color coding is driven by each cell's `verdict` field (see
.claude/agents/concall-digest-writer.md): beat/met -> positive (green),
missed -> negative (red), partial/too_early/absent -> neutral (no
comparison to make, or a genuinely mixed one). Cells written before the
`verdict` field existed fall back to a best-effort regex read of a leading
BEAT/MISS/PARTIAL word in the summary text.

Usage:
    python3 build_site.py
"""
from __future__ import annotations

import html
import json
import re
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
STATE_PATH = REPO_ROOT / "digests" / "state.json"
OUT_PATH = REPO_ROOT / "docs" / "index.html"
MAX_QUARTERS = 4

POSITIVE = {"beat", "met"}
NEGATIVE = {"missed", "miss"}
# everything else (partial, too_early, None) renders neutral

LEGACY_VERDICT_RE = re.compile(r"^\s*(beat|missed|miss|met|partial|too early)\b", re.IGNORECASE)


def classify(cell: dict) -> str:
    verdict = cell.get("verdict")
    if verdict is None:
        m = LEGACY_VERDICT_RE.match(cell.get("summary", ""))
        verdict = m.group(1).lower() if m else None
    if verdict in POSITIVE:
        return "positive"
    if verdict in NEGATIVE:
        return "negative"
    return "neutral"


def render_cell(cell: dict | None) -> str:
    if cell is None:
        return '<td class="cell empty">not yet logged</td>'
    status = classify(cell)
    summary = html.escape(cell["summary"])
    quarter = html.escape(cell["quarter"])
    return (
        f'<td class="cell {status}">'
        f'<div class="cell-quarter">{quarter}</div>'
        f'<div class="cell-summary">{summary}</div>'
        f'</td>'
    )


def render_row(symbol: str, entry: dict) -> str:
    quarters = entry["quarters"]
    padded = [None] * (MAX_QUARTERS - len(quarters)) + quarters
    name = html.escape(entry.get("company_name") or symbol)
    cells = "".join(render_cell(q) for q in padded)
    return (
        f'<tr><td class="stock-col">'
        f'<span class="stock-name">{name}</span>'
        f'<span class="stock-sym">{html.escape(symbol)}</span>'
        f'</td>{cells}</tr>'
    )


TEMPLATE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Concall Digest — Guidance Ledger</title>
<style>
  :root {{
    --bg: #EEF1EF; --surface: #FFFFFF; --surface-alt: #F5F7F5;
    --ink: #1A2023; --ink-muted: #5B6660; --ink-faint: #94A099;
    --border: #DAE0DC; --accent: #1F5F63; --accent-soft: #E4EEEC;
    --pos-fg: #1F6B45; --pos-bg: #E4F1E8;
    --neg-fg: #A23F26; --neg-bg: #F7E7E1;
    --neu-fg: #8A6110; --neu-bg: #F3EAD4;
    --shadow: 0 1px 2px rgba(20,30,27,.06), 0 8px 24px rgba(20,30,27,.05);
  }}
  @media (prefers-color-scheme: dark) {{
    :root:not([data-theme="light"]) {{
      --bg: #14181A; --surface: #1B2123; --surface-alt: #212829;
      --ink: #E7ECE9; --ink-muted: #98A39D; --ink-faint: #616D67;
      --border: #2B3335; --accent: #6BB6B8; --accent-soft: #223330;
      --pos-fg: #7DCB9C; --pos-bg: #1E3226;
      --neg-fg: #E39678; --neg-bg: #362320;
      --neu-fg: #E0BC72; --neu-bg: #352C1B;
      --shadow: 0 1px 2px rgba(0,0,0,.3), 0 8px 24px rgba(0,0,0,.35);
    }}
  }}
  :root[data-theme="dark"] {{
    --bg: #14181A; --surface: #1B2123; --surface-alt: #212829;
    --ink: #E7ECE9; --ink-muted: #98A39D; --ink-faint: #616D67;
    --border: #2B3335; --accent: #6BB6B8; --accent-soft: #223330;
    --pos-fg: #7DCB9C; --pos-bg: #1E3226;
    --neg-fg: #E39678; --neg-bg: #362320;
    --neu-fg: #E0BC72; --neu-bg: #352C1B;
    --shadow: 0 1px 2px rgba(0,0,0,.3), 0 8px 24px rgba(0,0,0,.35);
  }}
  * {{ box-sizing: border-box; }}
  body {{
    margin: 0; background: var(--bg); color: var(--ink);
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
    line-height: 1.5; padding: clamp(20px, 4vw, 56px);
    display: flex; justify-content: center;
  }}
  .page {{ width: 100%; max-width: 1160px; display: flex; flex-direction: column; gap: 24px; }}
  h1 {{ font-family: Georgia, "Iowan Old Style", "Times New Roman", serif; text-wrap: balance; margin: 0; font-size: clamp(24px, 3.2vw, 34px); font-weight: 600; }}
  header.top {{ display: flex; flex-direction: column; gap: 12px; padding-bottom: 18px; border-bottom: 1px solid var(--border); }}
  .eyebrow {{ font-family: ui-monospace, "SF Mono", Menlo, Consolas, monospace; font-size: 12px; letter-spacing: .09em; text-transform: uppercase; color: var(--accent); }}
  .lede {{ max-width: 62ch; color: var(--ink-muted); font-size: 15px; }}
  .meta-row {{ display: flex; flex-wrap: wrap; gap: 10px 28px; margin-top: 2px; }}
  .meta-item {{ display: flex; flex-direction: column; gap: 2px; }}
  .meta-label {{ font-size: 11px; text-transform: uppercase; letter-spacing: .07em; color: var(--ink-faint); }}
  .meta-value {{ font-family: ui-monospace, "SF Mono", Menlo, Consolas, monospace; font-variant-numeric: tabular-nums; font-size: 14px; }}
  .legend {{ display: flex; flex-wrap: wrap; gap: 8px; align-items: center; }}
  .chip {{ display: inline-flex; align-items: center; gap: 5px; font-family: ui-monospace, "SF Mono", Menlo, Consolas, monospace; font-size: 11px; font-weight: 600; letter-spacing: .04em; padding: 3px 8px; border-radius: 4px; }}
  .chip.positive {{ color: var(--pos-fg); background: var(--pos-bg); }}
  .chip.negative {{ color: var(--neg-fg); background: var(--neg-bg); }}
  .chip.neutral {{ color: var(--neu-fg); background: var(--neu-bg); }}
  .table-card {{ background: var(--surface); border: 1px solid var(--border); border-radius: 10px; box-shadow: var(--shadow); overflow: hidden; }}
  .table-scroll {{ overflow-x: auto; }}
  table {{ border-collapse: collapse; width: 100%; min-width: 980px; }}
  thead th {{ text-align: left; font-family: ui-monospace, "SF Mono", Menlo, Consolas, monospace; font-size: 11px; letter-spacing: .07em; text-transform: uppercase; color: var(--ink-faint); font-weight: 500; padding: 14px 18px; background: var(--surface-alt); border-bottom: 1px solid var(--border); white-space: nowrap; }}
  thead th.stock-col {{ position: sticky; left: 0; z-index: 2; background: var(--surface-alt); }}
  tbody td {{ padding: 16px 18px; border-bottom: 1px solid var(--border); vertical-align: top; font-size: 13.5px; }}
  tbody tr:last-child td {{ border-bottom: none; }}
  tbody tr:hover {{ background: var(--accent-soft); }}
  tbody tr:hover .stock-col {{ background: var(--accent-soft); }}
  td.stock-col {{ position: sticky; left: 0; z-index: 1; background: var(--surface); min-width: 200px; max-width: 200px; }}
  .stock-name {{ font-weight: 600; color: var(--ink); font-size: 14px; display: block; }}
  .stock-sym {{ display: block; margin-top: 2px; font-family: ui-monospace, "SF Mono", Menlo, Consolas, monospace; font-size: 11px; color: var(--ink-faint); letter-spacing: .04em; }}
  td.cell {{ min-width: 210px; max-width: 260px; border-left: 3px solid transparent; }}
  td.cell.positive {{ background: var(--pos-bg); border-left-color: var(--pos-fg); }}
  td.cell.negative {{ background: var(--neg-bg); border-left-color: var(--neg-fg); }}
  td.cell.neutral {{ background: transparent; }}
  td.cell.empty {{ color: var(--ink-faint); font-family: ui-monospace, "SF Mono", Menlo, Consolas, monospace; font-size: 12px; }}
  .cell-quarter {{ font-family: ui-monospace, "SF Mono", Menlo, Consolas, monospace; font-size: 11px; color: var(--ink-faint); margin-bottom: 6px; }}
  .cell-summary {{ color: var(--ink-muted); font-size: 13px; line-height: 1.5; }}
  td.cell.positive .cell-summary, td.cell.negative .cell-summary {{ color: var(--ink); }}
  footer.note {{ padding: 16px 20px; background: var(--surface-alt); border: 1px solid var(--border); border-radius: 10px; font-size: 12.5px; color: var(--ink-muted); }}
  footer.note code {{ font-family: ui-monospace, "SF Mono", Menlo, Consolas, monospace; background: var(--accent-soft); color: var(--accent); padding: 1px 5px; border-radius: 4px; font-size: .92em; }}
</style>
</head>
<body>
<div class="page">
  <header class="top">
    <span class="eyebrow">concall-daily-digest</span>
    <h1>Guidance Ledger</h1>
    <p class="lede">One row per NSE-listed company, rebuilt daily from filed earnings-call transcripts. Every cell leads with forward guidance; color marks whether the previous quarter's guidance was met.</p>
    <div class="meta-row">
      <div class="meta-item"><span class="meta-label">Last updated</span><span class="meta-value">{updated}</span></div>
      <div class="meta-item"><span class="meta-label">Companies tracked</span><span class="meta-value">{count}</span></div>
    </div>
    <div class="legend">
      <span class="chip positive">Guidance met / beat</span>
      <span class="chip negative">Guidance missed</span>
      <span class="chip neutral">Neutral / not yet comparable</span>
    </div>
  </header>
  <div class="table-card">
    <div class="table-scroll">
      <table>
        <thead><tr>
          <th class="stock-col">Stock</th>
          <th>Q(t&minus;3)</th><th>Q(t&minus;2)</th><th>Q(t&minus;1)</th><th>Q(t) &middot; current</th>
        </tr></thead>
        <tbody>
          {rows}
        </tbody>
      </table>
    </div>
  </div>
  <footer class="note">
    Rendered from <code>digests/state.json</code> by <code>scripts/build_site.py</code>, regenerated on every daily run.
    Only today's transcript and the previous quarter are read per run &mdash; the left columns fill in as each company reports over time.
  </footer>
</div>
</body>
</html>
"""


def main() -> None:
    state = json.loads(STATE_PATH.read_text()) if STATE_PATH.exists() else {}
    rows = "\n          ".join(render_row(sym, state[sym]) for sym in sorted(state.keys()))
    updated = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    html_out = TEMPLATE.format(rows=rows or '<tr><td class="cell empty" colspan="5">No companies logged yet.</td></tr>', updated=updated, count=len(state))
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(html_out)
    print(f"Wrote {OUT_PATH} ({len(state)} companies)")


if __name__ == "__main__":
    main()
