# BRIEF: hp-runner

_Type: program-workstream (L3 of the harness-port program).
Spec: `company/specs/spec-harness-port.md` - read ONLY the FR-HP-20 through
FR-HP-28 blocks and the OQ rows named below. The rest of the spec is not yours.
Lead: tech-lead. Date: 2026-08-13. Tracking issue: #97._

> Schema, contracts, kernel, shared UI, and anything in
> `company/frozen-surfaces.json` are FROZEN - consume them exactly as shipped;
> any change goes through `company/change-requests/`, never a local edit.

## Mission

The gate runner is loud, forgetful, and in a worktree it gates the wrong tree.
It echoes every gate's full output whether or not anything is wrong, which
bloats the transcript and then multiplies through every later turn's cache
reads; it keeps no record of where the time went; it deletes each gate's output
the moment it has printed it; and it resolves the project root from
`CLAUDE_PROJECT_DIR`, which the harness pins to the MAIN checkout, so a lead
running the ladder from a worktree gates and stamps somebody else's tree and
receives a green stamp for code it did not build. Success: a green ladder is
quiet and leaves a durable record, a red one still shows you everything, and the
ladder always gates the tree you are actually standing in.

You also build one thing that did not come from the fork: a mechanical assertion
that the hooks are actually WIRED. The fork un-wired a hook while its own
doctrine still cited that hook as a live integrity point, and nothing caught it
because no code had changed. `guard_models --check` already asserts the spawn
hook is wired so enforcement cannot ship as code without teeth; you generalize
that to the full expected wiring.

The hard constraint: **the runner's exit code and the ladder table are the
contract.** Everything downstream (the stamp, `guard_commit`, `stop_gate`, CI)
keys on them. You are changing what the runner PRINTS and WHERE it writes, never
what it decides.

## Read first (in order)

