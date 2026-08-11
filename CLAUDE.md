# CLAUDE.md

This file provides guidance to Claude Code when working in this repository.

**Keep this file current.** If a change alters the pipeline architecture —
a new data source, a different dedup strategy, a change to what
`digests/*.md` contains — update the relevant section in the same commit.

## What this is

A personal, automated daily digest of Indian (NSE-listed) earnings-call
transcripts, rendered as **one persistent table** — a plain-Markdown view
(`digests/TABLE.md`) and a color-coded HTML view
(`docs/index.html`, served by GitHub Pages at
**https://raftar2097-source.github.io/concall-daily-digest/**) — one row
per company, up to 4 quarter-columns, weighted toward **forward guidance**
and **whether management's past guidance has actually held up**, not just
"what were the numbers." Runs via the `daily-digest` skill
(`.claude/skills/daily-digest/SKILL.md`), which is the source of truth for
the step-by-step pipeline; this file is architecture context, not the
procedure itself.

**This repo is public**, unlike this user's other pipeline
(`stock-logbook`, which keeps a private data repo and pushes only a built
site to a separate public repo). That split exists there specifically to
get free GitHub Pages hosting on a private repo. Here, the repo had to
become public anyway for a different reason — claude.ai's Routines feature
(used for the daily cron trigger) can currently only see **public**
repositories, confirmed by inspecting its `code/repos` API response
(`is_complete: true`, zero private repos returned — not a caching issue).
Given that constraint already forced public visibility, there was no
reason to also run the two-repo split — `docs/index.html` is served
directly from this repo's own GitHub Pages. If claude.ai's connector ever
gains private-repo support, revisit whether to make this repo private
again and split off a `concall-daily-digest-site` repo the way
`stock-logbook` does.

**Cost is a first-class constraint, not an afterthought.** Every company
is one `haiku` agent call reading at most 2 transcripts (this quarter +
previous). See "Why only 2 transcripts" below — this was a deliberate
correction after the first version (4 quarters, `sonnet`) proved
expensive at ~110k tokens per company on a day with 56 filings.

## Pipeline architecture

```
NSE corporate-announcements API      digests/state.json (already known?)   screener.in
      │                                          │                              │
      │ today's transcript-tagged                │ previous-quarter summary     │ first time seeing
      │ filings                                  │ text, if this company's      │ this company only:
      ▼                                           │ been seen before             │ fetch previous
scripts/fetch_todays_transcripts.py               │                              │ transcript
      │                                           │                              ▼
      │ manifest.json: today's                    └──────────────┬───────────────┘
      │ transcript per company                                   │
      ▼                                                           │
scripts/filter_new_companies.py                                   │
      │ drops any company already logged                          │
      │ for this quarter — before any                              │
      │ fetch or agent spend happens                                │
      └───────────────────────────────┬──────────────────────────┘
                                       ▼
              Agent (concall-digest-writer, haiku, per company, parallel batches)
                                       │ writes a compact JSON cell (≤70 words/quarter,
                                       │ guidance-forward, MET/BEAT/MISSED tag if
                                       │ previous context was available)
                                       ▼
                        digests/cells/<SYMBOL>.json  (scratch, gitignored)
                                       │
                                       ▼
                      scripts/build_table.py  (deterministic, not an LLM step —
                                       │        avoids parallel agents racing on
                                       │        one shared state file)
                                       ▼
       digests/state.json (rolling 4-quarter window per company, committed)
                                       │
                                       ▼
                      scripts/build_site.py  (deterministic; reads state.json,
                                       │        color-codes by verdict)
                                       ▼
       digests/TABLE.md     (plain-Markdown view, committed + pushed)
       docs/index.html      (color-coded HTML view, served by GitHub Pages,
                              committed + pushed)
```

Two independent data sources feed each company's cells:

- **NSE** (`scripts/fetch_todays_transcripts.py`) is the trigger — it
  answers "who filed a transcript today" and provides that transcript
  itself. Requests go through `curl`, not Python's own HTTP stack — NSE's
  bot-protection 403s identical requests from Python's TLS stack but not
  curl's (fingerprinting, not a header check). See the script's docstring.
- `scripts/filter_new_companies.py` is the idempotency guard: a company
  already logged for the current quarter (e.g. a same-day re-run) is
  dropped before any screener.in fetch or agent spend, not just deduped
  later when `build_table.py` merges — the merge-time dedupe is a
  backstop, not the primary cost control.
- **screener.in** (`scripts/fetch_historical_transcripts.py`, vendored from
  the `transcript-summarizer` plugin — same repo owner, GitHub
  `raftar2097-source/transcript-summarizer`) is used **only the first time
  a company is seen**, to backfill one "previous quarter" cell. After
  that, `digests/state.json` already has the prior quarter's summary, so
  it's reused as context text instead of re-fetching or re-reading the raw
  transcript again.

## Why only 2 transcripts (not 4) per run

The table has 4 quarter-columns, but each *run* only ever reads 2
transcripts per company: today's (always) and, at most, one previous
(fetched fresh only on a company's first appearance; reused from
`state.json` every time after). The other columns aren't backfilled — they
fill in naturally as that company reports quarter after quarter over
roughly a year of real runs. A company will show blank cells on the left
of its row until it's been through enough cycles. This trades a slower
ramp to a full 4-quarter view for a flat, low, indefinitely-sustainable
per-run cost — consistent with this user's other pipelines
(`stock-logbook`) being built to run forever at near-zero cost rather than
optimized for day-one completeness.

## Why "filed a transcript today" isn't quite "held a concall today"

SEBI LODR Reg 46 gives companies up to 5 working days after a concall to
upload the transcript, though same-day is common. This pipeline keys off
*filing date*, not *call date* — a company that called yesterday but filed
today shows up in today's digest, one that called today but files
Thursday shows up Thursday's. Framed as "transcripts filed today," not
"concalls held today," in all user-facing output.

## Scope / known gaps

- NSE-listed only. BSE-only small/micro-caps aren't covered (BSE has an
  equivalent announcements API; not wired up in v1).
- `scripts/fetch_historical_transcripts.py`'s screener.in scraping is
  regex-based against the current page structure — a site redesign breaks
  `parse_concalls()` silently (returns no concalls) rather than erroring
  loudly. If a normally-covered company shows "no history," check that
  before assuming the company itself lacks transcripts.

## Data retention

`digests/state.json`, `digests/TABLE.md`, and `docs/index.html` are the
only things committed. Raw PDFs/`.txt` (`tmp/`) and per-company scratch
cells (`digests/cells/`) are gitignored — regenerable working files, not
worth the repo bloat of keeping forever. Daily history of the table itself
lives in git log, not as separate dated files.

## Secrets

None. Both data sources are public, unauthenticated endpoints.
