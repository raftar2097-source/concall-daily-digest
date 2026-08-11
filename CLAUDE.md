# CLAUDE.md

This file provides guidance to Claude Code when working in this repository.

**Keep this file current.** If a change alters the pipeline architecture —
a new data source, a different dedup strategy, a change to what
`digests/*.md` contains — update the relevant section in the same commit.

## What this is

A personal, automated daily digest of Indian (NSE-listed) earnings-call
transcripts. Every trading day: find which companies filed a concall
transcript today, pull each company's last 3-4 quarters for context, and
write a per-company Markdown digest weighted toward **forward guidance**
and **whether management's past guidance has actually held up** — not just
"what were the numbers." Runs via the `daily-digest` skill
(`.claude/skills/daily-digest/SKILL.md`), which is the source of truth for
the step-by-step pipeline; this file is architecture context, not the
procedure itself.

## Pipeline architecture

```
NSE corporate-announcements API          screener.in (per company)
      │                                          │
      │ today's transcript-tagged filings        │ last 3-4 quarters'
      ▼                                           │ transcripts
scripts/fetch_todays_transcripts.py               ▼
      │                              scripts/fetch_historical_transcripts.py
      │ manifest.json: today's                    │ manifest.json: history
      │ transcripts, per company                  │
      └──────────────────┬────────────────────────┘
                          ▼
         Agent (concall-digest-writer, per company, parallel batches)
                          │ reads all transcripts for that company,
                          │ writes one digest emphasizing guidance +
                          │ guidance-vs-actual track record
                          ▼
              digests/<date>/<SYMBOL>.md
                          │
                          ▼
              digests/<date>/SUMMARY.md  (index, committed + pushed)
```

Two independent data sources feed each company's digest:

- **NSE** (`scripts/fetch_todays_transcripts.py`) is the trigger — it
  answers "who filed a transcript today" and provides that transcript
  itself. Requests go through `curl`, not Python's own HTTP stack — NSE's
  bot-protection 403s identical requests from Python's TLS stack but not
  curl's (fingerprinting, not a header check). See the script's docstring.
- **screener.in** (`scripts/fetch_historical_transcripts.py`, vendored from
  the `transcript-summarizer` plugin — same repo owner, GitHub
  `raftar2097-source/transcript-summarizer`) supplies the prior 3-4
  quarters needed to judge whether guidance held up. No auth needed either.

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

`digests/*.md` (the deliverable) is the only thing committed. Raw PDFs and
extracted `.txt` live under `tmp/`, gitignored — they're regenerable working
files, not worth the repo bloat of keeping forever.

## Secrets

None. Both data sources are public, unauthenticated endpoints.
