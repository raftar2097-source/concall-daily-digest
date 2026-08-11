#!/usr/bin/env python3
"""Fetch the most recent quarterly concall transcripts for a company from
screener.in and convert each to plain text.

No API key or login needed — screener.in's concall list and the underlying
BSE-hosted transcript PDFs are both public. Uses only the Python stdlib
plus the `pdftotext` binary (poppler-utils) for PDF -> text.

Usage:
    python3 fetch_transcripts.py "Reliance Industries" -n 4
    python3 fetch_transcripts.py --slug TCS -n 4 -o /tmp/tcs_transcripts

If the company name is ambiguous, prints the candidate slugs to stderr and
exits 2 — re-run with --slug <SLUG> to disambiguate.

Output: <outdir>/<quarter-slug>.pdf, <outdir>/<quarter-slug>.txt for each
fetched quarter, plus <outdir>/manifest.json describing what was fetched.
manifest.json (and only it) is also printed to stdout on success.
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import quote
from urllib.request import Request, urlopen

UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0 Safari/537.36"
)


def http_get(url: str, referer: str | None = None) -> tuple[bytes, str]:
    headers = {"User-Agent": UA}
    if referer:
        headers["Referer"] = referer
    req = Request(url, headers=headers)
    with urlopen(req, timeout=30) as resp:
        return resp.read(), resp.geturl()


def search_company(query: str) -> list[dict]:
    url = f"https://www.screener.in/api/company/search/?q={quote(query)}"
    data, _ = http_get(url)
    return json.loads(data)


def fetch_company_page(slug: str) -> tuple[str, str]:
    """Try the consolidated view first, fall back to the standalone-only
    page for companies screener has no consolidated financials for."""
    last_err: Exception | None = None
    for path in (f"/company/{slug}/consolidated/", f"/company/{slug}/"):
        url = f"https://www.screener.in{path}"
        try:
            data, final_url = http_get(url)
            return data.decode("utf-8", errors="replace"), final_url
        except HTTPError as e:
            if e.code == 404:
                last_err = e
                continue
            raise
    raise RuntimeError(f"Could not load a screener.in page for slug {slug!r}: {last_err}")


def parse_concalls(html: str) -> list[dict]:
    """Extract [{quarter, pdf_urls: [...]}], newest first, from the Concalls
    block.

    Screener renders one <li> per concall entry with a date label div and an
    <a class="concall-link" ... title="Raw Transcript">Transcript</a>
    pointing at a transcript PDF (usually BSE-hosted, sometimes on the
    company's own investor-relations site). Attribute order on that <a> is
    not fixed, so the tag is matched as a whole and href is pulled out
    separately.

    The same quarter can legitimately appear in more than one <li> (e.g. a
    BSE filing plus the company's own copy of the same transcript) — those
    are collapsed into one entry with multiple candidate URLs, since a
    later fallback should try them as alternates for the *same* quarter
    rather than consuming a second slot out of the requested quarter count.
    """
    idx = html.find("documents concalls")
    if idx == -1:
        return []
    section = html[idx:]
    by_quarter: dict[str, list[str]] = {}
    order: list[str] = []
    for li in re.split(r'<li class="flex flex-gap-8', section)[1:]:
        date_m = re.search(r'class="ink-600[^"]*"[^>]*>\s*([^<]+?)\s*</div>', li)
        a_m = re.search(r"<a\b([^>]*)>\s*Transcript\s*</a>", li)
        if not date_m or not a_m:
            continue
        href_m = re.search(r'href="([^"]+)"', a_m.group(1))
        if not href_m:
            continue
        quarter = date_m.group(1).strip()
        url = href_m.group(1)
        if quarter not in by_quarter:
            by_quarter[quarter] = []
            order.append(quarter)
        if url not in by_quarter[quarter]:
            by_quarter[quarter].append(url)
    return [{"quarter": q, "pdf_urls": by_quarter[q]} for q in order]


def download_pdf(url: str, dest: Path, referer: str) -> None:
    data, _ = http_get(url, referer=referer)
    dest.write_bytes(data)


def pdf_to_text(pdf_path: Path, txt_path: Path) -> None:
    """Convert to plain text (no -layout) and strip the regulatory
    cover-letter boilerplate every BSE-hosted transcript is wrapped in.

    -layout preserves column-alignment whitespace, which matters for
    tabular financial statements but is pure token bloat for a
    dialogue-heavy transcript (~22% smaller without it on a sample file,
    with no loss of readability). The cover letter (addressed to
    NSE/BSE, "Sub: Disclosure under Regulation 30...") is identical
    boilerplate across filings and contributes nothing to a summary, so
    it's cut up to the first "Moderator:" line — bounded to the first 80
    lines so this never accidentally truncates a transcript that happens
    not to use that exact convention.
    """
    if not shutil.which("pdftotext"):
        raise RuntimeError(
            "pdftotext not found on PATH. Install poppler: `brew install poppler` "
            "(macOS) or `apt install poppler-utils` (Debian/Ubuntu)."
        )
    subprocess.run(["pdftotext", str(pdf_path), str(txt_path)], check=True)

    lines = txt_path.read_text(errors="replace").splitlines()
    for i, line in enumerate(lines[:80]):
        if re.match(r"^\s*moderator\s*:?\s*$", line, re.IGNORECASE):
            txt_path.write_text("\n".join(lines[i:]))
            break


def slugify(s: str) -> str:
    return re.sub(r"[^A-Za-z0-9_-]+", "_", s).strip("_")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("company", nargs="?", help="Company name to search for, e.g. 'Reliance Industries'")
    ap.add_argument("--slug", help="Exact screener.in slug (e.g. RELIANCE, TCS) — skips search/disambiguation")
    ap.add_argument("-n", "--quarters", type=int, default=4, help="Number of most recent quarters to fetch (default: 4)")
    ap.add_argument("-o", "--outdir", default=None, help="Output directory (default: ./screener_transcripts/<slug>)")
    args = ap.parse_args()

    if not args.company and not args.slug:
        ap.error("provide a company name or --slug")

    if args.slug:
        slug = args.slug
        company_name = args.slug
    else:
        results = search_company(args.company)
        if not results:
            print(f"No screener.in match found for {args.company!r}", file=sys.stderr)
            sys.exit(1)
        if len(results) > 1:
            exact = [r for r in results if r["name"].lower() == args.company.lower()]
            if len(exact) == 1:
                results = exact
            else:
                print(f"Multiple matches for {args.company!r}:", file=sys.stderr)
                for r in results:
                    r_slug = r["url"].strip("/").split("/")[1]
                    print(f"  {r['name']}  ->  --slug {r_slug}", file=sys.stderr)
                print("Re-run with --slug <SLUG> to pick one.", file=sys.stderr)
                sys.exit(2)
        company_name = results[0]["name"]
        slug = results[0]["url"].strip("/").split("/")[1]

    html, page_url = fetch_company_page(slug)
    concalls = parse_concalls(html)
    if not concalls:
        print(f"No concall transcripts found on {page_url}", file=sys.stderr)
        sys.exit(1)

    chosen = concalls[: args.quarters]

    outdir = Path(args.outdir) if args.outdir else Path("screener_transcripts") / slugify(slug)
    outdir.mkdir(parents=True, exist_ok=True)

    manifest = {"company": company_name, "slug": slug, "source_page": page_url, "quarters": []}

    for i, item in enumerate(chosen, start=1):
        qslug = slugify(item["quarter"])
        pdf_path = outdir / f"{qslug}.pdf"
        txt_path = outdir / f"{qslug}.txt"
        used_url = None
        for candidate_url in item["pdf_urls"]:
            print(f"[{i}/{len(chosen)}] {item['quarter']}: trying {candidate_url}", file=sys.stderr)
            try:
                download_pdf(candidate_url, pdf_path, referer=page_url)
                pdf_to_text(pdf_path, txt_path)
                used_url = candidate_url
                break
            except Exception as e:  # noqa: BLE001 - try next candidate / report and move on
                print(f"  failed ({e}); trying next source if any", file=sys.stderr)
        if used_url is None:
            print(f"  ALL SOURCES FAILED for {item['quarter']}", file=sys.stderr)
            continue
        manifest["quarters"].append(
            {
                "quarter": item["quarter"],
                "pdf_url": used_url,
                "pdf_path": str(pdf_path),
                "txt_path": str(txt_path),
            }
        )

    if not manifest["quarters"]:
        print("All downloads failed — nothing to summarize.", file=sys.stderr)
        sys.exit(1)

    (outdir / "manifest.json").write_text(json.dumps(manifest, indent=2))
    print(json.dumps(manifest, indent=2))


if __name__ == "__main__":
    main()
