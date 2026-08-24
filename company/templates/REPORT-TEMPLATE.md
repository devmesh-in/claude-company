# REPORT: <task-slug>

_Agent: <role>. Brief: `company/briefs/brief-<slug>.md`. Date: YYYY-MM-DD._

Hard summary budget (FR-ASR-16): about 1-2k tokens. Facts, pasted ladder, FR checklist.
Bulky evidence (logs, screenshots beyond the four UI states, long diffs)
lives under `company/evidence/<slug>/` and is referenced here by path.
Do not paste transcripts.

Reports contain facts, not adjectives. "Robust" and "comprehensive" are not
facts. Never describe unverified work as working.

## What changed
- <path>: <one line>

## Gate results (paste the ladder, do not summarize)
```
<output of bash company/run-gates.sh>
```

## FR checklist
- FR-XX-01: implemented + tested (<test path>) | deferred because <reason>

## Witness candidates
1-3 load-bearing markers for what shipped - the spots that would break first if
this regressed. You propose; the CEO curates and records them (`W-NNN`) at
integration. Each: file + exact substring + why it is load-bearing.
- `<path>` : "<exact substring>" - <why breaking this means the change regressed>

## Ownership
`git diff --stat <base>..HEAD` summary. Confirm: no paths outside the brief's
"You own" list. If any, say so plainly.

## Evidence
UI: screenshots loaded / empty / error / after-action, paths or embeds.
Everything else: `company/evidence/<slug>/` referenced by path.

## CRs filed
- CR-<n>: <slug> - status

## Deviations from the brief
What and why. An empty section means "none", written explicitly.

## Worries for the CEO
Suspicions, near-misses, false-green risks - anything that belongs in
`company/state/WORRIES.md`.

## Acceptance
Acceptance: pending owner
(Delivery is not done until the owner's acceptance is recorded in
`company/state/DECISIONS.md`. Silence is not acceptance - see
`ORCHESTRATOR.md` step 8.)
