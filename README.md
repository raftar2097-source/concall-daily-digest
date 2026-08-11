# concall-daily-digest

A personal, automated daily digest of NSE-listed companies' earnings-call
(concall) transcripts — weighted toward **forward guidance** and **whether
management's past guidance has actually held up**, not just restating
results.

Every trading day:

1. Find every NSE company that filed a concall transcript today.
2. Pull each company's last 3-4 quarters of transcripts from screener.in
   for context.
3. Write a per-company digest: forward guidance, this quarter's
   commentary, a guidance-vs-actual track record across the last 3-4
   quarters (met/beat/missed/quietly-dropped), tone trend, one-line verdict.
4. Commit everything to `digests/<date>/` and push.

See `CLAUDE.md` for the pipeline architecture and
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

## Layout

```
scripts/fetch_todays_transcripts.py       # NSE: today's filed transcripts
scripts/fetch_historical_transcripts.py   # screener.in: last N quarters for a company
.claude/agents/concall-digest-writer.md   # per-company digest writer
.claude/skills/daily-digest/SKILL.md      # the full daily procedure
digests/<date>/SUMMARY.md                 # index, skim this first
digests/<date>/<SYMBOL>.md                # per-company digest
```

## Scope

NSE-listed only (BSE-only microcaps not covered in v1). India equities.
"Filed a transcript today" is not exactly "held a concall today" — see
CLAUDE.md.

## License

Personal use.
