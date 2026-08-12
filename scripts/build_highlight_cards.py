#!/usr/bin/env python3
"""Render each story in digests/highlights/<date>.json into a 3-slide
1080x1080 Instagram-carousel image set (hook / stats / context).

Deterministic, not an LLM step — the highlights-writer agent already
produced the structured `slides` data per story; this just lays it out
into HTML and rasterizes it via a headless browser. Same reasoning as
build_table.py / build_site.py: no judgment calls left to make by the time
this runs.

Requires a headless-capable Chromium/Chrome binary on PATH or in one of
the common install locations. If none is found, this script prints a
clear warning and exits 0 without writing images — the text content
(captions, scripts) in highlights/<date>.json is still complete and usable
on its own, so a missing browser degrades this feature gracefully rather
than failing the whole daily run.

Usage:
    python3 build_highlight_cards.py digests/highlights/11-08-2026.json
"""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path

CANDIDATE_BROWSERS = [
    "chromium", "chromium-browser", "google-chrome", "google-chrome-stable",
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
]

CARD_CSS = """
* { margin: 0; padding: 0; box-sizing: border-box; }
html, body { width: 1080px; height: 1080px; overflow: hidden; background: #14181A; }
.card { width: 1080px; height: 1080px; display: flex; flex-direction: column; padding: 84px; }
.eyebrow { font-family: ui-monospace, "SF Mono", Menlo, Consolas, monospace; font-size: 24px;
  letter-spacing: .1em; text-transform: uppercase; color: #98A39D; }
.company { font-family: ui-monospace, "SF Mono", Menlo, Consolas, monospace; font-size: 30px;
  letter-spacing: .05em; color: #98A39D; margin-top: 14px; }
.serif { font-family: Georgia, "Iowan Old Style", "Times New Roman", serif; }
.mono { font-family: ui-monospace, "SF Mono", Menlo, Consolas, monospace; }
.footer { font-family: ui-monospace, monospace; font-size: 22px; color: #616D67;
  display: flex; justify-content: space-between; margin-top: auto; padding-top: 24px; }
.hook { display: flex; flex-direction: column; justify-content: center; flex: 1; gap: 4px; }
.hook .line { font-family: Georgia, serif; font-size: 72px; line-height: 1.2; color: #E7ECE9; font-weight: 600; max-width: 900px; }
.stats-wrap { display: flex; flex-direction: column; justify-content: center; flex: 1; gap: 40px; }
.stat { border-radius: 20px; padding: 44px 48px; display: flex; flex-direction: column; gap: 16px; border-left: 8px solid; }
.stat.pos { background: #1E3226; border-left-color: #7DCB9C; }
.stat.neg { background: #362320; border-left-color: #E39678; }
.stat.neutral { background: #352C1B; border-left-color: #E0BC72; }
.stat .label { font-family: ui-monospace, monospace; font-size: 26px; letter-spacing: .06em; text-transform: uppercase; color: #98A39D; }
.stat .value { font-family: Georgia, serif; font-size: 54px; color: #E7ECE9; font-weight: 600; display: flex; align-items: baseline; gap: 18px; flex-wrap: wrap; }
.stat .tag { font-family: ui-monospace, monospace; font-size: 22px; font-weight: 700; padding: 6px 14px; border-radius: 6px; letter-spacing: .05em; }
.stat.pos .tag { background: #7DCB9C; color: #10201A; }
.stat.neg .tag { background: #E39678; color: #2A1712; }
.stat.neutral .tag { background: #E0BC72; color: #2A2010; }
.context-wrap { display: flex; flex-direction: column; justify-content: center; flex: 1; gap: 40px; }
.context-title { font-family: Georgia, serif; font-size: 44px; color: #E7ECE9; font-weight: 600; margin-top: 12px; }
.grid { display: flex; gap: 32px; }
.box { flex: 1; background: #1B2123; border: 1px solid #2B3335; border-radius: 16px; padding: 36px; display: flex; flex-direction: column; gap: 12px; }
.box .label { font-family: ui-monospace, monospace; font-size: 22px; color: #616D67; text-transform: uppercase; letter-spacing: .05em; }
.box .val { font-family: Georgia, serif; font-size: 46px; color: #E7ECE9; font-weight: 600; }
.disclaimer { font-family: ui-monospace, monospace; font-size: 22px; color: #616D67; line-height: 1.6; border-top: 1px solid #2B3335; padding-top: 28px; }
"""


