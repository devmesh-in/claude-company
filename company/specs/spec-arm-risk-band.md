# SPEC: arm the risk band - make DECISIONS #19's compensating control real

_Author: CEO (acting as product-manager; the owner's standing instruction this
session is that no subagents are dispatched). Date: 2026-08-22._
_Status: HALT - see the open BLOCKER (OQ-ARB-05). Not buildable to completion._
_Owner decision that produced it: 0.3.1 readiness, "arm the risk band first"._

## Part 1 - Product requirements

### Problem

DECISIONS #19 (b) adopted a risk-scaled audit with two halves:

> a risk-scaled audit derived from risk_score.py's EXISTING bands rather than a
> new line-count fence, and the same change ARMS a mandatory audit in the high
> band, which closes the worry about a large clean delegated build integrating
> with no independent read - this is the version that cuts ceremony at the
> bottom and ADDS rigor at the top, which is why it is the one I am taking.

Only the bottom half shipped. Verified on main at 84dd95c:

- `grep -n "risk\|band" .claude/hooks/guard_provenance.py` returns exactly one
  hit, a comment at `:459`. There is no band logic in the enforcement layer.
- `risk_score.py` has zero callers in any hook and appears nowhere in
  `.claude/settings.json`. It is a manual CLI.
- The only place the band is mentioned as mandatory is a runbook line for the
  CEO, `ORCHESTRATOR.md` step 6.

So the audit demand was narrowed (mode C exempts worktree commits via
`in_worktree_or_out_of_tree`, and returns on a clean tree via `if answered and
not dp: continue`) while the compensating rigor was never mechanized. The
worry the narrowing was accepted against - a large clean delegated build
integrating with no independent read - is open, not closed.

### Goal and success metrics

Make the high band arm a mandatory independent audit mechanically, at the point
where unread work actually reaches `main`.

Success: a high-band integration cannot complete without a fresh auditor pass
recorded in the provenance ledger, and a low or medium integration is
unaffected. Measured by: the acceptance criteria below all passing, and the
band gate firing at least once on a real integration within the next release
cycle (a gate that never fires is the mode E failure and must be reported as
such, not left silently inert).

### Users and personas

The CEO integrating a lane's work, and any install running PR-mode
integration. Not the builder: lanes are unaffected while they build.

### Functional requirements

- **FR-ARB-01.** A new module-level helper resolves the band for an integrand:
  `risk_band(tree, ref)` returning `(band, score, signals)`, where band is one
  of `"low" | "medium" | "high" | None`. `None` means "could not score" and is
  distinct from every band. A companion `integration_ref(seg, tree)` resolves
  WHAT is being integrated, and returns None when it cannot (see OQ-ARB-03).
- **FR-ARB-02.** The helper reuses `risk_score.py`'s existing scoring and band
  cuts. It MUST NOT re-implement, re-tune, or re-derive them. Band cuts stay
  25 / 50 exactly as recorded in that file's docstring.
- **FR-ARB-03.** The gate arms at INTEGRATION, not at commit. Rationale and the
  rejected alternative are in OQ-ARB-01.
- **FR-ARB-12.** The tree a segment acts on is resolved through
  `_common.acting_tree` and normalised to a checkout root. It MUST NOT be
  re-derived locally: `_common` states outright that a hook resolving its own
  tree is how the guard_secrets class of bug returns, and the first
  implementation of this gate proved the point by shipping an inverted copy.
- **FR-ARB-13.** Commands that CONCLUDE or CANCEL a merge (`--abort`,
  `--continue`, `--quit`, `--skip`, `gh --disable-auto`) and a tree with
  `.git/MERGE_HEAD` present are NOT integrations and must never arm. Blocking
  them strands an operator mid-conflict: resolving conflicts edits the tree,
  which stales the audit, after which neither continuing nor aborting is
  available. Mode C already carries the MERGE_HEAD exemption for this reason.
- **FR-ARB-14.** A fault inside this gate MUST NOT disarm mode C. Fail-open is
  the file's posture but it is PER GATE; a shared handler would turn a blocking
  compound command into an allow, violating BR-ARB-01.
