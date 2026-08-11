#!/usr/bin/env python3
"""Drop companies from today's NSE manifest whose current quarter is
already recorded in digests/state.json — a cheap, deterministic check run
*before* any screener.in fetch or agent spend, so a same-day re-run (or a
company whose quarter was already logged by an earlier run) doesn't waste
a fetch+haiku-analysis cycle only to be silently deduped later at merge
time by build_table.py.

Usage:
    python3 filter_new_companies.py <manifest.json> [--state digests/state.json]

Prints the filtered manifest (same shape as the input, `companies` reduced)
to stdout, and a one-line skip count to stderr.
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_STATE_PATH = REPO_ROOT / "digests" / "state.json"


def quarter_label(date_str: str) -> str:
    """DD-MM-YYYY -> 'Mon YYYY', matching the label convention used
    throughout the rest of the pipeline (screener.in's own format)."""
    return datetime.strptime(date_str, "%d-%m-%Y").strftime("%b %Y")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("manifest", help="Path to today's fetch_todays_transcripts.py manifest.json")
    ap.add_argument("--state", default=str(DEFAULT_STATE_PATH), help="Path to digests/state.json")
    args = ap.parse_args()

    manifest = json.loads(Path(args.manifest).read_text())
    state_path = Path(args.state)
    state = json.loads(state_path.read_text()) if state_path.exists() else {}

    current_label = quarter_label(manifest["date"])

    kept, skipped = [], []
    for company in manifest["companies"]:
        symbol = company["symbol"]
        logged_labels = {q["quarter"] for q in state.get(symbol, {}).get("quarters", [])}
        if current_label in logged_labels:
            skipped.append(symbol)
        else:
            kept.append(company)

    manifest["companies"] = kept
    print(json.dumps(manifest, indent=2))
    print(
        f"{len(kept)} to process, {len(skipped)} already logged for {current_label} "
        f"(skipped: {', '.join(skipped) if skipped else 'none'})",
        file=__import__("sys").stderr,
    )


if __name__ == "__main__":
    main()
