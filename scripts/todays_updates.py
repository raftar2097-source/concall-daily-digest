#!/usr/bin/env python3
"""List today's newly-updated companies from digests/state.json, for the
highlights-writer agent to pick stories from.

A company counts as "today's" if its most recent logged quarter matches
today's label — i.e. it was touched by this run (either first-seen or a
returning company whose current quarter just got appended).

Usage:
    python3 todays_updates.py --date 11-08-2026
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
STATE_PATH = REPO_ROOT / "digests" / "state.json"


def quarter_label(date_str: str) -> str:
    return datetime.strptime(date_str, "%d-%m-%Y").strftime("%b %Y")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--date", required=True, help="DD-MM-YYYY, the digest run's target date")
    args = ap.parse_args()

    label = quarter_label(args.date)
    state = json.loads(STATE_PATH.read_text()) if STATE_PATH.exists() else {}

    todays = []
    for symbol, entry in state.items():
        quarters = entry.get("quarters", [])
        if quarters and quarters[-1]["quarter"] == label:
            todays.append({
                "symbol": symbol,
                "company_name": entry.get("company_name"),
                "summary": quarters[-1]["summary"],
                "verdict": quarters[-1].get("verdict"),
            })

    print(json.dumps({"date": args.date, "companies": todays}, indent=2))


if __name__ == "__main__":
    main()