- **FR-ARB-04.** The integration surface the gate recognizes MUST include
  `gh pr merge`, not only `git merge`. See FR-ARB-05 for why this is a
  requirement and not an implementation detail.
- **FR-ARB-05.** `_common.git_subcmd` returns `(None, [])` unless the segment's
  first token is literally `git`, so `gh pr merge` is invisible to every gate
  built on it today. A new recognizer is required; `git_subcmd` itself MUST NOT
  be widened, because `guard_commit`, `guard_secrets` and `guard_provenance`
  all consume it and changing its contract changes three gates at once.
- **FR-ARB-06.** On a high band with no fresh audit for the current work_hash,
  the integration BLOCKS with a message naming the score, the band, the
  integrand, the top contributing signals, and the exact remedy (one Task call,
  `subagent_type: auditor`). The signals are already computed at the block
  site; deferring the "why" to a second command makes the message a pointer
  rather than a recipe.
- **FR-ARB-07.** A fresh audit satisfies the gate. "Fresh" reuses the existing
  `fresh_audit(root, ledger)` / `staleness_reason` machinery in
  `guard_provenance`; no second definition of freshness is introduced.

  **What that actually means today, stated because the doctrine must not
  overclaim.** Measured 2026-08-22: of 14 AUDIT records in this repo's history, the only
  5 carrying a real verdict are the OLD substring parser's false positives
  (all `do-not-ship`, all July). Since that parser was corrected EVERY record
  reads `verdict: unknown`, and none is written when an auditor COMPLETES -
  PostToolUse Task fires at agent LAUNCH for a background agent, so the parsed
  text is the launch acknowledgement. `fresh_audit` accepts anything that is
  not literally "do-not-ship", so what this gate enforces is **an auditor was
  dispatched over this exact tree and the tree has not changed since**, NOT
  "an audit passed". That is weaker than the phrase "mandatory audit" suggests
  and it is inherited, not introduced here (mode C has behaved this way since
  the ledger existed). Recorded as a P0 in WORRIES.md and owed its own spec:
  the naive fix - refusing to record an unknown verdict - would mean no
  background audit is ever recorded and both gates deadlock, which is the mode
  D failure. Nothing in this feature's prose may describe the gate as verifying
  a verdict until that P0 is closed.
- **FR-ARB-08.** Low and medium bands allow silently. No output, no log line,
  no behavior change whatsoever.
- **FR-ARB-09.** A hotfix entry bypasses, logging BYPASS, consistent with every
  other gate in the file (RISK-MST-01 posture).
- **FR-ARB-10.** The gate fails OPEN on any internal error, matching the file's
  standing posture. A band of `None` (FR-ARB-01) allows and logs one INFO line
  saying the tree could not be scored. It MUST NOT fail closed: `risk_score.py`
  is documented as always exiting 0 and failing open per signal, so a closed
  failure here would invent a block the scorer cannot justify.
- **FR-ARB-11.** Every arm, bypass and INFO writes one `adherence.log` line, so
  the gate's fire rate is measurable against the mode E precedent.

### Business rules and validations

- **BR-ARB-01.** Monotonicity: this change converts ALLOWs into BLOCKs only. No
  path that blocks today may start allowing. This is the safe direction and is
  the reason no spec-lite rung applies.
- **BR-ARB-02.** The arithmetic is frozen. Signal points and band cuts are the
  calibration `risk_score.py` was accepted with; this spec consumes them and
  changes none of them. Any wish to re-tune is a separate spec.
- **BR-ARB-03.** No new magic numbers. The arming threshold IS the existing
  `high` band, not a new fence.

### Scope

IN: the band helper, the integration recognizer, the gate, its tests, and the
doctrine lines that describe it.

OUT: re-tuning risk_score; widening `git_subcmd`; arming at commit time;
scoring calibration for non-git forges other than `gh`; fixing the pre-existing
blindness of `guard_commit`'s own merge gate to `gh pr merge` (recorded as a
new worry by this spec, owed its own change - see Risks).

