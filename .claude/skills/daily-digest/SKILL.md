---
name: daily-digest
description: "Run the full daily concall pipeline for this repo: find every NSE-listed company that filed an earnings-call transcript today, pull each company's last 3-4 quarters of transcripts for context, write a per-company digest emphasizing forward guidance and whether management's past guidance held up, then commit and push. Use this whenever asked to run/update the daily concall digest, or on the scheduled daily run."
---

# Daily concall digest

Turns "which NSE companies had a concall today" into a set of per-company
Markdown digests, weighted toward forward guidance and whether management's
past guidance has actually held up — then commits everything to this repo.

## 0. Setup check

Run from the repo root. Confirm `pdftotext` is on PATH (`brew install
poppler` / `apt install poppler-utils` if not) and `curl` is available
(required — see script docstring for why plain Python HTTP clients don't
work against nseindia.com).

## 1. Find today's transcripts

```bash
python3 scripts/fetch_todays_transcripts.py -o tmp/nse_$(date +%Y%m%d)
```

This hits NSE's public corporate-announcements feed, filters to filings
tagged as concall updates that also mention "transcript" (excludes mere
schedule-of-meet notices), downloads each PDF, and converts to text. Read
the printed `manifest.json` — don't guess file paths.

**If `manifest["companies"]` is empty** (weekend, market holiday, or just a
quiet day before the evening filing rush), that's a valid outcome, not an
error. Write `digests/<date>/SUMMARY.md` with a single line noting zero
filings, commit, and stop — don't fabricate content to look busy.

## 2. Pull each company's history

For each company in the manifest, fetch its last 4 quarters from screener.in:

```bash
python3 scripts/fetch_historical_transcripts.py "<company_name>" -n 4 -o tmp/hist/<SYMBOL>
```

- Use the `company_name` field from the NSE manifest (screener's search
  usually resolves the exact legal name to the right slug automatically).
- Exit code 2 means an ambiguous match — candidates are printed to stderr.
  Try re-running with the most obviously-correct `--slug`. If it's still
  unclear, skip historical context for that company and note in its digest
  that only today's transcript was available.
- **De-duplicate against today's filing**: screener sometimes already lists
  the same quarter you just pulled from NSE (if it's had time to index it).
  Compare the newest entry in screener's manifest to today's NSE filing —
  if they're the same reporting quarter, drop that screener entry and use
  the remaining ones as the 3 prior quarters. You now have up to 4 total
  files per company: today's (from NSE) + up to 3 prior (from screener),
  oldest to newest.

## 3. Write each company's digest, in parallel batches

For each company, spawn one `Agent` (subagent_type: **concall-digest-writer**,
a project agent defined in `.claude/agents/concall-digest-writer.md`, tools
Read+Write, model sonnet). Give it: company name/symbol, the ordered list of
transcript `.txt` paths (oldest first, flag which one is today's), and the
destination path `digests/<date>/<SYMBOL>.md`.

Batch this **~8 companies at a time**, all in one message per batch (parallel
independent tool calls), rather than one-by-one or all-at-once — on a heavy
day (50+ filings is normal) spawning everything in a single burst is wasteful
and unnecessary serialization is slow. Move to the next batch once a batch's
calls return.

Why a dedicated writer agent instead of the `transcript-reader` pattern used
for single-company requests: that pattern deliberately keeps synthesis with
the orchestrator because it only ever handles one company's worth of
context at a time. Here there can be 50+ companies a day, so each company's
synthesis is fully delegated to its own agent instead — the guidance-vs-actual
judgment call is exactly the "catch the subtle tell" work that benefits from
sonnet over haiku (per `concall-digest-writer`'s model choice).

## 4. Build the day's index and commit

Write `digests/<date>/SUMMARY.md`: one line per company (symbol, company
name, one-line verdict pulled from its digest file), grouped by verdict
sentiment if that's easy to eyeball (credible/improving guidance vs.
walked-back/skeptical) — this is the file to skim first.

Then:

```bash
git add digests/
git commit -m "Concall digest for <date>: N companies"
git push
```

Don't commit `tmp/` (already gitignored) — raw PDFs/text are working files,
not the deliverable.

## Known constraints

- **NSE-listed only, current implementation.** BSE-only small-caps aren't
  covered; add a parallel BSE fetch script if that gap matters later (BSE's
  announcement API exists but wasn't wired up in v1).
- **Same-day transcript uploads only.** Some companies hold the concall
  today but don't upload the transcript for a few days (SEBI LODR Reg 46
  allows up to 5 working days) — those show up in a *later* day's run, not
  today's. This means "today's digest" is really "transcripts filed today,"
  not strictly "concalls held today." Don't conflate the two when
  presenting results.
- **NSE's API needs curl, not Python's HTTP stack** — see
  `scripts/fetch_todays_transcripts.py` docstring. If NSE starts blocking
  curl too, that's the first thing to re-diagnose (TLS fingerprinting, not
  a header problem).
- **screener.in scraping is regex-based** (vendored from the
  `transcript-summarizer` plugin) — if a site redesign breaks
  `parse_concalls()` in `scripts/fetch_historical_transcripts.py`, re-fetch
  a sample page and check for drift there before assuming a company just
  has no history.
