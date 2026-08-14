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
                                       │
                                       ▼
                      scripts/todays_updates.py  (deterministic; pulls today's
                                       │           newly-updated companies out
                                       │           of state.json)
                                       ▼
              Agent (highlights-writer, sonnet, one call for the whole day)
                                       │ picks 3-5 notable stories, writes
                                       │ factual Instagram/YouTube Shorts copy
                                       │ + structured `slides` data per story
                                       ▼
       digests/highlights/<date>.json  (committed — see "Public content /
                                       │  SEBI" below before touching this
                                       │  agent's output rules)
                                       ▼
              scripts/build_highlight_cards.py  (deterministic; renders
                                       │  `slides` into 3 PNGs/story via
                                       │  headless Chromium — skips itself
                                       │  gracefully if none is available)
                                       ▼
       digests/highlights/<DDMMYYYY>/*.png  (1080x1080 Instagram-carousel
                                              cards, committed)
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

## Public content / SEBI

`digests/highlights/<date>.json` feeds public posting (Instagram, YouTube
Shorts) — this is the one place this pipeline's output is meant to reach a
public audience rather than just the operator. That changes the legal
posture: SEBI's Research Analyst Regulations, 2014 require registration
(NISM-Series-XV certification + SEBI registration) for anyone publishing
recommendations, price targets, or "opinions that facilitate a basis for
investment purposes" **for compensation** — and SEBI's 2024-2025
finfluencer enforcement has specifically targeted unregistered social-media
financial content.

The `verdict` field (`beat`/`missed`/etc.) used internally for
`docs/index.html`'s color-coding is exactly that kind of opinion. It's
fine to keep computing and displaying it site-side (informational, not
optimized for reach), but `highlights-writer` deliberately never emits it
or paraphrases of it — its copy is restricted to **factual restatement**
("management guided X, delivered Y"), checked against a real precedent:
concall.in (a funded, ~15k-user, monetized competitor) does the identical
thing — their public concall summaries are organized by theme and
strictly descriptive, no buy/sell/rating language anywhere.

**If this pipeline is ever monetized**, the two honest paths are (a) keep
public output factual-only as it is now, sell access to the verdict/
guidance-track-record data as the paid differentiator, or (b) get NISM
certified + SEBI RA registered if the scored/opinion version itself is
what's being sold. Don't blur this line by making public copy "punchier"
over time — that drift is exactly what the regulation targets.

## Scope / known gaps

- NSE-listed only. BSE-only small/micro-caps aren't covered (BSE has an
  equivalent announcements API; not wired up in v1).
- `scripts/fetch_historical_transcripts.py`'s screener.in scraping is
  regex-based against the current page structure — a site redesign breaks
  `parse_concalls()` silently (returns no concalls) rather than erroring
  loudly. If a normally-covered company shows "no history," check that
  before assuming the company itself lacks transcripts.
- **`scripts/build_highlight_cards.py` needs a headless Chromium/Chrome
  binary** on the machine it runs on. Not present by default on the cloud
  routine's environment — the environment's setup script installs it via
  apt (`chromium` or `chromium-browser`, whichever the image has). If
  that ever stops working, the script degrades gracefully (skips images,
  keeps the text content), it doesn't fail the run — check the
  environment's setup script output before assuming the renderer itself
  broke.
- **`scripts/todays_updates.py` matches on quarter label, which is
  month-granular** (e.g. "Aug 2026"), not day-granular. On the *second or
  later* run within the same calendar month, it returns every company
  whose latest quarter is that month's label — including companies from
  earlier runs that month, not just the run that just happened. First
  surfaced 13-08-2026 (second run of the month; the script returned all
  142 companies logged since 12-08-2026 instead of that day's 32). Until
  the script itself is fixed (e.g. track filing date, not just quarter
  label), whoever drives step 5 should filter `todays_updates.py`'s output
  down to the symbols actually processed in that run (available from step
  1.5's filtered manifest) before handing it to `highlights-writer` —
  otherwise "today's highlights" can resurface a company already featured
  on an earlier day this month.

## Data retention

`digests/state.json`, `digests/TABLE.md`, `docs/index.html`,
`digests/highlights/<date>.json`, and `digests/highlights/<DDMMYYYY>/*.png`
are committed. Raw PDFs/`.txt` (`tmp/`) and per-company scratch cells
(`digests/cells/`) are gitignored —
regenerable working files, not worth the repo bloat of keeping forever.
`highlights/` is kept as dated files (unlike the table) specifically so
there's a record of exactly what copy was posted publicly on a given day.

## Secrets

None. Both data sources are public, unauthenticated endpoints.