## Part 2 - Build readiness

### Calibration evidence (why `high` is the right arming point)

Measured on main 2026-08-22, `python3 .claude/hooks/risk_score.py --base <sha>^`
over the seven most recent merges. Note this measures the MERGED CONTENT of
each commit, which is the integrand - so it describes what OQ-ARB-03 as
re-decided actually computes. Against the original commit-time subject it
described nothing the code did, and RISK-ARB-01's bound was unmeasured:

| commit | score | band | change |
|---|---|---|---|
| `137db3a` | 189 | high | secrets scanner P0 |
| `7d59375` | 133 | high | stop_gate deletion |
| `2f67856` | 93 | high | risk-scale |
| `7e1ff55` | 73 | high | salvage-provenance |
| `b5e9903` | 38 | medium | delegation doctrine |
| `d42d8d5` | 38 | medium | 1-line version bump |
| `84dd95c` | 0 | low | CR paperwork |

Four of seven arm. This directly answers the failure mode that killed mode E
(never fired once in five weeks) and the calibration datum recorded on the P0
worry (a +2426/-186 enforcement-hook diff scoring 25 = medium, below its own
threshold). That datum predates #122 / PR #124, which made `sensitive_paths`
scale with blast radius; post-#124 the same class of change scores 73 to 189.

The datum also shows the opposite risk is real but tolerable: a one-line
version bump scores 38 (medium), which does not arm. Nothing in the sample
arms that should not.

### Open questions, all with decided fallbacks

- **OQ-ARB-01: where does the band arm - commit or integration?**
  **DECIDED: integration.** DECISIONS #19 phrases the worry as a build
  "integrating with no independent read", and integration is where an unread
  diff reaches `main`. Commit-time arming was rejected on evidence: it is the
  shape of mode D, which "never fired and can deadlock" (RESUME.md), because a
  worktree lane commits continuously while building and would block mid-build
  waiting on an auditor that cannot usefully read unfinished work. Owner may
  veto toward commit-time; the FRs localize the choice to one call site.
- **OQ-ARB-02: what counts as integration?** **DECIDED: a `gh pr merge`
  segment, or a `git merge` segment.** Both, because this repo and the standing
  install guidance both use PR-mode integration, so `git merge` alone would
  ship a gate that never fires here - mode E again, by a different route.
- **OQ-ARB-03: what subject does the band score?** **RE-DECIDED 2026-08-22
  after an audit HALT: the INTEGRAND.** The first answer was "the default
  no-`--base` run", i.e. the tree as it stands, and it was wrong. That is the
  right subject for a COMMIT-time question; FR-ARB-03 had already moved the
  arming point to integration and the subject did not move with it. The
  consequence, reproduced: a CEO integrating a lane from a clean `main`
  checkout scores `merge-base(main, HEAD) == HEAD`, an empty diff, band `low`,
  and the gate is silent - on exactly the large clean delegated build this
  whole feature exists to catch. Scored from the lane branch the same change
  is `high` (94). The gate fired only on main-checkout self-authored work,
  which mode C already gates, and missed everything mode C exempts.

  The subject is now: for `git merge <ref>`, `merge-base(main, ref)...ref`;
  for `gh pr merge` with no PR argument, HEAD, which IS that command's
  integrand. Two declared limitations, both logged rather than silent:
  `gh pr merge <n>` resolves only via a local `refs/pull/<n>/head` and is
  otherwise UNSCORABLE and allowed (no hook here reaches the network); and the
  secrets signal is scored only when the integrand is HEAD, because
  `guard_secrets --scan-branch` is HEAD-relative. The secrets caveat can only
  lower a band, never raise one, so it cannot manufacture a block.
- **OQ-ARB-04: does a medium band deserve a nudge?** **DECIDED: no.** FR-ARB-08
  keeps medium completely silent. A nudge on 2 of 7 merges is noise, and the
  delegation-doctrine work merged this session was specifically about not
  adding one-directional pressure.

### Risks

