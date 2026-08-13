# Harness port - the complete change checklist

_Every change identified in the DevMesh fork review, ported or not, with its
status and the reason. Maintained by the CEO. Source catalog:
`DevMesh/company/harness-changes-2026-08-12.md` (14 items). The fork diff found
more than the catalog lists, so sections B and C exist._

_Last updated: 2026-08-13. Program: harness-port. Target release: 0.2.7._

## Status vocabulary

| Status | Meaning |
|---|---|
| ASSIGNED | In a dispatched workstream, not yet landed |
| DONE | Merged into main and verified |
| DEFERRED | Real, but waiting on an owner decision |
| GAP | Identified, agreed worth doing, not yet in any lane |
| REJECTED | Decided not to port, with a recorded reason |
| N/A | DevMesh-specific, does not apply upstream |

## Workstreams

| Lane | Issue | Wave | Owns | State |
|---|---|---|---|---|
| L1 kernel | #98 | 1 | `_common.py` | PR #107 open, CI running. All five suites green post-rebase (hooks 569). Carries the kernel AND the P0 fix: `rel_path` was blind inside worktrees, so `guard_frozen` was inert for every path under a worktree. CEO re-verified the control in both directions and the suite count exactly. Risk band medium. ADR-0002 accepted via CR-HP-1. |
| L2 guards | #99 | 1 | `guard_commit`, `guard_secrets`, `guard_spec` (is_source), `guard_provenance` (verdict) | **MERGED** as PR #104 (033730f). All five suites green, CI 9/9. CEO re-ran the hook suite independently: 468, matching the claim exactly. All four defects proven with before/after probes against pristine source rather than asserted. Worktree removed, branch deleted. |
| L3 runner | #97 | 1 | `run-gates.sh`, `gate_stamp.py`, wiring gate, `.gitignore`, `frozen-surfaces.json` | **MERGED** as PR #103 (ef30e52) after one rebuild. CI 9/9, installer suite 83/13 to 96/0, CEO re-verified it independently. Also repaired CR-UPD-1 and added `FrozenBaselineAgreement`, which asserts the registry and the hardcoded baseline agree in both directions - that turns a whole class of half-landed freeze into a red gate. Worktree removed, branch deleted. HISTORY, kept because the lesson is the point: PR #103 open, **CI RED, sent back**. Hooks 430 and npm 62 green (CEO re-ran both), but `tests/install/run_tests.sh` fails 13 of 96 on all three Linux runners. FR-HP-28 regressed it: the fixture invokes the runner with CLAUDE_PROJECT_DIR set to a non-git fixture dir WITHOUT cd-ing there, so resolving from the cwd's git toplevel returns the repo and the runner gates the wrong tree - the same class of bug the FR exists to fix, in the opposite direction. Everything else in the lane verified good, incl. the wiring gate hand-exercised by the CEO. CR-2 APPROVED. |

CEO verification so far: risk band MEDIUM on L3 (25 points - size plus three
sensitive hook paths), so extra spot-reads rather than a mandatory auditor.
Ownership diffs confirmed clean on both lanes against their briefs. I ran the
wiring gate myself rather than trusting the report: shipped tree exits 0, and a
fixture with `stop_gate.py` removed from the Stop group exits 1 printing
`Stop (no matcher) does not run stop_gate.py` plus the update fixit. That is the
mechanical answer to the rationale drift that started this whole review - had
this gate existed in the fork, un-wiring stop_gate would have turned a gate red
instead of silently invalidating a written safety argument.
| L4 state-writers | #100 | 2 | `witness_check.py`, `cost_capture.py`, `guard_spec` (torn read) | blocked on L1 |
| L5 provenance-scope | #101 | 2 | `guard_provenance.py` | blocked on L1, auditor mandatory |
| L6 stop_gate + doctrine | #102 | **1 (moved)** | `stop_gate.py`, doctrine files, agent defs, `ci.yml` | REPORTED, revising. All five suites green (hooks 423). stop_gate scoped, full doctrine sync, canon CI job built and demonstrated BOTH red and green. Two CRs, both decided: CR-HPD-1 approved and unblocked by PR #106; CR-HPD-2 UPHELD - the quick-needs-no-brief doctrine comes OUT and the guard_spec code goes to L4, because I reproduced the hazard (a briefless quick entry blocks source edits for a sibling lane whose brief is fine, so a CEO following my doctrine would brick its own checkout). Also approved its worktree-attribution composition, which closes the hole its own fallback left. HISTORY: BUILDING. Moved out of wave 2 on 2026-08-13: its file set is verified disjoint from all four running lanes, so it never had a dependency. The wave-2 barrier applies only to L4 and L5, which share `guard_spec.py` and `guard_provenance.py` with L2. Holding L6 behind that barrier was a CEO scheduling error and cost it several hours of idle time - the exact anti-pattern the parallel-discipline doctrine this very lane is writing exists to prevent. Carries two items newer than the spec (spec-lite rung, canon-vs-CI check) per DECISIONS #19. |

