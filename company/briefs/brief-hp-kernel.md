# BRIEF: hp-kernel

_Type: program-workstream (L1 of the harness-port program).
Spec: `company/specs/spec-harness-port.md` - read ONLY the FR-HP-01 through
FR-HP-08 blocks and the OQ register rows named below. The rest of the spec is
not yours.
Lead: tech-lead. Date: 2026-08-13. Tracking issue: #98._

> Schema, contracts, kernel, shared UI, and anything in
> `company/frozen-surfaces.json` are FROZEN - consume them exactly as shipped;
> any change goes through `company/change-requests/`, never a local edit.

## Mission

`.claude/hooks/_common.py` is the kernel every hook leans on, and it carries two
defects that the rest of this program cannot be built on top of. First, it has
no concurrency protection at all: we shipped multi-session task entries in
v0.2.6, which makes several sessions against one working tree normal, and every
read-modify-write in the state layer can still silently lose an update. Second,
`work_hash` fingerprints history POSITION (HEAD plus status plus diffs), so
committing audited work invalidates the audit and the gate stamp even when not
one byte of content changed. Success is a kernel that serializes state writes,
survives torn reads, and answers "has the work changed" by content rather than
by git history position - with the whole existing suite still green.

The hard constraint that must survive contact with reality: **hooks fail OPEN.**
Every mechanism you add must degrade to today's behavior rather than to a block.
A lock that cannot be taken proceeds unlocked. A hash that cannot be computed
falls back to the legacy digest. You are making the kernel safer, and a kernel
that jams a session is worse than the bug you are fixing.

## Read first (in order)

1. `CLAUDE.md` (project canon - the dual-nature rule, the two real gate suites,
   Python 3.8 stdlib only)
2. `company/METHOD.md` (how the team works; mechanism 4 and 5 are what this
   kernel enforces for everyone else)
3. `.claude/hooks/_common.py` (the whole file - you own it, and every other hook
   imports it)
4. `company/specs/spec-harness-port.md`, FR-HP-01 through FR-HP-08 only, plus
   OQ-HP-03, OQ-HP-07, OQ-HP-10 and OQ-HP-11. Those FR blocks carry the
   acceptance criteria with concrete values; implement to them exactly.
5. `tests/hooks/test_hooks.py` and `tests/hooks/test_multi_task_gates.py`
   (the existing idiom for temp-repo fixtures - match it, do not invent a new
   one)
6. `/Users/redomic/Documents/Projects/DevMesh/.claude/hooks/_common.py` - the
   working reference implementation. Diff against it when this brief or the
   spec is ambiguous. It is a REFERENCE, not a specification: it is a polyrepo
   working copy and carries `GATED_REPOS`, `gate_tree_hashes` and a
   `tree_hashes` stamp branch that you must NOT port (see Out of scope).

## You own

- `.claude/hooks/_common.py`
- `tests/hooks/test_state_kernel.py` (new file, yours to create)
- `company/adr/ADR-0002-content-based-freshness.md` (new, `Status: accepted`)

Nothing else. Anything not listed is read-only to you. Two other lanes are
building in parallel on `guard_commit.py`, `guard_secrets.py`, `guard_spec.py`,
`guard_provenance.py`, `run-gates.sh`, `gate_stamp.py`, `guard_models.py` and
`guard_frozen.py`. If a fix you need lives in one of those, report it - do not
make it.

## Invariants in play (must not break)

- **Hooks fail OPEN.** An internal error lets the action through. The two
  integrity CLIs (`witness_check.py`, `trace_check.py`) are the only exceptions
  and you are not touching them.
- **Python 3.8, stdlib only.** No new dependency, ever.
- `fcntl` is not available everywhere. Its absence is a fail-open path, not an
  error path.
- Only `run-gates.sh` writes `gates.status`; only `guard_provenance` writes the
  ledger; only `witness_check.py --add/--remove` mutates the witness registry.
  You are adding the primitives those writers will use, not new writers.
- Every existing caller of `work_hash`, `active_tasks`, `check_stamp` and
  `stamp_is_green` keeps working unchanged. This is a kernel: a signature change
  is a breaking change to eight other files you do not own.
- `company/` ships verbatim into installs and stays generic.

## Frozen surfaces nearby (CR, never edit)

- `company/state/gates.status`, `adherence.log`, `costs.log`,
  `.cost-cursor.json` and `provenance-ledger.json` are all on the frozen
  `always` list. You read and hash them; you do not edit them by hand.
- `company/frozen-surfaces.json` itself is owned by lane L3 this wave. If you
  need a registry entry, file a CR in `company/change-requests/`.
- ADR-0002 is yours to CREATE. An accepted ADR is immutable from the moment it
  says `Status: accepted`, so get it right the first time.

## Scope (ordered)

Build in this order. Each step lands with its tests; do not batch the suite to
the end.

1. **FR-HP-01 - `state_lock(root, timeout=2.0)`.** A context manager taking an
   exclusive non-blocking `flock` on `company/state/.state.lock`, retrying on a
   short poll until the timeout, then proceeding UNLOCKED. No `fcntl`, any
   exception, or a timeout all yield unlocked rather than raising. The fd is
   released on the way out even when the body raises - use a real `try/finally`,
   and note that the fork's `cost_capture` enters and exits this manager by hand
   and leaks the fd on an exception. Do not copy that pattern; your tests should
   make it impossible.
2. **FR-HP-02 - atomic JSON write helper.** `mkstemp` in the destination
   directory, write, flush, `os.replace`. A failure mid-write leaves both the
   destination and the directory clean, with no stray temp file.