- **RISK-ARB-01.** The gate could over-fire and make integration painful. Bounded
  by the calibration table and by FR-ARB-11, which makes the fire rate
  measurable rather than anecdotal. If it over-fires, the answer is a spec to
  re-tune, never a local threshold tweak (BR-ARB-02).
- **RISK-ARB-02, recorded and OUT of scope.** `guard_commit`'s existing merge
  gate is built on `git_subcmd` and is therefore already blind to `gh pr merge`.
  Every install told to use PR-mode integration has been merging without that
  gate firing. This spec does not fix it; it records it, and FR-ARB-04/05 make
  sure the NEW gate does not inherit the blindness. Owed its own worry row and
  its own change.

### BLOCKER, open: freshness is keyed to the wrong subject (OQ-ARB-05)

**Status: HALT. This spec is NOT buildable to completion until the owner
decides it.** Found by the second independent audit, 2026-08-22.

OQ-ARB-03 moved the RISK subject to the integrand. The EVIDENCE subject did not
move with it. FR-ARB-07 mandates reusing `fresh_audit(root, ledger)`, which
keys on `c.work_hash(root)` - the content of the integrating checkout - and
`mode_b_post` records audits under that same hash. `ref` never enters the
freshness question. That is structurally the identical error FR-ARB-03 fixed,
one function later.

Reproduced, two lanes, CEO on a clean `main`:

```
band(task/lane-b) = high (84)      # never read by any auditor
auditor dispatched over lane A only
git merge --no-ff task/lane-b   ->  exit 0
adherence.log: INFO | integration | high band score=84 satisfied by fresh audit
```

An unaudited 84-point lane integrates, and the log records it as audited. The
inverse also reproduces: with both lanes genuinely audited, merging lane A
changes `main`'s content and stales lane B's audit, so the CEO must re-audit
every remaining lane after each merge - and the block message gives the wrong
reason ("the tree changed after the last audit"; the integrand did not change).

**Why this cannot be patched here.** Any fix needs freshness keyed to what is
being integrated. That collides head-on with the P0 in WORRIES.md: audits are
recorded at agent LAUNCH, carrying the local checkout's hash and a verdict of
"unknown", because PostToolUse Task never fires with an auditor's report. There
is no point in the current substrate where the integrand's identity and an
auditor's actual verdict are both available. Keying freshness to the integrand
without fixing the recording path would make the gate demand an audit that can
never be recorded - a permanent deadlock, which is the mode D failure.

- **OQ-ARB-05: what evidence satisfies a high-band integration?** NOT DECIDED.
  Three candidates, none costed: (a) record audits against the integrand tip
  sha alongside `work_hash`, which requires the auditor's dispatch to know what
  it is auditing; (b) require the audit to have been taken while the checkout
  contained the integrand, which makes the gate demand a checkout-then-audit
  workflow and turns the `git merge` from `main` case into a permanent block;
  (c) fix the audit-recording path first (a `--record-audit` CLI, or Stop-time
  reconciliation) and key freshness on the integrand afterwards. (c) is the
  only one that also closes the P0, and it is a separate spec.

Until this is decided, mode F enforces "an auditor was dispatched over SOME
tree recently, and this checkout has not changed since", which is materially
weaker than what DECISIONS #19 asked for. No prose anywhere may describe it as
closing the delegated-build worry.

## Spec-ready checklist

- [x] Problem stated with verified evidence, file and line cited
- [x] Every FR has an ID and is independently checkable
- [x] Every open question has a decided fallback
- [x] Scope has an explicit OUT list
- [x] Risks named, with the out-of-scope one recorded rather than silently left
- [x] Calibration is measured, not asserted
- [x] No new magic numbers introduced (BR-ARB-03)

## Part 3 - Brief handoff

One seam: `guard_provenance.py` plus its tests, with a small recognizer added
next to the existing parsers. Per the delegation doctrine merged at b5e9903,
one seam is one builder - no tech-lead layer, no crew. Brief:
`company/briefs/brief-arm-risk-band.md`.
