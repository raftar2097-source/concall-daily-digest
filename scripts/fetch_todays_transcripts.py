#!/usr/bin/env python3
"""Find NSE-listed companies that filed an earnings-call transcript today
(or on a given date) and download those transcripts.

No API key needed — this replays the same JSON endpoint the NSE website
itself calls (`/api/corporate-announcements`), which requires only a
browser-like session cookie (obtained by hitting the homepage first) and a
Referer header. The transcript PDFs themselves are hosted on NSE's public
archive (nsearchives.nseindia.com) and need no auth at all.

Requests are shelled out to `curl` rather than made with Python's
`urllib`/`requests`: NSE's bot-protection layer 403s the identical request
(same headers, same UA) when it comes from Python's TLS stack, but allows
it from curl's — a TLS-fingerprint check, not a headers check. This is a
known quirk of nseindia.com, not specific to this script.

NSE tags every "concall happened / scheduled" filing under one category —
`Analysts/Institutional Investor Meet/Con. Call Updates` — which covers both
*advance notice* of an upcoming call and the *actual transcript* uploaded
afterwards (SEBI LODR Reg 30 requires the transcript within a few days, but
companies often upload same-day). This script keeps only the latter, by
requiring the word "transcript" in the filing's description or attachment
filename.

Usage:
    python3 fetch_todays_transcripts.py                       # today, IST
    python3 fetch_todays_transcripts.py --date 11-08-2026
    python3 fetch_todays_transcripts.py -o /tmp/nse_2026-08-11

Output: <outdir>/<SYMBOL>.pdf, <outdir>/<SYMBOL>.txt for each company, plus
<outdir>/manifest.json describing what was found. manifest.json (and only
it) is also printed to stdout on success.
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/122.0 Safari/537.36"
)
IST = timezone(timedelta(hours=5, minutes=30))
CONCALL_DESC = "Analysts/Institutional Investor Meet/Con. Call Updates"
TRANSCRIPT_RE = re.compile(r"transcript", re.IGNORECASE)


class NseSession:
    """Thin wrapper around curl: NSE's bot-protection 403s Python's own TLS
    stack (urllib and requests alike) even with identical headers, but
    allows curl's — so all requests go through curl with a shared cookie
    jar rather than a Python HTTP client."""

    def __init__(self) -> None:
        if not shutil.which("curl"):
            raise RuntimeError("curl not found on PATH")
        self._cookie_jar = Path(tempfile.mkstemp(prefix="nse_cookies_")[1])
        self._run(["-c", str(self._cookie_jar), "https://www.nseindia.com/", "-o", "/dev/null"])

    def _run(self, extra_args: list[str]) -> bytes:
        cmd = [
            "curl", "-s", "-A", UA,
            "-b", str(self._cookie_jar), "-c", str(self._cookie_jar),
            *extra_args,
        ]
        result = subprocess.run(cmd, capture_output=True, check=True)
        return result.stdout

    def get_json(self, url: str, referer: str) -> object:
        raw = self._run(["-H", f"Referer: {referer}", "-H", "Accept: application/json", url])
        return json.loads(raw)

    def download(self, url: str, dest: Path) -> None:
        raw = self._run([url])
        dest.write_bytes(raw)


def fetch_announcements(session: NseSession, date_str: str) -> list[dict]:
    url = (
        "https://www.nseindia.com/api/corporate-announcements"
        f"?index=equities&from_date={date_str}&to_date={date_str}"
    )
    return session.get_json(url, referer="https://www.nseindia.com/companies-listing/corporate-filings-announcements")


def is_transcript_filing(item: dict) -> bool:
    if item.get("desc") != CONCALL_DESC:
        return False
    haystack = (item.get("attchmntText") or "") + " " + (item.get("attchmntFile") or "")
    return bool(TRANSCRIPT_RE.search(haystack))


def dedupe_latest_per_symbol(items: list[dict]) -> list[dict]:
    """A company can file more than one transcript-tagged item in a day
    (e.g. a re-upload or a correction) — keep the most recent (by an_dt)."""
    best: dict[str, dict] = {}
    for item in items:
        sym = item["symbol"]
        if sym not in best or item["an_dt"] > best[sym]["an_dt"]:
            best[sym] = item
    return list(best.values())


def pdf_to_text(pdf_path: Path, txt_path: Path) -> None:
    if not shutil.which("pdftotext"):
        raise RuntimeError(
            "pdftotext not found on PATH. Install poppler: `brew install poppler` "
            "(macOS) or `apt install poppler-utils` (Debian/Ubuntu)."
        )
    subprocess.run(["pdftotext", str(pdf_path), str(txt_path)], check=True)
    # Best-effort strip of the "Sub: Disclosure under Regulation 30..."
    # cover letter every exchange filing is wrapped in, up to the first
    # "Moderator:" line (bounded so a transcript without that convention
    # never gets truncated).
    lines = txt_path.read_text(errors="replace").splitlines()
    for i, line in enumerate(lines[:120]):
        if re.match(r"^\s*moderator\s*:?\s*$", line, re.IGNORECASE):
            txt_path.write_text("\n".join(lines[i:]))
            break


def slugify(s: str) -> str:
    return re.sub(r"[^A-Za-z0-9_-]+", "_", s).strip("_")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--date", default=None, help="DD-MM-YYYY (default: today, IST)")
    ap.add_argument("-o", "--outdir", default=None, help="Output directory (default: ./nse_transcripts/<date>)")
    args = ap.parse_args()

    date_str = args.date or datetime.now(IST).strftime("%d-%m-%Y")
    outdir = Path(args.outdir) if args.outdir else Path("nse_transcripts") / date_str.replace("-", "")
    outdir.mkdir(parents=True, exist_ok=True)

    try:
        session = NseSession()
        announcements = fetch_announcements(session, date_str)
    except (subprocess.CalledProcessError, json.JSONDecodeError, RuntimeError) as e:
        print(f"NSE API request failed: {e}", file=sys.stderr)
        sys.exit(1)

    transcripts = dedupe_latest_per_symbol([a for a in announcements if is_transcript_filing(a)])
    transcripts.sort(key=lambda a: a["symbol"])

    manifest = {"date": date_str, "source": "nseindia.com/api/corporate-announcements", "companies": []}

    for i, item in enumerate(transcripts, start=1):
        symbol = item["symbol"]
        pdf_url = item["attchmntFile"]
        pdf_path = outdir / f"{slugify(symbol)}.pdf"
        txt_path = outdir / f"{slugify(symbol)}.txt"
        print(f"[{i}/{len(transcripts)}] {symbol}: {pdf_url}", file=sys.stderr)
        try:
            session.download(pdf_url, pdf_path)
            pdf_to_text(pdf_path, txt_path)
        except Exception as e:  # noqa: BLE001 - report and continue with the rest
            print(f"  FAILED for {symbol}: {e}", file=sys.stderr)
            continue
        manifest["companies"].append({
            "symbol": symbol,
            "company_name": item.get("sm_name"),
            "isin": item.get("sm_isin"),
            "industry": item.get("smIndustry"),
            "filed_at": item.get("an_dt"),
            "pdf_url": pdf_url,
            "pdf_path": str(pdf_path),
            "txt_path": str(txt_path),
        })

    (outdir / "manifest.json").write_text(json.dumps(manifest, indent=2))
    print(json.dumps(manifest, indent=2))


if __name__ == "__main__":
    main()