3. **FR-HP-03 and FR-HP-04 - torn reads.** `active_tasks(root)` retries a read
   that parses as nothing while the file exists (OQ-HP-10 fixes this at 3
   retries, 0.06s apart). New `active_tasks_unreadable(root)` returns True only
   when the file EXISTS and does not parse, so callers can tell "no tasks" from
   "cannot tell". You add the primitive; L4 wires it into `guard_spec`.
4. **FR-HP-05 - content-based `work_hash`.** Build the git tree the working copy
   WOULD commit, in a throwaway index (`GIT_INDEX_FILE` pointing somewhere
   temporary, `read-tree HEAD` when HEAD exists, `add -A`, drop the excludes,
   `write-tree`), and return that oid. **The real repo's `.git/index` must not
   be touched** - assert it in a test, because corrupting a developer's index is
   the worst thing this program could do. Any git trouble falls back to the
   legacy digest, which is stricter and therefore safe.
5. **FR-HP-06 - `HASH_EXCLUDES` is exactly `("company/state",)`.** The fork also
   excludes `*.md` and `*.txt` on the grounds that prose decides no gate
   outcome. That is TRUE for a product app and FALSE here: markdown IS this
   product - agent definitions, skills, COMPANY.md, doctrine - and
   `no_slop`, `trace_check` and `guard_models` all gate it. Implement the
   exclusion tuple so the difference is a one-line change, and leave a comment
   recording WHY prose stays in, so a future reader does not "fix" it.
6. **FR-HP-07 - slow-hash breadcrumb.** A `work_hash` call over 1.5 seconds
   writes one TIMING line to `adherence.log`. Log-only; it reaches no decision.
7. **FR-HP-08 - ADR-0002.** Record the freshness model change: what the old
   digest was, what content-hashing means, why prose is deliberately still
   hashed in this repo, and the fallback. Cite FR-HP-05 and FR-HP-06.

## Integration seams

- **L4 (wave 2)** consumes `state_lock` and the atomic writer for the witness
  registry and the cost cursor, and `active_tasks_unreadable` for the
  `guard_spec` fail-open path. You guarantee those three primitives exist with
  the signatures above; you may assume nobody calls them this wave.
- **L5 (wave 2)** consumes `state_lock` for every ledger read-modify-write.
- **L3 (this wave)** consumes the atomic writer for `gates.status` and reads
  `work_hash`. It is building in parallel, so it will merge against your kernel:
  keep the helper's name and signature stable once your first commit lands, and
  say so in your report.
- You may assume no other lane changes `_common.py` this wave.

## Definition of Done

- [ ] Every FR in scope (FR-HP-01 through FR-HP-08) implemented, tested, or
      explicitly deferred with a reason
- [ ] **Gates: run the two real suites from YOUR worktree root**, per
      `CLAUDE.md`: `python3 -m unittest discover -s tests/hooks -q` and
      `npm test`. Both green, pasted in your report. Do NOT run
      `bash company/run-gates.sh` - it resolves the project root from
      `CLAUDE_PROJECT_DIR`, which the harness pins to the MAIN checkout, so from
      a worktree it gates and stamps somebody else's tree. Lane L3 is fixing
      exactly that this wave; until it merges, the two suites above are the
      truth for you.
- [ ] The full existing hook suite still passes unchanged - 393 tests was the
      baseline before this program. A test you had to EDIT to make pass is a
      finding for your report, not a fix.
- [ ] No edits outside owned files; zero frozen surfaces patched locally
- [ ] Tests added for new behavior, in `tests/hooks/test_state_kernel.py`
- [ ] FR-HP-01 proven by a real TWO-PROCESS test (subprocess, not two threads),
      showing both updates survive a race that loses one without the lock
- [ ] FR-HP-05 proven by hash INVARIANCE across `git add` and across a commit of
      identical content, and hash CHANGE on a real source edit
- [ ] A test asserting `.git/index` is byte-identical before and after
      `work_hash`
- [ ] Commits follow `company/GIT.md`: conventional, `Task: hp-kernel` trailer,
      explicit staged paths, never `git add -A`
- [ ] Report follows `company/templates/REPORT-TEMPLATE.md`, and proposes 1-3
      witness candidates (the exact spots that break first if this regresses)

## Fallback assumptions

Implement THESE and tag the site - do not guess, do not ask:

- OQ-HP-03: slow-hash threshold -> FALLBACK: 1.5 seconds, log-only, no knob.
  Tag `# OQ-HP-03 assumption`.
- OQ-HP-07: whether `.gitignore` changes reach installs -> FALLBACK: repo-local
  only; `company/state` is hash-excluded so nothing stales.
- OQ-HP-10: torn-read retries -> FALLBACK: 3 retries, 0.06s apart.
  Tag `# OQ-HP-10 assumption`.
- OQ-HP-11: `state_lock` timeout -> FALLBACK: 2.0s, then proceed UNLOCKED with
  no log line at the kernel level. Tag `# OQ-HP-11 assumption`.

## Out of scope

Explicitly, so nobody helpfully expands:

- `GATED_REPOS`, `gate_tree_hashes`, and the `tree_hashes` branch of
  `stamp_is_green` from the reference implementation. They are polyrepo-specific
  and the stamp branch is a FALSE-GREEN GENERATOR here: it returns green
  unconditionally when the tree-hash map is empty, which is every single-repo
  project. Do not port any of it, and say so in your report so nobody re-adds it.
- Wiring the new primitives into any other hook (L3, L4, L5 own that).
- Anything touching commit-versus-merge gate timing - that is a parked owner
  decision, not yours.
- `company/gates.config`, `package.json`, `install.sh`, `update.sh`,
  `.github/workflows/`.

## Report back

Facts only: what changed (paths), both suites' output pasted, the FR checklist,
ownership diff summary, CRs filed, deviations from this brief and why, worries
for the CEO, and your witness candidates.
