# concall-daily-digest

A personal, automated daily digest of NSE-listed companies' earnings-call
(concall) transcripts, kept as **one running table** — weighted toward
**forward guidance** and **whether management's past guidance has actually
held up**, not just restating results.

Every trading day:

1. Find every NSE company that filed a concall transcript today.
2. For each: compare against the previous quarter (fetched fresh only the
   first time a company is seen; reused from stored state every time after).
3. Write a compact per-quarter cell — forward guidance first, then a
   MET/BEAT/MISSED/PARTIAL tag against what was previously guided.
4. Merge into `digests/TABLE.md`: one row per company, up to 4
   quarter-columns, oldest column drops off as new ones arrive.
5. Rebuild `docs/index.html` — a color-coded view (green = guidance
   met/beat, red = missed, neutral = partial or not yet comparable),
   served by GitHub Pages: **https://raftar2097-source.github.io/concall-daily-digest/**
6. Pick the 3-5 most notable stories of the day and generate ready-to-post
   Instagram/YouTube Shorts copy plus a 3-image 1080x1080 carousel per
   story (`digests/highlights/`) — strictly factual, no BEAT/MISS-style
   opinion language, see `CLAUDE.md`'s "Public content / SEBI" section.
7. Commit and push.

See `CLAUDE.md` for the pipeline architecture (including why only 2
transcripts are read per company per run) and
`.claude/skills/daily-digest/SKILL.md` for the exact procedure.

## Run it

```bash
python3 scripts/fetch_todays_transcripts.py -o tmp/nse_$(date +%Y%m%d)
```

or, inside Claude Code, from this repo:

```
/daily-digest
```

## Requirements

- `pdftotext` (poppler-utils): `brew install poppler` / `apt install poppler-utils`
- `curl` on PATH (required — NSE's API blocks Python's own HTTP stack; see
  `scripts/fetch_todays_transcripts.py`)
- A headless-capable Chromium/Chrome binary (optional — only needed for
  `build_highlight_cards.py`'s image generation; the pipeline degrades
  gracefully without it, just skips the images)

## Layout

```
scripts/fetch_todays_transcripts.py       # NSE: today's filed transcripts
scripts/fetch_historical_transcripts.py   # screener.in: previous quarter (first-seen companies only)
scripts/filter_new_companies.py           # idempotency: skip companies already logged this quarter
scripts/build_table.py                    # deterministic merge: cells/*.json -> state.json -> TABLE.md
scripts/build_site.py                     # deterministic render: state.json -> docs/index.html
scripts/todays_updates.py                 # deterministic: today's newly-updated companies, for highlights
scripts/build_highlight_cards.py          # deterministic render: highlights JSON -> 1080x1080 PNG cards
.claude/agents/concall-digest-writer.md   # per-company cell writer (haiku)
.claude/agents/highlights-writer.md       # daily highlights + social copy writer (sonnet)
.claude/skills/daily-digest/SKILL.md      # the full daily procedure
digests/TABLE.md                          # plain-Markdown view: one row per company
digests/state.json                        # persistent rolling 4-quarter data behind both views
docs/index.html                           # color-coded HTML view, served by GitHub Pages
digests/highlights/<date>.json            # daily Instagram/YouTube Shorts copy (factual only)
digests/highlights/<DDMMYYYY>/*.png       # matching 1080x1080 carousel cards
```

## Scope

NSE-listed only (BSE-only microcaps not covered in v1). India equities.
"Filed a transcript today" is not exactly "held a concall today" — see
CLAUDE.md. The table starts sparse (2 of 4 columns per new company) and
fills in over real quarterly cycles by design, to keep per-run cost low
and flat rather than backfilling everything upfront.

## License

Personal use.