def esc(s: str) -> str:
    return (s or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def render_hook(story: dict) -> str:
    lines = "".join(f'<div class="line">{esc(l)}</div>' for l in story["slides"]["hook"])
    return f"""<!doctype html><html><head><meta charset="utf-8"><style>{CARD_CSS}</style></head><body>
<div class="card">
  <div><div class="eyebrow">Today's Concall</div><div class="company">{esc(story['company_name'])} &middot; {esc(story['symbol'])}</div></div>
  <div class="hook">{lines}</div>
  <div class="footer"><span>Concall Daily Digest</span><span>{esc(story['_date_display'])}</span></div>
</div></body></html>"""


def render_stats(story: dict) -> str:
    boxes = ""
    for s in story["slides"]["stats"]:
        boxes += f"""<div class="stat {s['direction']}">
      <div class="label">{esc(s['label'])}</div>
      <div class="value">{esc(s['value'])} <span class="tag">{esc(s['tag'])}</span></div>
    </div>"""
    return f"""<!doctype html><html><head><meta charset="utf-8"><style>{CARD_CSS}</style></head><body>
<div class="card">
  <div class="eyebrow">{esc(story['company_name'])} ({esc(story['symbol'])})</div>
  <div class="stats-wrap">{boxes}</div>
  <div class="footer"><span>Concall Daily Digest</span><span>{esc(story['_date_display'])}</span></div>
</div></body></html>"""


def render_context(story: dict) -> str:
    boxes = ""
    for c in story["slides"]["context_stats"]:
        sub = f'<div class="label">{esc(c["sub"])}</div>' if c.get("sub") else ""
        boxes += f"""<div class="box"><div class="label">{esc(c['label'])}</div><div class="val">{esc(c['value'])}</div>{sub}</div>"""
    return f"""<!doctype html><html><head><meta charset="utf-8"><style>{CARD_CSS}</style></head><body>
<div class="card">
  <div class="context-wrap">
    <div>
      <div class="eyebrow">{esc(story['company_name'])} ({esc(story['symbol'])})</div>
      <div class="context-title">{esc(story['slides']['context_title'])}</div>
    </div>
    <div class="grid">{boxes}</div>
    <div class="disclaimer">Factual summary of public company disclosures.<br>Not investment advice.</div>
  </div>
  <div class="footer"><span>Concall Daily Digest</span><span>{esc(story['_date_display'])}</span></div>
</div></body></html>"""


def find_browser() -> str | None:
    for candidate in CANDIDATE_BROWSERS:
        if "/" in candidate:
            if Path(candidate).exists():
                return candidate
        else:
            found = shutil.which(candidate)
            if found:
                return found
    return None


def screenshot(browser: str, html_path: Path, png_path: Path) -> None:
    subprocess.run(
        [browser, "--headless", "--disable-gpu", "--no-sandbox",
         f"--screenshot={png_path}", "--window-size=1080,1080", f"file://{html_path}"],
        check=True, capture_output=True,
    )


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("highlights_json", help="Path to digests/highlights/<date>.json")
    args = ap.parse_args()

    highlights_path = Path(args.highlights_json)
    data = json.loads(highlights_path.read_text())
    date_str = data["date"]  # DD-MM-YYYY
    date_display = "-".join(reversed(date_str.split("-")))[:10]  # cheap DD-MM-YYYY -> readable-ish

    browser = find_browser()
    if browser is None:
        print(
            "No headless Chromium/Chrome found on this machine — skipping image "
            "generation. Text content in highlights JSON is unaffected.",
            file=sys.stderr,
        )
        return

    out_dir = highlights_path.parent / date_str.replace("-", "")
    out_dir.mkdir(parents=True, exist_ok=True)
    tmp_html_dir = out_dir / "_html"
    tmp_html_dir.mkdir(exist_ok=True)

    written = []
    for story in data["stories"]:
        if "slides" not in story:
            print(f"  skipping {story['symbol']}: no slides data", file=sys.stderr)
            continue
        story["_date_display"] = date_str
        renderers = [("1-hook", render_hook), ("2-stats", render_stats), ("3-context", render_context)]
        for suffix, fn in renderers:
            html_path = tmp_html_dir / f"{story['symbol']}-{suffix}.html"
            png_path = out_dir / f"{story['symbol']}-{suffix}.png"
            html_path.write_text(fn(story))
            try:
                screenshot(browser, html_path.resolve(), png_path.resolve())
                written.append(str(png_path))
            except subprocess.CalledProcessError as e:
                print(f"  FAILED {png_path.name}: {e.stderr.decode(errors='replace')[:300]}", file=sys.stderr)

    shutil.rmtree(tmp_html_dir, ignore_errors=True)
    print(f"Wrote {len(written)} card images to {out_dir}")


if __name__ == "__main__":
    main()