1. `CLAUDE.md` (project canon - the dual-nature rule; `company/gates.config`
   keeps `CONFIGURE ME` placeholders on purpose and you must not commit this
   repo's real gate commands into it)
2. `company/GATES.md` (the gate ladder contract you are implementing against -
   note that documenting your changes belongs to L6, not you)
3. `company/run-gates.sh` (whole file - the config parser, the run loop, the
   ladder table, the stamp step)
4. `.claude/hooks/gate_stamp.py` and `.claude/hooks/guard_models.py` (whole
   files - you own both)
5. `.claude/hooks/guard_frozen.py` - specifically `ALWAYS_DEFAULTS`, and note
   the VERIFIED fact that `install.sh` uses `copy_if_absent` and `update.sh`
   restores `frozen-surfaces.json` only when absent, so the JSON `always` list
   reaches FRESH installs only. A freeze that exists only in the JSON does not
   protect a single existing user.
6. `company/specs/spec-harness-port.md`, FR-HP-20 through FR-HP-28 only, plus
   OQ-HP-02, OQ-HP-04, OQ-HP-06 and OQ-HP-14.
7. `/Users/redomic/Documents/Projects/DevMesh/company/run-gates.sh` - the
   working reference for quiet-pass and `gates.log`. It ALSO contains
   repo-scoped cached gate skips and a `tree_hashes` stamp branch that you must
   NOT port (see Out of scope).

## You own

- `company/run-gates.sh`
- `.claude/hooks/gate_stamp.py`
- `.claude/hooks/guard_models.py`
- `.claude/hooks/guard_frozen.py` - `ALWAYS_DEFAULTS` only
- `company/frozen-surfaces.json`
- `.gitignore`
- `company/change-requests/CR-2-*.md` (new, yours to file)
- `tests/hooks/test_gate_runner.py` (new file, yours to create)

Nothing else. In particular you change NO doctrine file - `company/GATES.md` and
`company/METHOD.md` are L6's in wave 2, and FR-HP-26 exists to make that seam
explicit so neither lane assumes the other did it.

## Invariants in play (must not break)

- **Only the runner writes `gates.status`, and only the runner writes
  `gates.log`.** You are adding a second runner-only file, not a second writer.
- **The stamp is checksum-sealed.** Anything you add to the stamp payload goes
  INSIDE the checksum, or you have created a hand-editable field.
- **`company/gates.config` keeps its placeholders in the tracked tree.** This
  repo's real gate commands are local-only. Read `CLAUDE.md` on this before you
  touch anything near it.
- A failure to write telemetry never changes the runner's exit code. Logging is
  never load-bearing.
- Hooks fail OPEN; `guard_models --check` is a CLI gate and exits non-zero on a
  real finding, which is correct and not a violation of that rule.
- Python 3.8 stdlib only; the runner is POSIX shell and must stay portable.

## Frozen surfaces nearby (CR, never edit)

- `company/frozen-surfaces.json` IS a frozen surface, and changing the registry
  is itself a change-request action (METHOD mechanism 3, precedent CR-UPD-1).
  **File CR-2 and get it approved by the CEO before this lane merges** - that is
  FR-HP-27 and it is a merge condition, not paperwork.
- `company/state/gates.status` is already frozen. `gate_stamp.py` writes it
  through the filesystem rather than the Edit tool, so `guard_frozen` does not
  interfere.
- `.claude/settings.json` is READ by FR-HP-25 and written by nobody.

## Scope (ordered)

1. **FR-HP-28 - root resolution first**, because everything else stamps through
   it. Resolve from the working tree containing the cwd
   (`git rev-parse --show-toplevel`), falling back to `CLAUDE_PROJECT_DIR`, then
   `pwd`. That INVERTS today's order. The resolved root must also reach
   `gate_stamp.py`, which resolves its own root independently today - if you
   leave that seam open, the runner gates one tree and stamps another, which is
   a worse bug than the one you are fixing. A worktree ladder deliberately does
   NOT satisfy the main checkout's stamp (OQ-HP-14); that is intended, and the
   alternative is the false green this FR exists to kill.
2. **FR-HP-20 and FR-HP-21 - quiet-pass.** A passing gate prints its last 3
   non-empty lines plus one pointer line; a failing gate echoes everything.
   Every gate's full output is preserved at
   `company/state/gate-output/<gate>.log`. Today's runner writes a temp file,
   `cat`s it, and then `rm -f`s it - preserving that output is part of the
   change, because a pointer to a deleted file is worse than no pointer.
3. **FR-HP-22 - `gates.log`.** Exactly one appended line per ladder run: ISO-8601
   UTC timestamp, total duration, overall status, and one
   `NAME:RESULT:DURATION` field per gate in ladder order.
4. **FR-HP-23 - freeze and ignore the two new paths.** Add them to
   `guard_frozen.ALWAYS_DEFAULTS` (reaches existing installs), to the `always`
   list in `company/frozen-surfaces.json` (fresh installs), AND to `.gitignore`.
   All three, or the change is half-done - the fork did the registry and forgot
   the gitignore, and its run log is now committable.
5. **FR-HP-27 - file CR-2** covering both new patterns. Get CEO approval before
   merging.
6. **FR-HP-24 - `gate_stamp.write_stamp` writes atomically** through the L1
   helper. Torn stamp reads currently surface as false "malformed stamp" merge
   blocks.
7. **FR-HP-25 - the wiring gate.** `guard_models.py --check` asserts the FULL
   expected hook wiring from a declarative `(event, matcher, hook filename)`
   table. A row is checked only when that hook file exists, so an older install
   missing a newer hook is not failed for it. Only `.claude/settings.json`
   counts; `settings.local.json` is ignored; extra hooks and groups are allowed.
   Record the RATIONALE in the file itself - a fork un-wired a hook while its
   doctrine still called that hook a live integrity point, and no test caught it
   because the code never changed.

## Integration seams

- **L1 (this wave)** is rewriting `_common.py` and gives you the atomic write
  helper for FR-HP-24 and the content-based `work_hash` the stamp records. It is
  building in parallel: code against the helper name in FR-HP-02 and coordinate
  through your reports rather than editing `_common.py` yourself.
- **L6 (wave 2)** documents every runner change in `company/GATES.md` and
  `company/METHOD.md`. You guarantee the behavior; it guarantees the prose.
  FR-HP-26 says your ownership diff must touch no file under `company/` except
  `run-gates.sh`, `frozen-surfaces.json` and your CR.
- **The CEO** approves CR-2. File it early, not at the end.

## Definition of Done

- [ ] Every FR in scope (FR-HP-20 through FR-HP-28) implemented, tested, or
      explicitly deferred with a reason
- [ ] **Gates: run the two real suites from YOUR worktree root**, per
      `CLAUDE.md`: `python3 -m unittest discover -s tests/hooks -q` and
      `npm test`. Both green, pasted in your report. You are the lane FIXING
      `run-gates.sh`, so you may additionally exercise the runner directly as
      part of your testing - but the two suites above are what proves your tree.
- [ ] The full existing hook suite still passes - 393 was the baseline
- [ ] FR-HP-28 proven with a REAL `git worktree`: run the ladder from the
      worktree with `CLAUDE_PROJECT_DIR` pointing elsewhere, and assert the stamp
      lands in the worktree carrying the worktree's work hash while the other
      tree's stamp is untouched
- [ ] FR-HP-25 proven by removing the `stop_gate.py` command from a fixture
      settings file and asserting `--check` exits 1 naming `Stop` and
      `stop_gate.py`
- [ ] Quiet-pass proven by line COUNT against a fixture gate that prints 500
      lines, green and red
- [ ] CR-2 filed and approved before merge
- [ ] `company/gates.config` unchanged, and no real gate command committed
- [ ] No edits outside owned files; zero frozen surfaces patched locally
- [ ] Commits follow `company/GIT.md`: conventional, `Task: hp-runner` trailer,
      explicit staged paths, never `git add -A`
- [ ] Report per `company/templates/REPORT-TEMPLATE.md`, with 1-3 witness
      candidates

## Fallback assumptions

- OQ-HP-02: an exemption knob for the wiring assertion -> FALLBACK: none. A
  missing binding is a red gate and a CR. Tag `# OQ-HP-02 assumption`.
- OQ-HP-04: quiet-pass tail length -> FALLBACK: 3 lines plus the pointer, no
  knob. Tag `# OQ-HP-04 assumption`.
- OQ-HP-06: `gates.log` rotation -> FALLBACK: none in 0.2.7. Tag it.
- OQ-HP-14: a worktree ladder does not satisfy the main checkout's stamp ->
  FALLBACK: yes, intended. Tag `# OQ-HP-14 assumption`.

## Out of scope

Explicitly, so nobody helpfully expands:

- **Repo-scoped cached gate skips, the `repo` gate field, and `tree_hashes`
  stamp keying** from the reference implementation. This repo is single-repo,
  `company/specs/spec-repo-scoped-enforcement.md` is already parked with
  evidence refuting the premise, and the reference `check_stamp` returns green
  UNCONDITIONALLY when its tree-hash map is empty - which is every single-repo
  project, i.e. a false-green generator. Do not port any of it, and say so in
  your report so nobody re-adds it.
- Every doctrine file. L6, wave 2.
- Splitting the ladder into worktree-meaningful versus integration-only gates.
  Parked owner decision.
- `company/gates.config`, `package.json`, `install.sh`, `update.sh`,
  `.github/workflows/`.

## Report back

Facts only: what changed (paths), both suites' output pasted, the FR checklist,
the transcript-line before-and-after for a green ladder, ownership diff summary,
CR-2 status, deviations and why, worries for the CEO, and your witness
candidates.
