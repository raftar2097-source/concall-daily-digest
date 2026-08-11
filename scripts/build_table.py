#!/usr/bin/env python3
"""Merge per-company cell files into the persistent state, then render the
table.

Each `concall-digest-writer` agent run writes one `digests/cells/<SYMBOL>.json`
(1-2 new quarter cells for that company). This script is the single writer
of `digests/state.json` — it's a plain deterministic merge, run once after
all per-company agents finish, specifically to avoid multiple parallel
agents racing to write the same shared state file.

For each company: new quarter cells are appended (skipped if that quarter
label is already recorded), then only the most recent 4 quarters are kept
(oldest dropped) so the table stays a rolling 4-quarter window. Processed
cell files are deleted after merging (they're scratch, not the deliverable).

Usage:
    python3 build_table.py
"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
CELLS_DIR = REPO_ROOT / "digests" / "cells"
STATE_PATH = REPO_ROOT / "digests" / "state.json"
TABLE_PATH = REPO_ROOT / "digests" / "TABLE.md"
MAX_QUARTERS = 4


def parse_quarter(label: str) -> datetime:
    try:
        return datetime.strptime(label, "%b %Y")
    except ValueError:
        return datetime.min  # unparseable labels sort first, don't crash the merge


def load_state() -> dict:
    if STATE_PATH.exists():
        return json.loads(STATE_PATH.read_text())
    return {}


def merge_cells(state: dict) -> int:
    if not CELLS_DIR.exists():
        return 0
    merged = 0
    for cell_file in sorted(CELLS_DIR.glob("*.json")):
        data = json.loads(cell_file.read_text())
        symbol = data["symbol"]
        entry = state.setdefault(symbol, {"company_name": data.get("company_name"), "quarters": []})
        entry["company_name"] = data.get("company_name", entry["company_name"])
        existing_labels = {q["quarter"] for q in entry["quarters"]}
        for cell in data["cells"]:
            if cell["quarter"] in existing_labels:
                continue
            entry["quarters"].append(cell)
            existing_labels.add(cell["quarter"])
            merged += 1
        entry["quarters"].sort(key=lambda q: parse_quarter(q["quarter"]))
        entry["quarters"] = entry["quarters"][-MAX_QUARTERS:]
        cell_file.unlink()
    return merged


def render_table(state: dict) -> str:
    lines = [
        "# Concall digest — rolling 4-quarter table",
        "",
        "One row per company, most recent quarter in the rightmost filled column.",
        "Blank cells mean that quarter hasn't been logged yet (either the company",
        "was seen for the first time recently, or it predates this pipeline).",
        "",
        "| Stock | Q(t-3) | Q(t-2) | Q(t-1) | Q(t) |",
        "|---|---|---|---|---|",
    ]
    for symbol in sorted(state.keys()):
        entry = state[symbol]
        quarters = entry["quarters"]
        padded = [None] * (MAX_QUARTERS - len(quarters)) + quarters
        cells = []
        for q in padded:
            if q is None:
                cells.append("")
            else:
                summary = q["summary"].replace("|", "\\|").replace("\n", " ")
                cells.append(f"**{q['quarter']}**: {summary}")
        name = (entry.get("company_name") or symbol).replace("|", "\\|")
        lines.append(f"| {name} ({symbol}) | " + " | ".join(cells) + " |")
    return "\n".join(lines) + "\n"


def main() -> None:
    state = load_state()
    merged = merge_cells(state)
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(json.dumps(state, indent=2, sort_keys=True))
    TABLE_PATH.write_text(render_table(state))
    print(f"Merged {merged} new quarter cell(s) across {len(state)} companies.")
    print(f"Wrote {STATE_PATH} and {TABLE_PATH}")


if __name__ == "__main__":
    main()