---

## Section A - the 14 catalogued changes

| # | Change | Status | Where / why |
|---|---|---|---|
| 1 | Content-based `work_hash` (tree the working copy would commit as) | ASSIGNED | L1. Closes the WORRIES row "staging stales a provenance audit". |
| 1b | `HASH_EXCLUDES` also excluding `*.md` and `*.txt` | REJECTED | Catalog tags this generic and it is wrong for us. Markdown IS the product here (agent definitions, skills, doctrine) and `no_slop`, `trace_check` and `guard_models` all gate it. Excluding it would let a doctrine rewrite stale nothing. |
| 2 | Gate the merge, not the commit | DEFERRED | Amends METHOD mechanism 4. Most of the supporting evidence was staleness loops that item 1 deletes on its own, so re-measure after L1 lands. Must land paired with the stop_gate decision and with DevMesh's later correction that a waiver must itself require a green fresh stamp. |
| 3 | Repo-scoped gate runs with cached skips (`repo` field) | REJECTED | Single-repo upstream, so the field is inert. `company/specs/spec-repo-scoped-enforcement.md` is already parked with evidence refuting the premise. Their `stamp_is_green` also returns green UNCONDITIONALLY when the tree_hashes map is empty, which is every non-polyrepo project - a false-green generator. |
| 3b | Cheap-to-expensive gate ordering | N/A | Already ours. `company/GATES.md` states it; it is config authoring, not code. |
| 4 | Low-band waiver at 20 changed source lines | REJECTED | DECISIONS #5 vetoed exactly this shape - a numeric fence. A scored model with numbers inside is fine, a bare line cap as a gate is not. See parked decision 2 for the principled version. |
| 4b | Waiver SCOPE fix (dirty paths INTERSECTED WITH ledger self_authored) | ASSIGNED | L5. Independently excellent and separable from the waiver. It is the exact fix our own parked spec named as "the cheaper and more principled fix". Closes the P1 row "provenance dirty check is umbrella-scoped". |
| 4c | `quick` entries need no brief | DEFERRED | Grouped with parked decision 3 - both are "ceremony scales with the task" loosenings, and they should be decided together rather than one riding in quietly. |
| 5 | Gates and auditor started together; ONE delta-scoped re-audit; auditor verifies the stamp instead of re-running the ladder | ASSIGNED | L6. Mechanism 5 intact - the auditor still reads independently. Depends on L1, or "verify the stamp" means verifying a history digest. |
| 6 | The ladder runs once, at integration | ASSIGNED | Split in two. The BUG is L3: `run-gates.sh` prefers `CLAUDE_PROJECT_DIR`, which the harness pins to the main checkout, so a worktree agent gates and stamps the wrong tree and gets a green stamp for code it did not build. Barely bites this repo because CLAUDE.md already tells agents to run the two suites directly, but it bites every wired INSTALL. Decided without escalation: it is a straight false-green fix and strictly more correct. The DOCTRINE half (agent defs, brief DoD) is L6. The larger question of splitting the ladder into worktree-meaningful versus integration-only gates stays parked as decision 5. |
| 7 | Multi-session concurrency layer (state_lock, atomic writers, torn-read fail-open) | ASSIGNED | L1 (kernel), L4 (witness registry, cost cursor, guard_spec fail-open), L5 (ledger locking, unattributed dispatch). Highest priority: we shipped multi-session-tasks in v0.2.6 with no lock under it. |
| 7b | Repair procedure for lost dispatch credits (re-credit under the lock, adherence REPAIR line, never hand-edit the ledger) | ASSIGNED | L6. A hand edit resets the checksum and wipes the audit history, which is why the procedure has to be written down. |
| 7c | Standing advisory: one INTEGRATING session per repo at a time | ASSIGNED | L6. Concurrent building sessions are fine and are what the lock layer is for; concurrent merges are not, and git's index.lock makes that collision loud rather than silent. |
| 8 | Model routing: qa-engineer, docs-librarian, and the builtins to sonnet | REJECTED | DECISIONS #1, vetoed 2026-07-09, stands. Not reopened. |
| 8b | `pricing.sonnet` data block | N/A | Only useful if a role runs sonnet. Under the all-opus veto it is dead data. |
| 9 | Phase 0 spec-lite rung | DEFERRED | Amends METHOD mechanism 1. Conditions are objective and the escape is one-way, which is the principled shape, but it is canon and therefore yours. |
| 10 | Parallel discipline (wave in one message, per-lane integration, CRs interrupt-priority) | ASSIGNED | L6. Prose plus telemetry, no enforcement change. |
| 11 | Right-sized paperwork (state caps with verbatim archive, QA per CHANGED screen, batched docs-librarian, test-quality DoD) | ASSIGNED | L6. Includes editing `docs-librarian.md` itself, which DevMesh forgot - their agent definition still contradicts their own batching doctrine. |
| 12 | Observability - see the four rows below | ASSIGNED | Split across L1, L2, L3. |
| 12a | `gates.log`: one line per ladder run, runner-written, on the frozen always-list AND gitignored | ASSIGNED | L3. DevMesh did the frozen list and forgot the gitignore. |
| 12b | Quiet-pass runner: passing gate prints its tail plus a pointer; failing gate echoes everything | ASSIGNED | L3. Verified our runner currently `cat`s every gate's full output and then deletes the file, so preserving it is part of the change. DevMesh measured a green ladder going from ~2,600 transcript lines to ~30. |
| 12c | Slow-hash breadcrumb (work_hash over 1.5s logs a timing line) | ASSIGNED | L1. |
| 12d | Block-message ergonomics: warn that a compound `switch && commit` is judged against the CURRENT branch | ASSIGNED | L2. Was missing from the first dispatch, added by addendum. |
| 13 | pytest-xdist with per-worker databases, smoke tier | N/A | Their stack. Our suite is 393 python tests at ~102s plus npm; parallelising it is a separate question, not this port. |
| 14 | Regression suite | ASSIGNED (distributed) | Adapted rather than copied. DevMesh has one 393-line flat script at `.claude/hooks/tests/`, which `install.sh` would copy into every user project. Ours goes to `tests/hooks/` as unittest so it joins the existing 393-test discover run, and each lane lands with its own cases rather than one lane landing a monolith. |

