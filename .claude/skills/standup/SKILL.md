---
name: standup
description: The company standup - report current state from the company/ state files (done / in-flight / blocked / decisions-needed), gate status, open CRs, and top worries, without starting any work. Use when the user says /standup, "status?", "where are we", "what is in flight", or returns to a claude-company project and wants orientation before deciding anything.
---

# /standup - state of the company

Report only - do not dispatch agents, do not start work, do not fix things you
notice (note them as worries instead).

Read, in order: `company/state/RESUME.md`, `company/state/STATUS.md`,
`company/state/WORRIES.md`, `company/state/DECISIONS.md`,
`company/state/active-task.json` (if present - it lists every task entry in
flight in this working tree), open CRs in `company/change-requests/`,
`git log --oneline -10`, and the tail of
`company/state/adherence.log`. Report every entry in flight, in the file's
order, and check each one's worktree git log for progress that has not been
reported. Read only: a standup never adds or removes an entry.

Also run `bash company/run-gates.sh` if the last stamp in
`company/state/gates.status` is missing or stale - the standup states gate
truth, not gate memory.

Also tail `company/state/costs.log` if present (one line per stop, pipe
separated: `ts | session | kind | task | model | in=.. out=.. cache_r=..
cache_w=.. | est=$X.XX`). The task column can name several slugs joined with
`+` (truncated to three plus `+more`), so match by CONTAINMENT, not equality:
a line belongs to an entry when the task column CONTAINS that entry's `task`
slug (OQ-MST-05 assumption). Sum the `est=$` column two ways for the Spend
line: spend for TODAY (lines whose `ts` date matches today) and spend PER
ENTRY (for each entry, sum every line whose task column contains its slug).
Never split a shared line - it is attributed in full to every entry it names,
so whenever more than one entry was in flight the per-entry figures are
APPROXIMATE and the output must say so explicitly. If a line has no `est=$`
segment (no pricing configured), report token totals instead of dollars and
say estimates are unavailable. Costs are estimates only, not billing.

Then report, in this shape, tight and factual:

```
## Standup - <date>

**Done since last update:** ...
**In flight:** one line per entry: <task> - <agent/worktree> - <last known state>
**Gates:** <green/red + which> (stamped <when>, fresh/stale)
**Spend (est):** today $<X.XX> - per entry <slug> $<Y.YY>, ... (mark APPROXIMATE when more than one entry is in flight; tokens if no pricing)
**Blocked:** <what, on whom>
**Decisions needed (owner):** <numbered, each with what it blocks>
**Open CRs:** <n> (<newest slugs>)
**Top worries:** <up to 3 rows from WORRIES.md, verbatim>
**Recommended next:** <1-3 actions, in order>
```

Red stays red until proven green. Never average a status. If state files
contradict the git log, say so - that discrepancy is itself a finding.
