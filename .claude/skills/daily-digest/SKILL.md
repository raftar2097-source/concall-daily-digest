---
name: daily-digest
description: "Run the full daily concall pipeline for this repo: find every NSE-listed company that filed an earnings-call transcript today, compare each against its previous quarter, and update a persistent rolling 4-quarter table weighted toward forward guidance and whether management's past guidance held up. Then commit and push. Use this whenever asked to run/update the daily concall digest, or on the scheduled daily run."
---

# Daily concall digest

Turns "which NSE companies had a concall today" into updates to one
persistent table (`digests/TABLE.md`) — one row per company, up to 4
quarter-columns, weighted toward forward guidance and whether management's
guidance has actually held up. Built for daily, indefinite, low-cost
operation: `haiku` for the per-company writes, at most 2 transcripts ever
read per company per run, and a company already logged for the current
quarter is skipped entirely before any fetch or agent spend (step 1.5) —
so re-running the pipeline the same day is close to free.

## 0. Setup check

Run from the repo root. Confirm `pdftotext` and `curl` are on PATH (see
`scripts/fetch_todays_transcripts.py` docstring for why curl specifically
is required against nseindia.com).

## 1. Find today's transcripts

```bash
python3 scripts/fetch_todays_transcripts.py -o tmp/nse_$(date +%Y%m%d)
```

Read the printed `manifest.json`. **If `manifest["companies"]` is empty**
(weekend, holiday, or just early in the day before the evening filing
rush), that's a valid outcome — note it in the commit message and stop,
don't fabricate content.

## 1.5. Skip companies already logged for this quarter

```bash
python3 scripts/filter_new_companies.py tmp/nse_$(date +%Y%m%d)/manifest.json > tmp/manifest.filtered.json
```

This is a **deterministic pre-filter, not an LLM judgment call** — it drops
any company whose current-quarter label is already in `digests/state.json`
before any screener.in fetch or agent spend happens. It exists so a
same-day re-run (someone re-triggers the pipeline, or it's run twice)
doesn't burn a fetch-plus-haiku-analysis cycle on a company only to have it
silently deduped later at merge time by `build_table.py` — that later
dedupe is still a correctness backstop, but it shouldn't be the *only*
thing preventing wasted work. Use `tmp/manifest.filtered.json`'s
`companies` list for every step from here on, not the original manifest.

## 2. For each remaining company, decide what "previous" means

Read `digests/state.json` (may not exist yet — treat as `{}` if so). For
each company in the **filtered** manifest, derive `current`: quarter label =
today's date as `"%b %Y"` (e.g. "Aug 2026"), transcript = the `.txt` path
from step 1's manifest. Then, **per company**:

- **Already in `state.json` with a most-recent quarter label different
  from `current`'s label**: that stored entry's `summary` text *is* your
  "previous" — pass it to the writer agent as context text, **do not**
  fetch anything from screener.in for this company. (This is the case for
  almost every company after the pipeline has been running a while — it's
  the whole point of keeping state.)
- **Not in `state.json` yet (first time seen)**: fetch from screener.in —
  ```bash
  python3 scripts/fetch_historical_transcripts.py "<company_name>" -n 2 -o tmp/hist/<SYMBOL>
  ```
  Drop any returned quarter whose label matches `current`'s (screener may
  have already indexed today's filing — compare loosely, e.g. same month).
  If one remains, that's "previous" as a **file to read**. If none remain
  (genuinely no prior transcript, e.g. recently listed), there is no
  previous — the company gets only 1 cell this run.
  - Ambiguous name match (exit code 2): retry with the best `--slug` from
    stderr; if still unclear, treat as "no previous available" rather than
    guessing.

## 3. Write each company's cell(s), in parallel batches

For each company, spawn one `Agent` (subagent_type: **concall-digest-writer**,
project agent in `.claude/agents/concall-digest-writer.md`, haiku). Give it:
company name/symbol, `current`'s transcript path + label, `previous` as
determined above (a file path to read, or a summary string to use as
context, or absent), and destination `digests/cells/<SYMBOL>.json`.

Batch **~10-15 companies per message** (parallel independent Agent calls) —
haiku is cheap and fast enough that this batch size is fine; move to the
next batch once one returns.

## 4. Merge into the table and commit

```bash
python3 scripts/build_table.py
```

This is a plain deterministic script (not an LLM step, deliberately — see
its docstring) that merges every `digests/cells/*.json` into
`digests/state.json` (rolling window, most recent 4 quarters per company)
and re-renders `digests/TABLE.md` from it. Then:

```bash
git add digests/state.json digests/TABLE.md
git commit -m "Concall digest for <date>: N companies (M new, K first-seen)"
git push
```

Only `state.json` and `TABLE.md` are committed — `digests/cells/` is
scratch (gitignored, and `build_table.py` deletes processed files anyway).

## Known constraints

- **NSE-listed only, current implementation.** BSE-only small-caps aren't
  covered (BSE has an equivalent announcements API; not wired up in v1).
- **Same-day transcript uploads only** — SEBI LODR Reg 46 allows up to 5
  working days, so "today's digest" really means "transcripts filed
  today," not strictly "concalls held today."
- **Only 2 quarters are ever read per company per run**, by design (cost).
  The 4-quarter table fills in naturally over ~1 year of real runs as each
  company reports quarter after quarter — it is not backfilled on day one.
  A company will show blank cells on the left of its row until it's been
  through enough cycles.
- **`haiku` reads transcripts fairly literally** — it's the deliberate
  cost/quality tradeoff here (vs. the single-company `sonnet`-based
  `transcript-summarizer` plugin this pipeline's fetch scripts were
  vendored from). If a specific company's cells consistently read as
  generic positive paraphrase rather than catching real guidance
  shifts, that's a signal to special-case that company to `sonnet`, not a
  reason to change the default.
- **NSE's API needs curl, not Python's HTTP stack** (TLS fingerprinting,
  not a header problem — see the fetch script's docstring).
- **screener.in scraping is regex-based** — if a normally-covered company
  shows no history, check for site-structure drift in `parse_concalls()`
  before assuming the company itself lacks transcripts.