---

## Section B - found by diffing the fork, absent from its catalog

These are the highest-value rows. Nothing here was in the change doc.

| Change | Status | Where / why |
|---|---|---|
| Labeled audit-verdict parser plus `response_text` content-block flattening | ASSIGNED | L2. Closes our P1 row "provenance audit verdict parser is substring-naive", which has already cost four blocked commits against passing audits. |
| `git_subcmd` must consume separated-argument globals | ASSIGNED | L2. Reproduced: `git -C sub commit` parses its subcommand as `sub`, so the commit gate never arms, and `git -C sub push origin main` evades the protected-branch check by the same parse. Worse than the P3 row that recorded it. |
| `guard_secrets` delegates to `guard_commit.git_subcmd` instead of duplicating it | ASSIGNED | L2. Same escape currently bypasses the secrets scan; dedup means the two cannot diverge. |
| `is_source` exempt-dir test anchored to the FIRST path segment | ASSIGNED | L2. Reproduced: `app/company/billing.py`, `src/docs/handler.py` and `pkg/.claude/x.py` all return False today, so they need no brief, no execution decision, and never count as dirty source for the audit demand. |
| Mode D block reason names the offending self-authored dirty paths | ASSIGNED | L2. |
| `delegated_with_dispatches` - entry-shape route to the delegation exemption | ASSIGNED | L5. I initially rejected this as a self-reported waiver of mechanism 5 and was wrong on both counts: the declaration is necessary but not sufficient, and the two conditions that do the work (a credited dispatch, zero overlap with self_authored) are both hook-recorded. Must land with the accepted hole tested: source written via Bash is never recorded self-authored, so it stops arming the requirement. |
| DevMesh un-wired `stop_gate` from the Stop hook | REJECTED for us | See DECISIONS #18 and section C. Their doctrine still cited stop_gate as a live integrity point while it was unwired - the drift that motivated our new wiring gate. |
| DevMesh deleted the Workflow-tool prohibition from ORCHESTRATOR | REJECTED | Undocumented, and `models.json` and `METHOD.md` still cite the rule. The premise (internal `agent()` spawns fire no PreToolUse events, so `guard_models` cannot pin them) is empirically checkable and nobody has checked it. Sent back to DevMesh as a finding. |
| DevMesh reverted ORCHESTRATOR to single-task wording | REJECTED | Contradicts the concurrency layer shipped in the same session. Sent back as a finding. |
| `tree_hashes` stamp keying | REJECTED | CORRECTION 2026-08-13: I claimed it was written OUTSIDE the stamp checksum and that was wrong - the reference computes the checksum after adding the field. The refusal stands on its own evidence instead: their `check_stamp` returns green UNCONDITIONALLY when `tree_hashes` is a present-but-empty dict, which is every non-polyrepo project, and it never reaches the `work_hash` comparison. Recorded because a rejection resting on a false reason is worth exactly nothing. |
| `guard_invariants.py` | REJECTED | Re-implements an em-dash rule `no_slop` already enforces, plus stack-specific Alembic rules, and it is wired only in a local settings file where nobody reading `settings.json` would see it. |
| `contract_parity.py`, `devmesh-*` agents, `.{repo}-wt` mounts, per-repo `fresh_audit`, `seg_git_dir`, `commit_repo_root` | N/A | Polyrepo-specific. |

---

## Section C - originated here, not from DevMesh

| Change | Status | Why |
|---|---|---|
| Mechanical hook-wiring assertion | ASSIGNED (L3) | DevMesh un-wired a hook while its doctrine still cited that hook as a live integrity point, and no test caught it because the code never changed. `guard_models --check` already asserts the spawn hook is wired so enforcement cannot ship without teeth; this extends that idea to the full expected wiring. It is the mechanical answer to rationale drift. |
| `stop_gate` multi-session scoping | ASSIGNED (L6) | New P1, reproduced 2026-08-13. Decided by the owner as DECISIONS #18: scope it, do not unwire. |

---

## Section D - parked owner decisions

Owner unparked these on 2026-08-13 (DECISIONS #19: "cut unnecessary ceremony as
much as possible... quality is great already"). Three adopted, one deliberately
held.

| # | Decision | Status | Where |
|---|---|---|---|
| 1 | Move the green-stamp requirement from commit to merge | **STILL PARKED, deliberately** | The instruction to cut ceremony does not change the arithmetic. Most of its supporting evidence was staleness that content hashing deletes on its own, so this gets decided at wave-1 integration against a real block count, not on appetite. Holding it is the honest reading of "balance efficiency with quality". |
| 2 | A risk-scaled audit band | **ADOPTED** | Derived from `risk_score.py`'s EXISTING bands, never a new line-count fence, and the same change ARMS a mandatory audit in the high band. This is the version worth having: it cuts ceremony at the bottom and ADDS rigor at the top, closing the worry about a large clean delegated build integrating with no independent read. Wave 2. |
| 3 | Phase 0 spec-lite rung, plus 4c (quick needs no brief) | **ADOPTED** | Objective conditions, one-way escape upward, hooks force the upgrade. Wave 2, L6. |
| 4 | Model tiering | REJECTED | Standing veto, DECISIONS #1. Unchanged. |
| 5 | Splitting the ladder into worktree-meaningful gates versus integration-only gates (witnesses, trace, models) | Worth doing, but it is a doctrine change about WHERE proof happens, not a bug. The underlying false-green bug is already assigned to L3 without escalation. | You say so. |
| 6 | ~~Whether `company/briefs/**` and `company/specs/**` should join `company/state` in HASH_EXCLUDES~~ **ADOPTED 2026-08-13, sent to L1 mid-build**. Inputs are excluded; shipped behavior (doctrine, agent definitions, skills) stays hashed. Original note kept below for the reasoning. | Raised 2026-08-13 after the CEO's own paperwork staled the stamp and cost a 459s ladder. The fork's answer (exclude ALL markdown) is still wrong here because doctrine and agent definitions are executable product. But briefs and specs are build INPUTS, not shipped behavior, and a brief edit invalidating a code gate result is hard to defend. A more precise cut than either extreme. NOT sent to L1 mid-flight - FR-HP-06 is explicit and changing a sealed brief mid-build is a CR-shaped action for a mere optimization. | Decide at wave-1 integration, when L1's implementation makes it a one-line change. |

---

## Scoreboard

| | Count |
|---|---|
| DONE (merged and verified) | 0 |
| ASSIGNED (in a dispatched lane) | 22 |
| DEFERRED (owner decision) | 4 |
| GAP (agreed, unassigned) | 0 |
| REJECTED (with reason) | 11 |
| N/A (DevMesh-specific or already ours) | 5 |

Nothing from the review is unaccounted for. The four DEFERRED rows are the only
open questions, and none of them blocks wave 1.

## Retrospective - what made this slow, and the mechanical fixes

_Owner asked mid-program why it was taking so long. These are causes, not
excuses, ordered by cost. Each one has a mechanical fix, because a lesson that
lives only in a retro is a lesson that gets relearned._

| # | Cause | Cost | Fix, and it must be mechanical |
|---|---|---|---|
| 1 | **A barrier nobody verified.** The CEO held L6 behind a wave-2 barrier taken from the spec's wave plan as fact. Its file set was fully disjoint from every running lane; it never had a dependency | ~2 hours of idle lane | Before accepting ANY wave barrier, compute it: intersect the owned-file lists of the two briefs. Empty intersection means no barrier. This is a five-line check and it should run at dispatch, not live in the CEO's head. The wave plan PROPOSES barriers; the ownership diff DECIDES them |
| 2 | **Findings absorbed into running lanes instead of triaged.** "Fix whatever findings you get" was taken as a standing instruction to grow scope in flight. Four new gates, a P0, four flaky tests and a half-landed release repair all joined a program already in motion | Roughly doubled the program | A finding discovered mid-program defaults to the BACKLOG, not to the current lane. It joins the running work only if it BLOCKS the running work. Batch the rest into one owner decision - "6 found, 2 block, 4 are next" - which is the interruption discipline METHOD already requires and which the CEO did not apply to itself |
| 3 | **A known defect was paid instead of fixed.** stop_gate's cross-session block was logged with a measured price after the FIRST incident, then paid five more times while its fix sat in a not-yet-dispatched lane | 6 ladder runs, ~30 min, plus the turns around them | When a logged defect has interrupted the CURRENT work twice, it is promoted to the front of the queue. The instrument for noticing already exists as of this program - `gates.log` records every ladder run and why. Nothing consumes it yet, which is its own row below |
| 4 | **Verification that duplicated CI.** Full local suite re-runs of what a six-platform CI matrix already ran | ~10 min per lane | Split the labor explicitly: CI proves it passes everywhere, the CEO proves the CLAIMS - controls, blast radius, spot-reads, and the specific assertion a lane says is load-bearing. The installer-suite-on-main run earned its place because it was a CONTROL, a different question. The rest were re-runs |
| 5 | **Integration deferred into a backlog.** Witnesses, checkout sync, the ADR index and the paperwork commit were deferred repeatedly on sound individual reasoning, and became a lump | One extra pass | Deferring is legitimate ONLY when the thing it waits on is already merged or imminent. Otherwise integrate per lane, which is the doctrine this very program wrote |
| 6 | **Doctrine ordered ahead of the code it describes** (quick-needs-no-brief) | One CR, one lane holding a clause | Already fixed mechanically by L6's `CeremonyDoctrineMatchesTheGuard`, which fails the moment the guard and the prose disagree |

**The honest meta-cause.** Every individual decision above was defensible in
isolation - verify more, fix what you find, do not skip the check. The aggregate
was slow because nothing was optimizing for DONE. The company has strong
machinery for "is this correct" and almost none for "is this finished", and a
CEO with an open-ended instruction will keep finding correct things to do. The
fix is not to care less about correctness; it is that scope changes should
require the same explicit, batched owner decision that every other escalation
does. A program that doubles in flight without one decision point is a process
defect, not diligence.

## A weakness the port closed that nobody knew about

Found 2026-08-13 while investigating why a commit passed the gate when the
stamp should have been stale. It was not a malfunction.

The LEGACY `work_hash` fingerprinted `HEAD` plus `git status --porcelain` plus
the diffs. For an UNTRACKED file, `status --porcelain` prints `?? path` no
matter what the file contains, and `git diff` covers only tracked files. So the
old hash could see an untracked file APPEAR, and was blind to every subsequent
edit to its CONTENT. A brand-new source file could be rewritten freely after a
green stamp without staling it.

Verified both directions in a throwaway repo: the content-based hash now on
main returns a different value after an untracked file's content changes; the
legacy digest does not. So FR-HP-05 closed a real enforcement gap on top of the
staleness-churn problem it was built for, and neither the DevMesh catalog nor
this program's spec knew that. Worth remembering as evidence for the general
shape of this port: several changes justified on ergonomics turned out to be
correctness fixes once someone looked.

## Measured baselines, taken 2026-08-13 before any change

Recorded so the close-out compares against numbers rather than impressions.

| Measure | Before |
|---|---|
| Full ladder, all green | 459s, 453s, 371s, 287s - FOUR runs in one session, 1570s total (26 minutes), every one triggered by paperwork |
| Installer suite (`tests/install/run_tests.sh`) | 96 tests, green on main - the control that proved L3's 13 failures were its own |
| Update suite (`tests/install/test_update.sh`) | 139 tests, green on main. Slow: it outlasted a 600s foreground budget when run concurrently with a ladder, so measure it alone before quoting a number |
| Hook suite alone | 393 tests |
| npm suite alone | 62 tests, 0 failures |
| Green-ladder transcript | full output of every gate echoed, then deleted |
| `gates.log` | does not exist - there is no record of where ladder time goes |

All three ladder runs were triggered by the stop_gate defect firing on PAPERWORK.
The third one was diagnosed precisely before paying it: the only gate-relevant
change since the previous green stamp was ONE new brief file, and no brief can
affect any gate outcome. That is 21 minutes spent proving something that had
already been proven, and it is the concrete case for the HASH_EXCLUDES change
now in flight with L1.

There is a SECOND loop underneath it, and it decided a parked question. I did
not commit this session's paperwork, because committing moves HEAD, which under
today's history-based `work_hash` stales the stamp again and would have cost a
FOURTH ladder run. Content-based hashing dissolves that on its own: committing
identical content does not move a content hash. So the commit-stales-the-stamp
pain is fixed by L1 alone, WITHOUT merge-only gating - which is exactly why
parked decision 1 stays parked. The evidence arrived while paying the tax.

Note on what the ladder cost buys: that first 459s run was triggered by the Stop hook
firing on three task entries whose code lives entirely in other worktrees, on a
main checkout containing only paperwork. The runtime is the honest price of the
suite; the fact that it was demanded at all is the stop_gate defect (WORRIES,
P1, assigned to L6). Do not conflate the two at close-out - the observability
work makes the cost VISIBLE, the scoping fix stops it being spent needlessly,
and neither one makes the suite itself faster.
