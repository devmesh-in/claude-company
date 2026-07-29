# SPEC: repo-scoped enforcement (the enforcement unit becomes the working tree)

_Type: feature. Author: product-manager. Date: 2026-07-29._
_Status: PARKED - NOT DISPATCHED. Do not build from this without re-reading the
note below first._
_Slug: `repo-scoped-enforcement`. Target release: none. It was written against
0.2.6 and deliberately left out of it._

## PARK NOTE (CEO, 2026-07-29) - read before you build any of this

This spec was commissioned to fix a polyrepo umbrella install (DevMesh) where a
clean, fully-delegated session could not reach Stop. Measured against that real
install AFTER the spec was written, its central premise did not hold:

- Git does not recurse into nested repositories. All seven sub-repos carry their
  own `.git`, so the umbrella `git status` never saw one line of their source.
- All 71 paths blocking that install were UMBRELLA-LEVEL files: 66 under
  `.playwright-mcp/` (screenshots and console logs), one `ORCHESTRATOR.md.new`
  that `claude-company update` creates itself, a stray png, two fonts, one html.
- The company had authored 8 files, all clean. The intersection of "dirty" and
  "self-authored" was ZERO.

So repo scoping would not have unblocked that install - the orchestrator session
runs at the umbrella root and would have resolved to the umbrella anyway.

The cheaper and more principled fix, identified but NOT built: Mode C and Mode D
should require an audit for `dirty_source_paths` INTERSECTED WITH the ledger's
`self_authored` list, rather than for every dirty path. The doctrine says
"nothing SELF-AUTHORED integrates unaudited"; the code has never actually asked
that question. Doing so makes the gate correct for polyrepo universally without
any scoping machinery, because it stops asking a tree-shaped question. Its one
cost is that source written via Bash is not in `self_authored` and would stop
triggering the requirement - a narrow, nameable, testable hole.

The owner chose to ship 0.2.6 without either fix. This spec is kept because its
fact-classification table, its zero-subprocess resolver, and its analysis of the
Stop hook having no path to scope from all remain correct and reusable - and
because the worktree-commit P1 and issue #37 are genuinely separate from the
DevMesh block and still open. Re-validate the premise against a real install
before dispatching any of it.

The spec is rich and human-facing; it can be long. The builder agent NEVER
reads it - it reads the brief derived from it. Reference, do not embed.

Owner decision of record (2026-07-29, carried in the dispatch): the fix is
fundamental, not surgical. **The enforcement unit becomes the git working tree
that contains the thing being acted on**, rather than `CLAUDE_PROJECT_DIR`.
This spec does not reopen that shape; it makes it buildable and checkable.

Release note the CEO must resolve before dispatch: `company/state/STATUS.md`
records v0.2.6 as PREPARED and awaiting the owner's tag. If that tag is cut
before this merges, the target is 0.2.7 (OQ-RSE-12). Nothing in the spec
depends on which.

Tracking issues: TBD at dispatch - one per commit band in Part 3. Recorded in
`company/state/active-task.json` `"issues"` before the first builder spawn; the
FR-DE-15 tracking gate blocks the dispatch otherwise.

## Part 1 - Product requirements

### Problem

`_common.project_root(payload)` returns `CLAUDE_PROJECT_DIR`, else the payload
cwd, else `os.getcwd()`. Every TREE FACT in the enforcement system is then
computed against that one root:

| Fact | Computed as | Site |
|---|---|---|
| dirty source paths | `git -C <root> status --porcelain -uall -- . :(exclude)company/state` | `guard_provenance.dirty_source_paths` :251 |
| tree fingerprint | `git -C <root> rev-parse HEAD / status / diff / diff --cached` | `_common.work_hash` :244 |
| current branch | `git -C <branch_dir> symbolic-ref --short HEAD` | `_common.current_branch` :217, called from `guard_commit` :184 |
| gate stamp and staleness | `<root>/company/state/gates.status` vs `work_hash(root)` | `_common.check_stamp` :281 |
| staged-index secrets scan | `git -C <root> diff --cached -U0` | `guard_secrets` :209 |

That encodes one assumption: **project root == one git repository == one
working tree.** The assumption is false in two shipped configurations.

**Polyrepo umbrella.** The owner's DevMesh install puts `company/` at an
umbrella root that contains N git repos. Every fact above is then computed
across all of them at once.

**Git worktrees.** A dispatched builder works in `.claude/worktrees/<slug>` on
`task/<slug>`, but the harness pins the payload cwd to the main checkout, so
every cwd-derived fact describes a tree the agent is not working in.

Three currently-open defects are the same root cause:

1. **The umbrella dirty check (P1, `WORRIES.md` row recorded 2026-07-29).**
   `dirty_source_paths` counts dirty source anywhere under the umbrella as THIS
   session's unaudited work. Two call sites share the identical function -
   `guard_provenance.py` :832 (Mode C, commit) and :878 (Mode D, Stop). A
   clean, fully-delegated session therefore cannot reach Stop without faking an
   audit or deleting another session's files. This is actively blocking the
   DevMesh project.
2. **Worktree agents cannot commit (P1, `WORRIES.md` row 1).** `guard_commit`
   resolves the branch through `git_cwd(payload, root)` :67, which prefers the
   payload cwd; the harness pins that to the main checkout, so a developer in
   `.claude/worktrees/<slug>` on `task/<slug>` is judged to be on `main` and
   blocked as "commit on protected branch". The workaround is the CEO
   committing from the main checkout, which converts every delegated build into
   self-authored work and defeats the delegation economics.
3. **Stamp-root mismatch (issue #37).** `guard_commit` :228 reads
   `check_stamp(root)`, and `work_hash(root)` fingerprints the main checkout.
   Work in a worktree or a sibling repo is invisible to that fingerprint, so a
   green stamp that never saw the work still authorizes its commit. This one is
   a hole in the ALLOW direction: it is a false green, not friction.

The cost today: in the umbrella, the enforcement layer is unusable and is being
worked around by hand; in a worktree, delegation silently degrades into
self-authored work; and at the commit gate, the stamp can be green for a tree
nobody gated. All three are the same missing concept - the system has no notion
of WHICH working tree a fact belongs to.

### Goal and success metrics

Every tree fact is computed against the working tree that contains the thing
being acted on. Task facts stay global, because one `company/` is one company
regardless of how many repos it governs. In an ordinary single-repo install
nothing changes at all, byte for byte.

Binary success signals, all must hold:

- **SM-1 - single-repo identity.** Every existing test file under
  `tests/hooks/` passes with ZERO edits. Any existing assertion that has to
  change is a defect, not a design choice. Plus a parity suite: for every hook
  and every event, a single-repo fixture produces byte-identical exit code,
  stdout, stderr, and appended `adherence.log` line before and after this
  change, compared against goldens captured at the merge base.
- **SM-2 - zero cost when there is nothing to resolve.** In a single-repo
  fixture, no hook spawns a single additional subprocess for tree resolution
  (asserted by counting `_common._git` invocations, not by inspection).
- **SM-3 - the umbrella P1 is closed.** Umbrella fixture: root repo `R` plus
  sibling repo `B`, `B` dirty with unaudited source, `R` clean, one delegated
  feature entry active. Stop produces no block decision. Same fixture with `R`
  dirty instead: Stop still blocks.
- **SM-4 - the commit half is closed.** Same fixture: `git commit` run in `B`
  with `B` dirty and no audit BLOCKS; `git commit` run in `B` with `B` clean
  and `R` dirty ALLOWS.
- **SM-5 - the worktree P1 is closed.** Payload cwd is the main checkout on
  `main`; the command is `cd .claude/worktrees/x && git commit -m msg`, and the
  worktree is on `task/x`. The commit is ALLOWED and Mode C treats it as
  worktree work. The same command without the `cd` is BLOCKED with today's
  exact protected-branch message.
- **SM-6 - #37 is closed in the safe direction.** A green stamp that
  fingerprints only the project root does NOT authorize a commit in a tree it
  does not fingerprint: that commit is BLOCKED with a reason naming the tree.
  After the gate suite runs from that tree, the same commit is allowed.
- **SM-7 - no forbidden narrowing.** For `guard_spec`, `guard_tests`,
  `guard_models`, `stop_gate`, and `guard_provenance` Mode A / Mode B / Mode E,
  a test proves that introducing a second working tree does not turn any block
  into an allow.
- **SM-8 - the staged scan gets stronger, not weaker.** A staged secret in
  sibling repo `B`, committed from `B`, is BLOCKED. Today it is allowed,
  because the scan reads the umbrella index.
- **SM-9 - gate ladder.** `python3 -m unittest discover -s tests/hooks -q`,
  `npm test`, `bash tests/install/run_tests.sh`, and
  `bash tests/install/test_update.sh` all green.

### Users and personas

- **The single-repo client (the overwhelming majority, and the one who must
  notice nothing).** One repo, one working tree, `CLAUDE_PROJECT_DIR` equal to
  the git toplevel. Every behavior, message, log line, and cost is unchanged.
  This persona is the reason BR-RSE-01 exists.
- **The umbrella CEO session (the persona in pain).** One `company/` at an
  umbrella root, N git repos beneath it, tasks that span them. Full write
  access to `company/state/`. Needs the dirty check, the commit gate, and the
  Stop gate to speak about the repo being acted on.
- **The dispatched tech lead / developer in a worktree.** Works in
  `.claude/worktrees/<slug>` with a harness-pinned cwd pointing elsewhere.
  Never writes `company/state/`. Needs its commits judged by its own branch and
  its own tree, and now must run the gate suite from its own tree (a new
  obligation - see RISK-RSE-04).
- **The auditor (read-only).** Its completion writes an audit record. That
  record must now say WHICH trees it covered, so it cannot vacuously satisfy a
  gate over a tree it never read.
- **The owner (escalation only).** Owns whether polyrepo umbrella installs are
  a supported product configuration (OQ-RSE-11). Not consulted mid-build.

No new privilege surface. No new state file. One new CLI flag
(`gate_stamp.py --check --tree`).

### User stories and acceptance criteria

- **US-RSE-1**: As a single-repo client, I see no change whatsoever.
  - AC: given a project where `CLAUDE_PROJECT_DIR` is the git toplevel, when
    any hook fires on any event, then exit code, stdout, stderr, and the
    appended `adherence.log` line are byte-identical to the pre-change build,
    and no additional subprocess is spawned.

- **US-RSE-2**: As an umbrella CEO session that delegated all of its work, I
  can finish my turn without touching another repo's files.
  - AC: given umbrella root `R` with sibling repo `B`, `B` holding dirty
    unaudited source that this session never edited, `R` clean, and one
    `feature` entry with `execution: delegated` and a recorded dispatch, when
    the Stop event fires, then `guard_provenance` Mode D prints nothing and
    exits 0, and `adherence.log` carries one `SCOPE` line naming the tree set
    the decision was made over.

- **US-RSE-3**: As an umbrella CEO session, dirty source in the repo I am
  committing still blocks me.
  - AC: given the same fixture with `B` dirty and no fresh audit covering `B`,
    when a `git commit` runs with `B` as its effective git directory, then Mode
    C exits 2 and the message names `B` and lists `B`'s dirty paths.

- **US-RSE-4**: As a dispatched developer in a worktree, my commit is judged by
  my worktree's branch, not by the main checkout's.
  - AC: given payload cwd `<root>` on branch `main`, a worktree at
    `<root>/.claude/worktrees/x` on `task/x`, and one active `feature` entry,
    when the Bash command is `cd .claude/worktrees/x && git commit -m "x"`,
    then `guard_commit` does not block on the protected-branch rule and
    `adherence.log` records the tree it judged.
  - AC: given the same state and the command `git commit -m "x"` with no `cd`,
    then `guard_commit` exits 2 with today's exact protected-branch message.

- **US-RSE-5**: As the harness, a green gate stamp never speaks for a tree it
  did not fingerprint.
  - AC: given `gates.status` green and fresh for the project root and carrying
    no fingerprint for `.claude/worktrees/x`, when a commit runs with that
    worktree as its effective git directory, then `guard_commit` exits 2 with
    reason `gates.status has no fingerprint for .claude/worktrees/x`, and the
    message names the recipe (run the gate suite from that tree).

- **US-RSE-6**: As an auditor, my audit covers exactly the trees I was pointed
  at, and a gate over another tree is not satisfied by it.
  - AC: given an audit record whose `trees` map covers only `.`, when Mode C
    gates a commit in sibling repo `B`, then `fresh_audit` is false and the
    block reason is `audit does not cover B`.
  - AC: given a legacy audit record carrying only a scalar `work_hash` and no
    `trees` map, when Mode C gates a commit at the project root in a
    single-repo install, then it is treated exactly as today.

- **US-RSE-7**: As a support engineer reading `adherence.log`, I can tell which
  tree every non-default decision was made against.
  - AC: given any BLOCK, BYPASS, GRANT, or SCOPE line produced while the
    resolved tree is not the project root, then the line carries a
    `tree=<key>` segment; and given the resolved tree IS the project root, then
    no such segment appears anywhere in the line.

### Functional requirements

Stable IDs. Every FR is later implemented, tested, or explicitly deferred - the
traceability gate checks these IDs against the PR. Each FR that narrows a scope
states the invariant it protects and why the narrowing is safe, because
narrowing is the direction that silently disarms gates (BR-RSE-03).

#### Group A - working-tree resolution (`_common`)

- **FR-RSE-01** - **`_common.working_tree(path, root) -> str`.** Returns the
  deepest ancestor directory of `path` that is at or below `root` and contains
  a `.git` entry (file OR directory - a linked worktree and a submodule both
  carry `.git` as a file). If no such ancestor exists, returns `root`. The walk
  NEVER looks above `root`: a home directory that happens to be a git repo must
  never become an enforcement scope. If `path` names a file, the walk starts at
  its dirname; if `path` does not exist yet, the walk starts at its nearest
  existing ancestor; if `path` is empty or outside `root`, the function returns
  `root`. Never raises, never returns None, never returns "" - the worst case
  is the project root, which is today's scope (BR-RSE-05).

- **FR-RSE-02** - **no subprocess is spent on resolution.**
  `working_tree` is a pure filesystem walk (`os.path.exists` per ancestor). It
  does NOT call `git rev-parse --show-toplevel`, so it has no timeout, no
  nonzero-exit, and no missing-git failure mode to fail open from. The
  deliberate trade is recorded in OQ-RSE-02: `GIT_DIR` / `GIT_WORK_TREE` /
  `GIT_CEILING_DIRECTORIES` overrides are not honored, and a bare repo is not
  detected. The residual is bounded because every consumer then runs
  `git -C <tree> ...`, and git re-resolves the repository itself; the only
  thing a wrong walk can change is the `-- .` pathspec anchor.
  _Invariant protected:_ hooks stay cheap enough to run on every event, and the
  5 second `_git` timeout can never turn a scope resolution into a stall.

- **FR-RSE-03** - **memoization.** `working_tree` memoizes on the normalized
  start directory in a module-level dict, and `_common` exposes
  `reset_tree_cache()` for tests. One hook process handles one event, so the
  cache lifetime is one event. Budget (BR-RSE-11): a path-bearing event costs
  at most one walk of depth `d`, where `d` is the number of path segments
  between the acted-on path and the project root; the Stop event costs at most
  one walk per DISTINCT directory in the session tree set.

- **FR-RSE-04** - **`_common.tree_key(root, tree) -> str`.** The stable
  identity of a tree in logs, messages, and the stamp: `"."` when `tree` is
  `root`, else the forward-slash path of `tree` relative to `root`, else the
  absolute path when `tree` is not under `root` (OQ-RSE-01).

- **FR-RSE-05** - **`_common.scope_dir(root, tree) -> str`.** The directory a
  scan runs in: `tree` when `tree` is at or below `root`, else `root`. This
  exists because today's scans pass `-- .`, which anchors on the `-C`
  directory; running a scan from a tree ABOVE the project root would widen the
  scan rather than narrow it. `scope_dir(root, root) == root`, so today's calls
  are unchanged.

- **FR-RSE-06** - **`_common.work_hash(root, tree=None)`.** `tree=None` means
  `root` and the body is byte-identical to today (same four git calls, same
  digest order, same `no-git` fallback). With a tree, the same four calls run
  with `-C scope_dir(root, tree)`. The `company/state` exclusion is kept
  verbatim for every tree, because `company/state` only exists in the umbrella
  tree and the exclusion pathspec is harmless where it matches nothing.

- **FR-RSE-07** - **`_common.check_stamp(root, tree=None)`.** With `tree` None,
  or with a tree whose `tree_key` is `"."`, the function is byte-identical to
  today, including every reason string. With any other tree: the stamp must be
  valid and green as today, and then the freshness comparison reads
  `stamp["trees"][tree_key]` instead of `stamp["work_hash"]`. A missing `trees`
  map, or a `trees` map with no entry for that key, returns
  `(False, "gates.status has no fingerprint for <key> (gates have not run in
  that working tree)")`.
  _Invariant protected:_ nothing commits over red or stale gates. A stamp
  speaks only for the trees it fingerprints (BR-RSE-06); absent coverage is
  treated as stale, which BLOCKS. This closes #37 in the ALLOW-to-BLOCK
  direction.

#### Group B - resolving the tree a git command acts on

- **FR-RSE-08** - **one copy of the command parser.** `segments(command)` and
  `git_subcmd(segment)` move into `_common` verbatim. `guard_commit` and
  `guard_secrets` (which carries a copied idiom at :71) and
  `guard_provenance` (:811-812) all call the `_common` copy. No aliases are
  left behind, because a shim is how two copies silently diverge again.

- **FR-RSE-09** - **`git_subcmd` consumes option ARGUMENTS.** Today the parser
  skips tokens starting with `-`, so `git -C x commit` returns subcommand `x`
  and every Bash gate misses the commit entirely (`WORRIES.md` P3 row). The
  parser now consumes the argument of the option-with-argument forms `-C`,
  `-c`, `--git-dir`, `--work-tree`, `--namespace`, `--exec-path` (both the
  `--opt=value` and the `--opt value` spellings), then returns the first
  remaining non-option token as the subcommand.
  _Invariant protected:_ gates arm on commits. This is a strengthening only:
  commands that previously slipped past `guard_commit`, `guard_secrets`, and
  Mode C now reach them. RISK-RSE-06 records that this can surface as new
  blocks in the field on release.

- **FR-RSE-10** - **`_common.effective_git_dir(payload, command, seg_index)
  -> str`.** The directory git will actually run in, resolved from exactly what
  git itself will act on, and nothing else:
  1. start at the payload cwd if present, else `root`;
  2. walk the segments preceding `seg_index` in order; for each segment that
     is exactly `cd <one-token>`, apply it (absolute token replaces, relative
     token joins) - this mirrors the shell, which is cumulative;
  3. if any preceding segment starts with `cd` but does not match that exact
     shape (`cd` with no argument, `cd -`, `~`, a variable, a substitution,
     more than one token), ABANDON cd tracking entirely and return the payload
     cwd. Ambiguity resolves toward today's answer;
  4. a `-C <dir>` on the git invocation itself wins over the accumulated cd
     (git applies it last), joined relatively against the accumulated cd;
  5. if the resolved directory does not exist, return the payload cwd.
  _Invariant protected:_ the branch and the tree a commit is judged by must be
  the branch and tree git writes. Safety argument, stated as BR-RSE-08: this
  parses only tokens git will honor, so a divergence requires a parse bug, not
  a crafted command. Every unparseable form falls back to today's answer, which
  is the blocking direction for the protected-branch rule.

- **FR-RSE-11** - **`guard_commit` uses the effective git directory.**
  `git_cwd(payload, root)` is REPLACED by `effective_git_dir`. The
  protected-branch check reads `current_branch(effective_git_dir)`, the
  `push_targets_protected` bare-push check reads the same, and the stamp check
  reads `check_stamp(root, working_tree(effective_git_dir, root))`. When the
  effective git directory is outside the project root, the stamp check keeps
  today's `check_stamp(root)` exactly (identity: this is today's behavior for
  out-of-tree commits and is not this spec's problem to fix).
  _Invariant protected:_ work belongs on a task branch. Judging by a tree the
  command does not write is not enforcement; it is the noise that pushes
  delegated work back into the main checkout. This is the worktree half of
  ACCEPTED narrowing N-3 (BR-RSE-03).

#### Group C - provenance scoping

- **FR-RSE-12** - **`dirty_source_paths(root, tree=None)`.** With `tree` None
  the body is byte-identical to today. With a tree, the status runs with
  `-C scope_dir(root, tree)` and the returned paths stay relative to that scope
  directory. Callers that render paths in a message prefix them with
  `<tree_key>/` when the key is not `"."`.

- **FR-RSE-13** - **Mode C scopes to the tree the commit writes.** For each
  `commit` segment, `dir = effective_git_dir(...)` and
  `tree = working_tree(dir, root)`. The existing worktree/out-of-tree
  exemption at :827 now tests `dir` instead of `payload.get("cwd")` - which is
  the Mode C half of the worktree P1, because the payload cwd is the harness's
  answer, not the shell's. The `MERGE_HEAD` check reads `<tree>/.git/MERGE_HEAD`
  (and, for a linked worktree where `.git` is a file, the commit is already
  exempt before that line, so no extra handling is needed). The dirty check
  becomes `dirty_source_paths(root, tree)`.
  _Invariant protected:_ nothing self-authored integrates on the authority of
  the context that produced it. ACCEPTED narrowing N-1: a commit writes exactly
  one working tree, and dirty source in a repo this commit cannot touch is not
  evidence about this commit. Visible per FR-RSE-26.

- **FR-RSE-14** - **`session_tree_set(root, payload, ledger) -> list`.** The
  ordered, de-duplicated set of working trees a Stop-time decision is made
  over:
  `[working_tree(payload.get("cwd") or root, root)]` (the FLOOR - always
  present, always first) `+ [working_tree(join(root, rec["tree"] or rec["path"]),
  root) for rec in ledger["self_authored"]]`.
  It lives in `guard_provenance` beside the other ledger helpers, because the
  ledger is its only non-payload input. It is memoized through
  `working_tree`'s cache. In a single-repo install it always returns `[root]`.
  _Where the record lives:_ nowhere new. `self_authored` is the ledger list
  Mode A already appends to on every source edit; FR-RSE-17 tags each record
  with its tree so the set can be computed without inventing session-keyed
  state, which the multi-session spec deliberately scoped out.

- **FR-RSE-15** - **Mode D scopes to the session tree set.** After today's
  entry filtering and manifest check, Mode D computes
  `trees = session_tree_set(...)`, then
  `dp = [(t, p) for t in trees for p in dirty_source_paths(root, t)]`, then
  `fresh_audit(root, ledger, trees)`. The block decision is emitted exactly as
  today when `dp` is non-empty and the audit is not fresh, with the reason
  additionally naming the tree(s) that hold the dirty paths.
  _Invariant protected:_ a session does not finish holding self-authored source
  changes no independent verifier audited. This is ACCEPTED narrowing N-2 and
  the riskiest decision in this spec - see BR-RSE-03 and RISK-RSE-01 for the
  hole it opens and the floor that bounds it.

- **FR-RSE-16** - **the SCOPE line.** Whenever Mode D resolves a tree set that
  is not exactly `[root]`, it appends one `adherence.log` line
  `<ts> | guard_provenance | SCOPE | <tree keys joined by "+"> | stop-gate
  scope` BEFORE evaluating, whether or not it goes on to block. This is the
  mechanism that makes narrowing N-2 auditable rather than silent: a reader can
  see which trees the gate did and did not consider. In a single-repo install
  the line is never written, so `adherence.log` stays byte-identical (SM-1).

- **FR-RSE-17** - **`self_authored` records gain `tree`.** Mode A appends
  `{"path": rel, "tree": tree_key(root, working_tree(file_path, root)), "at":
  ...}`. `path` stays relative to the PROJECT ROOT exactly as today, so
  existing records and existing assertions are untouched; `tree` is additive.
  A record with no `tree` key is read as `"."`.

- **FR-RSE-18** - **audit records gain `trees`, and `fresh_audit` is ALL over
  trees.** Mode B-post writes `{"role", "at", "verdict", "work_hash":
  <root hash, unchanged>, "trees": {key: hash for every tree in
  session_tree_set(...)}}`. `fresh_audit(root, ledger, trees=None)`:
  - `trees` None or `[root]`: today's body verbatim, matching on the scalar
    `work_hash` field. This is what keeps every existing record and every
    existing test valid.
  - otherwise: true iff for EVERY tree in `trees` some audit record with a
    verdict other than `do-not-ship` carries a matching hash for that tree's
    key - reading a record with no `trees` map as covering `"."` only.
  ALL, not ANY, because an audit that read repo `A` is not evidence about repo
  `B`; ANY would be a false green, which is the one thing this change must not
  produce.

- **FR-RSE-19** - **`staleness_reason(root, ledger, trees=None)`** keeps its
  three existing strings verbatim for the single-tree case, and gains a fourth
  for the multi-tree case: `audit does not cover <tree keys>` naming the trees
  with no matching record.

- **FR-RSE-20** - **explicit NON-changes in `guard_provenance`.** Mode A's
  `in_worktree_or_out_of_tree` exemption, Mode B-pre's dispatch attribution and
  tracking gate, and Mode E's tracking / execution-decision / per-slug dispatch
  checks are NOT tree-scoped and are not touched. They read TASK facts from
  umbrella-global state (BR-RSE-09). Scoping any of them by tree would let an
  edit in sibling repo `B` escape the brief, the execution decision, and the
  dispatch requirement, which is precisely the forbidden direction. This FR
  exists so a builder does not helpfully extend the change.

#### Group D - secrets

- **FR-RSE-21** - **the staged-index scan runs in the commit's tree.**
  `guard_secrets.run_hook` resolves `dir = effective_git_dir(...)` for the
  first `commit` segment and scans `git -C dir diff --cached -U0`. In a
  single-repo install `dir` is the project root and the scan is identical.
  _Invariant protected:_ no secret enters a commit. `guard_secrets` honors no
  bypass at all (GATES.md), and this is a strengthening: a `git commit` can
  only commit its own index, so today's umbrella-index scan sees nothing
  relevant to a sibling-repo commit and lets its staged secrets through (SM-8).

#### Group E - the gate stamp

- **FR-RSE-22** - **`gates.status` gains an additive `trees` map.**
  `{"status", "ran_at", "work_hash", "gates", "trees": {key: hash}, "checksum"}`.
  `work_hash` keeps its exact meaning (the project root's fingerprint), so a
  single-repo stamp is byte-identical apart from a `trees` map holding exactly
  `{".": <same hash>}`. `CHECKSUM_SALT` is NOT bumped: the checksum is computed
  over whatever payload the stamp carries, so an existing stamp written before
  this change still verifies and is read as covering `"."` only (BR-RSE-06).

- **FR-RSE-23** - **`gate_stamp.py` discovers the trees it must fingerprint.**
  `--results` fingerprints the project root plus every tree in the DISCOVERY
  SET: (a) every immediate child directory of the project root that carries a
  `.git` entry, skipping dot-directories and `company/`; (b) every directory
  under `<root>/.claude/worktrees/` that carries a `.git` entry; (c) every
  distinct tree named in the ledger's `self_authored` records. Discovery is
  filesystem-only. A tree that discovery misses simply has no fingerprint, so a
  commit into it BLOCKS (FR-RSE-07) - the miss direction is safe, and the
  recipe is in the block message (FR-RSE-27). `--check` gains an optional
  `--tree <dir>` that checks one tree's coverage.

- **FR-RSE-24** - **`run-gates.sh` splits the state root from the run
  directory.** `PROJECT_ROOT` (config, stamper, `company/state`) keeps today's
  resolution order verbatim. A new `RUN_DIR` is the git toplevel of the current
  working directory when that toplevel differs from `PROJECT_ROOT` and lies
  under it, else `PROJECT_ROOT`. Gate commands execute in `RUN_DIR`; the
  banner prints both when they differ. In every single-repo, non-worktree
  session `RUN_DIR == PROJECT_ROOT` and the script is byte-identical in
  behavior and output.
  _Why this is required, not optional:_ without it, a lead running the suite
  from `.claude/worktrees/x` gates the MAIN checkout, and stamping a
  fingerprint for the worktree would then be a false green - a stamp claiming
  gates passed for a tree the gates never ran in. That is the exact failure
  class this spec exists to prevent.

- **FR-RSE-25** - **`stop_gate` is NOT tree-scoped.** It keeps
  `check_stamp(root)`. At Stop there is no thing being acted on, and the gate
  suite is configured once at the umbrella, so "are the company's gates green"
  is honestly a root-level question. The residual (a red sibling tree does not
  block Stop through `stop_gate`) is covered by Mode D's dirty-plus-audit check
  and is recorded as RISK-RSE-05. Stated as an FR so the non-change is
  deliberate and reviewable.

#### Group F - visibility

- **FR-RSE-26** - **`tree=` in the log, only when it means something.** Every
  BLOCK, BYPASS, GRANT, SCOPE, AUDIT, and DISPATCH line produced while the
  resolved tree key is not `"."` carries a trailing ` tree=<key>` in its
  `reason` column. When the key IS `"."`, no segment is added anywhere. This is
  what makes SM-1 (byte-identical single-repo `adherence.log`) provable while
  still satisfying BR-RSE-10.

- **FR-RSE-27** - **block messages name the tree and carry the recipe.**
  `MODE_C_MSG` and the Mode D reason gain a `<tree>` substitution rendered only
  when the key is not `"."`. The new stamp-coverage block from FR-RSE-07 reads:
  the tree that has no fingerprint, and the recipe - run `bash
  company/run-gates.sh` with that tree as the working directory, which both
  gates it and fingerprints it.
  _Invariant protected:_ when a hook blocks, its message is a recipe the
  blocked agent follows (METHOD.md). "Gates are stale" without naming the tree
  is not a recipe in a polyrepo.

#### Group G - doctrine, witnesses, tests

- **FR-RSE-28** - **doctrine.** `company/GATES.md` and `company/METHOD.md` gain
  one short "enforcement scope" statement: tree facts are computed against the
  working tree containing the thing being acted on; task facts and all of
  `company/state/` are global to the company. Wording stays generic and must
  read correctly in a plain single-repo install, where the working tree and the
  project root are the same directory (the dual-nature rule). `company/GIT.md`
  and `ORCHESTRATOR.md` gain the new lead obligation from FR-RSE-24: run the
  gate suite from the worktree you are committing in. `docs/glossary.md` gains
  `working tree` and `tree key`. `company/gates.config` is NOT touched and
  keeps its CONFIGURE-ME placeholders.

- **FR-RSE-29** - **witnesses**, added via
  `python3 .claude/hooks/witness_check.py --add` only, never by hand-editing
  `company/witnesses.json`: (a) a `must_contain` on `_common.py` for the
  "never walks above root" guard in `working_tree`, because that line is what
  stops a parent repo becoming an enforcement scope; (b) a `must_contain` on
  `guard_provenance.py` for the ALL-over-trees quantifier in `fresh_audit`,
  because a regression to ANY is a false green; (c) a `must_contain` on
  `guard_commit.py` for the `effective_git_dir` call feeding the branch check.

- **FR-RSE-30** - **WORRIES bookkeeping.** The two P1 rows (umbrella dirty
  check; worktree agents cannot commit) and the `git -C` P3 row graduate OUT of
  `company/state/WORRIES.md` when this ships, per the file's own rule. One row
  is added per named residual risk (RISK-RSE-01 through RISK-RSE-07).

- **FR-RSE-31** - **tests.** New: `tests/hooks/test_working_tree.py` (resolver
  table), `tests/hooks/test_repo_scope_parity.py` (SM-1 goldens and the SM-2
  subprocess count), `tests/hooks/test_umbrella_scope.py` (SM-3, SM-4, SM-7,
  SM-8), `tests/hooks/test_worktree_commit.py` (SM-5),
  `tests/hooks/test_stamp_trees.py` (SM-6). A shared fixture builder makes a
  real two-repo umbrella and a real linked worktree with `git init` /
  `git worktree add`, because a mocked tree would prove nothing about git's
  own resolution. NO existing test file is edited (SM-1); if one must be, the
  PR body calls it out line by line and the reviewer treats it as a defect
  report. Every new `tests/**/test_*.sh` file, if any, is named explicitly in
  `.github/workflows/ci.yml` - the `WORRIES.md` P3 row about invisible test
  files applies directly to this build.

### Business rules and validations

- **BR-RSE-01** - **the single-repo identity rule (the acceptance bar).** In an
  install where the project root is itself a git working tree and no acted-on
  path resolves to a different tree, every hook produces byte-identical exit
  code, stdout, stderr, and `adherence.log` line before and after this change,
  and spawns no additional subprocess. Behavior may differ ONLY when the
  acted-on path, or a resolved effective git directory, resolves to a working
  tree that is not the project root. Any FR whose decision differs in a
  single-repo install is a defect, not a design choice. Mechanically: every
  scoped helper has `tree=None` as its default and that default path is the
  old body verbatim, and `tree_key(root, root) == "."` gates every message and
  log addition.

- **BR-RSE-02** - **the fact-classification rule.** Every fact the enforcement
  system reads is classified once, here. The construction rule is
  GLOBAL-unless-justified: a fact becomes PER-TREE only when git itself cannot
  answer it across repository boundaries, or when scoping it strictly increases
  what is checked.

  | # | Fact | Scope | Resolved from | Why |
  |---|---|---|---|---|
  | 1 | dirty source paths | PER-TREE | the acted-on path (Mode C: the commit's tree; Mode D: the session tree set) | `git status` cannot report across repository boundaries at all; today's umbrella answer is a category error, not a wide answer |
  | 2 | `work_hash` | PER-TREE (parameterized, defaults to root) | the tree being fingerprinted | it is literally a fingerprint of one repository's HEAD, status, and diffs |
  | 3 | current branch | PER-TREE | `effective_git_dir` of the git command | a branch is a property of one working tree; two worktrees of one repo are on two branches at once |
  | 4 | gate stamp FILE location | GLOBAL | `<root>/company/state/gates.status` | one company, one state directory; N stamp files would be N things to keep in sync and a new install surface |
  | 5 | gate stamp freshness AT COMMIT | PER-TREE | the commit's tree, via the stamp's `trees` map | there is a tree being written, and a fingerprint of a different tree is not evidence about it (#37) |
  | 6 | gate stamp freshness AT STOP | GLOBAL | the project root | there is no thing being acted on, and the gate suite is configured once at the umbrella (FR-RSE-25) |
  | 7 | staged-index secrets scan | PER-TREE | the commit's tree | a commit can only commit its own index; the umbrella index says nothing about it, so scoping strictly increases what is caught |
  | 8 | ledger `audits` (the records) | GLOBAL list | `company/state/provenance-ledger.json` | one company keeps one audit history |
  | 9 | audit COVERAGE | PER-TREE | the record's `trees` map, ALL-quantified | an audit that read repo A is not evidence about repo B; ANY here would be the false green this change must not create |
  | 10 | ledger `self_authored` | GLOBAL list, PER-TREE tagged | Mode A, tagged with `working_tree` of the edited file | it is the company's record of unaudited authorship; the tag is what lets Mode D scope without inventing session state |
  | 11 | ledger `dispatches` | GLOBAL (per-slug, unchanged) | the spawn payload | a dispatch is an act of the company, not of a tree; a lead dispatched once does not need to dispatch again per repo |
  | 12 | ledger `nudge_state` | GLOBAL (per-slug, unchanged) | as today | the nudge names a task slug, not a tree |
  | 13 | `active-task.json` and every entry field (`brief`, `type`, `test_scope`, `execution`, `issues`) | GLOBAL | `<root>/company/state/` | one `company/` is one company; a task legitimately spans repos, and scoping any of these would let an edit in a sibling repo escape the brief and the execution decision |
  | 14 | all of `company/state/` (adherence.log, costs.log, ledger, STATUS, WORRIES) | GLOBAL | `<root>/company/state/` | see 13; this is the answer to "where does state live" and it does not move |
  | 15 | `company/provenance.json` manifest | GLOBAL | `<root>/company/` | the rollout switch is a company-level switch |
  | 16 | gate CONFIG (`company/gates.config`) | GLOBAL | `<root>/company/` | one suite is the company's definition of done; per-tree suites are a separate product decision (OQ-RSE-11) |
  | 17 | gate EXECUTION directory | PER-TREE | the cwd's toplevel, via `run-gates.sh` `RUN_DIR` | gating the wrong tree is how a false green is manufactured (FR-RSE-24) |
  | 18 | `pr_mode` (origin remote) | GLOBAL | the project root | it is a rollout switch for the company; per-tree resolution could arm or disarm the tracking gate in either direction, so it is left alone (OQ-RSE-08) |
  | 19 | frozen surfaces, `is_source`, `rel_path` rendering | GLOBAL, relative to the project root | as today | they are path patterns over the company's tree, and paths in messages must stay comparable across repos |

- **BR-RSE-03** - **the monotonicity rule (the central check, restated for
  this change).** Narrowing what counts as dirty, stale, or protected converts
  BLOCKs into ALLOWs. That is the direction that silently disarms a gate, so
  every scoping decision is checked against this rule and lands in exactly one
  of three buckets.

  **ACCEPTED narrowings.** Each is safe for a stated structural reason, and
  each is made visible in `adherence.log`.

  | ID | Narrowing | Why it is safe | How it is visible |
  |---|---|---|---|
  | N-1 | Mode C's dirty check goes from the umbrella to the commit's tree (FR-RSE-13) | a commit writes exactly one working tree; dirty source in a repo this commit cannot touch is not evidence about this commit | the BLOCK / BYPASS line carries `tree=<key>`; the message names the tree and its paths |
  | N-2 | Mode D's dirty check goes from the umbrella to the session tree set (FR-RSE-15) | the set is FLOORED by the session cwd's tree and extended by every tree the company recorded authorship in, so it can only omit a tree that neither this session sits in nor anyone edited through Edit/Write | a SCOPE line naming the tree set is written on every non-default Stop (FR-RSE-16) |
  | N-3 | `guard_commit`'s branch check and Mode C's worktree exemption move from the payload cwd to the effective git directory (FR-RSE-11, FR-RSE-13) | the payload cwd is the harness's answer and is provably wrong for dispatched agents; the effective git directory is parsed from exactly the tokens git will honor (BR-RSE-08) | the line carries `tree=<key>` whenever the judged tree is not the project root |
  | N-4 | `guard_secrets` scans the commit's index instead of the umbrella index (FR-RSE-21) | a commit can only commit its own index, so this removes no real coverage and adds coverage the umbrella scan never had | unchanged block line; SM-8 asserts the added coverage |

  **STRENGTHENINGS** (ALLOW to BLOCK, no justification owed, but each needs a
  test so nobody "fixes" it later): per-tree stamp coverage (FR-RSE-07),
  ALL-over-trees audit coverage (FR-RSE-18), `git -C` command recognition
  (FR-RSE-09), sibling-index secret scanning (FR-RSE-21).

  **FORBIDDEN narrowings.** A PR containing any of these fails review:
  1. Scoping any task fact by tree (row 13 of BR-RSE-02) - `guard_spec`,
     `guard_tests`, `guard_models`, `stop_gate`'s entry logic, Mode B, or Mode
     E's tracking / execution / dispatch checks.
  2. Letting a green stamp for tree A authorize a commit in tree B.
  3. Making `fresh_audit` ANY over trees instead of ALL.
  4. Any resolution failure that yields an EMPTY scope. Every failure path
     substitutes the project root (BR-RSE-05).
  5. Removing the session-cwd FLOOR from `session_tree_set`, which would let a
     session with an empty `self_authored` list check nothing at Stop.
  6. Adding a tree to the stamp's `trees` map by any route other than a gate
     run that actually executed in that tree.

- **BR-RSE-04** - **the resolution rule, exhaustively.** `working_tree(path,
  root)` answers this table and never raises:

  | Input condition | Result |
  |---|---|
  | `path` under `root`, nearest `.git` ancestor is `root` | `root` (the single-repo case, zero cost) |
  | `path` under `root`, nearest `.git` ancestor is `<root>/repo-b` | `<root>/repo-b` |
  | `path` under `<root>/.claude/worktrees/x` (a `.git` FILE) | `<root>/.claude/worktrees/x` |
  | `path` under a submodule (a `.git` FILE) | the submodule directory |
  | `path` does not exist yet | resolved from its nearest EXISTING ancestor directory |
  | `path` exists but no `.git` at or below `root` on its chain | `root` (today's scope) |
  | `root` itself is not inside any git repository | `root`; every consumer's `_git` call then returns None and the caller keeps today's fail-open answer |
  | git is not installed | irrelevant to resolution (FR-RSE-02); consumers keep today's `no-git` and None fallbacks |
  | `path` is empty, or outside `root` | `root` |
  | a `.git` ancestor exists ABOVE `root` | ignored - the walk stops at `root` |

- **BR-RSE-05** - **the fail-open rule, and where it could become a silent
  allow.** Hooks fail open by design (`except: sys.exit(0)`), so the danger is
  a new code path whose failure yields "nothing to check". Three sites are
  named and closed:
  1. `working_tree` returning None or "" would make `dirty_source_paths` scan
     the process cwd. Closed by FR-RSE-01: the function has no failure mode
     that returns anything but a directory, and its floor is `root`.
  2. `effective_git_dir` returning a nonexistent or non-repo directory would
     make `current_branch` return None, which today means "fail open, allow".
     Closed by FR-RSE-10 step 5: a nonexistent directory falls back to the
     payload cwd, so the branch answer is today's answer.
  3. `session_tree_set` returning `[]` would make Mode D check nothing at all.
     Closed by the FLOOR in FR-RSE-14: the list always contains at least the
     session cwd's tree. A test asserts `session_tree_set(...) != []` for every
     fixture including an empty ledger, an unreadable ledger, and a payload
     with no cwd.
  This is the same discipline FR-MST-03 applied to the removed `active_task`:
  a plausible-looking failure inside a `try` must not become an allow.

- **BR-RSE-06** - **the stamp coverage rule.** A stamp speaks only for the
  trees it fingerprints. `work_hash` covers `"."`; `trees[k]` covers `k`; a
  stamp with no `trees` map covers `"."` only. Absent coverage is treated as
  STALE, which blocks. Nothing may write a `trees` entry except a gate run that
  executed in that tree.

- **BR-RSE-07** - **the audit coverage rule.** An audit record covers the tree
  keys in its `trees` map, or `"."` alone if it has none. `fresh_audit` over a
  set of trees is ALL-quantified. One auditor pass over one tree at one hash
  still covers every task entry's changes in that tree - the multi-session
  rule (FR-MST-14) is unchanged; it is extended along the tree axis only.

- **BR-RSE-08** - **the command-parse rule.** The effective git directory is
  derived only from tokens git itself will act on (`-C`, and a leading
  `cd <dir>` in a preceding segment of the same command). Any form the parser
  cannot resolve exactly falls back to the payload cwd. The parser is
  anti-accident, not anti-adversary, consistent with the existing
  `CHECKSUM_SALT` posture; RISK-RSE-03 records the adversarial residual.

- **BR-RSE-09** - **the task-fact rule.** Task facts and `company/state/` are
  global to the company and are never tree-scoped. One `company/` governs N
  repos; a brief may own directories in several of them; an entry's
  `execution` decision, `test_scope` grant, and `issues` list apply wherever
  the work lands.

- **BR-RSE-10** - **the naming rule.** Any decision made against a tree whose
  key is not `"."` names that tree in `adherence.log` and in its human message.
  Any decision made against the project root names nothing new, so single-repo
  output is unchanged.

- **BR-RSE-11** - **the performance rule.** Tree resolution costs zero
  subprocesses (FR-RSE-02). Per event: at most one filesystem walk of depth `d`
  for a path-bearing event; at most one walk per distinct directory in the
  session tree set at Stop; results memoized for the life of the process. The
  only added git subprocesses are the per-tree `status` / fingerprint calls in
  the multi-tree case, which are bounded by the size of the session tree set
  and are zero in a single-repo install (SM-2). No gate decision derives from a
  count or a threshold - the discovery depth in FR-RSE-23 is a discovery rule
  whose miss direction is BLOCK, not a magic number in a decision.

### Scope

**In:**

- `_common`: `working_tree`, `tree_key`, `scope_dir`, `reset_tree_cache`, the
  `tree` keyword on `work_hash` and `check_stamp`, and the single home for
  `segments` / `git_subcmd` / `effective_git_dir`.
- `git_subcmd` option-argument consumption, so `git -C x commit` is recognized
  by every Bash gate.
- `guard_commit`: effective git directory for the branch check, the bare-push
  check, and the per-tree stamp check.
- `guard_provenance`: `dirty_source_paths(tree)`, Mode C scoping and its
  worktree exemption, `session_tree_set`, Mode D scoping and its SCOPE line,
  `self_authored` tree tagging, audit `trees` map, `fresh_audit` /
  `staleness_reason` over a tree set.
- `guard_secrets`: staged-index scan in the commit's tree.
- `gate_stamp.py`: the `trees` map, discovery, `--check --tree`.
- `run-gates.sh`: `RUN_DIR` split from `PROJECT_ROOT`.
- Doctrine, glossary, three witnesses, WORRIES bookkeeping.
- Tests: resolver table, single-repo parity goldens plus a subprocess count,
  umbrella fixture, worktree fixture, stamp-coverage fixture, and one
  "a second tree must not disarm gate X" test per unscoped gate.

**Out (explicit - each of these prevents a helpful expansion):**

- **Per-tree `company/state/`.** State stays umbrella-global (BR-RSE-02 row
  14). No per-repo ledger, task list, adherence log, or cost log.
- **Per-tree `active-task.json` entries or a `tree` field on an entry.** Task
  facts are global (BR-RSE-09). An entry that names a tree would immediately
  invite tree-scoped brief and execution checks, which are forbidden.
- **Per-tree gate CONFIG or per-tree gate suites.** One `gates.config` at the
  umbrella. What a gate suite means in a polyrepo is a product decision, not a
  scoping fix (OQ-RSE-11).
- **Per-tree stamp FILES.** One `gates.status` with a `trees` map.
- **Session-keyed state, session leases, locks, or any use of `session_id`**
  beyond today's `cost_capture` log column. The multi-session spec scoped this
  out and this spec does not reopen it - which is exactly why Mode D scopes
  from the ledger plus a floor rather than from a session footprint.
- **Pruning `self_authored`** when a path becomes clean (OQ-RSE-04). The list
  stays append-only, which over-scopes Mode D, which is the safe direction.
- **Tree-scoping `guard_spec`, `guard_tests`, `guard_models`, `stop_gate`'s
  entry logic, `guard_frozen`, `no_slop`, `context_pin`, `session_start`,
  `cost_capture`, `risk_score`, `trace_check`, `witness_check`, or
  `gates_detect`.** None of them is touched.
- **Tree-scoping `pr_mode`** (OQ-RSE-08).
- **Honoring `GIT_DIR`, `GIT_WORK_TREE`, or `GIT_CEILING_DIRECTORIES`**, or
  detecting bare repositories (OQ-RSE-02).
- **Parsing `pushd`, subshells, variables, or command substitution** to find
  the effective git directory (BR-RSE-08).
- **Anti-adversarial hardening**, including detecting a `git init` used to
  carve dirty files out of scope (RISK-RSE-03).
- **Any installer or updater change.** No new shipped file, no new state file,
  no pack-list change.
- **Real gate commands in `company/gates.config`.** The dual-nature rule
  stands; the tracked config keeps its CONFIGURE-ME placeholders.

### UX notes

The only surfaces a human sees are hook messages, `adherence.log`, and the gate
runner's banner.

- **Single-repo install:** nothing changes. No new message text, no new log
  segment, no new banner line. This is the loudest UX requirement in the spec.
- **Block messages** gain the tree only when it is not the project root, and
  always as a prefix on paths (`repo-b/src/x.ts`) plus a named tree in the
  reason line, so a reader never has to guess which repo is dirty.
- **The stamp-coverage block** is a recipe: it names the tree with no
  fingerprint and the one command that fixes it (run the gate suite with that
  tree as the working directory).
- **The SCOPE line** at Stop is the audit trail for the one narrowing that has
  no other visible artifact. Format:
  `<ts> | guard_provenance | SCOPE | .+repo-b | stop-gate scope`.
- **The gate runner banner** prints `Running gates from <RUN_DIR>` as today,
  and adds `(state in <PROJECT_ROOT>)` only when the two differ.
- **Empty state:** an install with no git at all behaves exactly as today -
  every tree resolves to the project root, every `_git` call returns None, and
  every fail-open path is the one that shipped.

## Part 2 - Build readiness (the bridge from PRD to buildable)

- **Owned files (one workstream, one tech lead):**
  - `.claude/hooks/_common.py` - resolver, keys, scope dir, `work_hash` and
    `check_stamp` tree kwargs, the single command parser
  - `.claude/hooks/guard_commit.py` - effective git directory, branch check,
    stamp check, `git_cwd` removal
  - `.claude/hooks/guard_provenance.py` - dirty scoping, Modes C and D,
    `session_tree_set`, ledger tree tagging, audit coverage
  - `.claude/hooks/guard_secrets.py` - staged scan directory, parser
    de-duplication
  - `.claude/hooks/gate_stamp.py` - `trees` map, discovery, `--tree`
  - `company/run-gates.sh` - `RUN_DIR`
  - Doctrine: `company/GATES.md`, `company/METHOD.md`, `company/GIT.md`,
    `ORCHESTRATOR.md`, `docs/glossary.md`
  - State: `company/state/WORRIES.md`; `company/witnesses.json` ONLY via
    `witness_check.py --add`
  - Tests: `tests/hooks/test_working_tree.py`,
    `tests/hooks/test_repo_scope_parity.py`,
    `tests/hooks/test_umbrella_scope.py`,
    `tests/hooks/test_worktree_commit.py`,
    `tests/hooks/test_stamp_trees.py` (all new); `.github/workflows/ci.yml`
    only if a new `.sh` suite is added
  - Explicitly NOT owned and not to be edited: every other file under
    `.claude/hooks/`, every existing file under `tests/hooks/`, `install.sh`,
    `update.sh`, `lib/`, `bin/`, `package.json`, `company/gates.config`.

  Disjointness: the only in-flight item is the v0.2.6 release close-out
  (`chore/v0.2.6-closeout`), which touches `company/state/` bookkeeping and
  `.github/workflows/`. It must be merged or tagged before this branches;
  otherwise the WORRIES edits collide. No other workstream is open.

- **Invariants in play:**
  - Python 3.8 stdlib only in every hook; hooks fail OPEN on internal error;
    `witness_check.py` and `trace_check.py` stay loud and are untouched.
  - The fail-open surface is where a scoping bug becomes a silent allow -
    three named sites, closed in BR-RSE-05.
  - Dual-nature rule (CLAUDE.md): `company/` ships verbatim, so all doctrine
    wording reads correctly in a single-repo install; `company/gates.config`
    keeps its CONFIGURE-ME placeholders; the two suites that gate THIS repo run
    directly (`python3 -m unittest discover -s tests/hooks -q`, `npm test`).
  - Witness registry is checksum-sealed and mutated only via the CLI.
  - Accepted ADRs are immutable; none is edited here.
  - `no_slop` on all writing: straight quotes, ' - ', three dots, no filler.
  - Principled enforcement, no magic numbers: no gate decision derives from a
    count or threshold. The one depth-shaped rule (stamp tree discovery,
    FR-RSE-23) is a discovery rule whose miss direction is BLOCK.
  - Low-token per-turn injection: `context_pin` is not touched and gains no
    tree line.
  - Multi-session invariants from the shipped spec stand: BR-MST-02 (N==1
    identity), BR-MST-03 (fact classification along the task axis), BR-MST-04
    (monotonicity). This spec extends BR-MST-03 along a second axis and
    restates BR-MST-04 as BR-RSE-03; it contradicts neither.
  - Commit discipline: conventional subject, `Task: repo-scoped-enforcement`
    trailer, explicit staged paths, work on the task branch.

- **Frozen surfaces touched:** None, and no CR is required.
  `company/frozen-surfaces.json` has an empty `surfaces` list. Its `always`
  list covers machine-written state including `company/state/gates.status` and
  `company/state/provenance-ledger.json`, which `guard_frozen` blocks for the
  `Edit` and `Write` TOOLS only; this build writes both through Python
  (`os.replace`, `json.dump`) and the tests write them through Python, so no
  path in this build is blocked. Confirm with a read of
  `company/frozen-surfaces.json` before the first commit; if `surfaces` has
  become non-empty since this spec was written, file a CR rather than patching.

- **Data model impact:** three additive, forward-only JSON changes, all read
  through defaulting accessors, none migrating a file on disk.
  1. `company/state/gates.status`: `+trees: {key: hash}`. A stamp without it is
     valid and covers `"."` only. `CHECKSUM_SALT` is NOT bumped (FR-RSE-22).
  2. `company/state/provenance-ledger.json` audit records: `+trees: {key:
     hash}`. A record without it covers `"."` only. Ledger stays version 2 - no
     v3 bump, because nothing is removed or reinterpreted.
  3. `company/state/provenance-ledger.json` `self_authored` records: `+tree:
     key`. A record without it reads as `"."`. `path` stays project-root
     relative.
  No database, no columns, no external migration, no install or update step.

- **Contracts impact:**
  - `_common` module API - ADDED: `working_tree`, `tree_key`, `scope_dir`,
    `reset_tree_cache`, `segments`, `git_subcmd`, `effective_git_dir`.
    CHANGED (additive keyword, back-compatible): `work_hash(root, tree=None)`,
    `check_stamp(root, tree=None)`. Consumers are this repo's hooks and tests
    only.
  - `guard_commit` - REMOVED: `git_cwd` (replaced by
    `_common.effective_git_dir`); MOVED OUT: `segments`, `git_subcmd`.
    `guard_provenance` :811-812 is the only external caller and migrates in the
    same commit. A grep test fails on any residual `guard_commit.segments`,
    `guard_commit.git_subcmd`, or `git_cwd(`.
  - `guard_secrets` - its private copies of `segments` / `git_subcmd` are
    deleted in favor of the `_common` ones. Three copies becoming one is a
    prerequisite for the `-C` fix applying uniformly.
  - `guard_provenance` - `dirty_source_paths(root, tree=None)`,
    `fresh_audit(root, ledger, trees=None)`,
    `staleness_reason(root, ledger, trees=None)`: additive keywords, existing
    call shapes unchanged. `read_ledger` / `write_ledger` shapes unchanged.
  - `gate_stamp.py` - `--check` gains `--tree`. `--results` output text
    unchanged.
  - `run-gates.sh` - output gains one conditional banner segment; exit codes
    and the ladder are unchanged.
  - Hook message strings gain conditional `<tree>` substitutions that render
    empty at the project root, so no existing message assertion changes.
  - No new shipped file and no pack-list change: every touched shipped path is
    already covered by `package.json` `files`; `tests/` is not packed and
    `company/specs/**` is excluded.

- **Named risks:**

  - **RISK-RSE-01 (the riskiest assumption in this spec) - Mode D's tree set
    can miss a tree.** Source written by Bash (a heredoc, `sed -i`, a
    generator) into a tree that is neither the session cwd's tree nor named in
    `self_authored` is invisible to Mode D. Today the umbrella check would
    catch it.
    _Why accepted:_ the alternative that catches it is the umbrella scan, which
    is the P1 being fixed and which is unusable in the field. The floor (the
    session cwd's tree) plus the ledger tags cover every path the enforcement
    layer has ever seen, and the Bash-written-source hole already exists
    upstream - Mode A and Mode E do not see Bash writes either, so this widens
    a known hole rather than opening a new class.
    _Mitigation:_ the SCOPE line (FR-RSE-16) makes every Stop-time scope
    readable after the fact; a WORRIES row carries the escalation, which is to
    add a PreToolUse Bash path extractor that records redirect and `-o` targets
    into `self_authored`.

  - **RISK-RSE-02 - `cd` parse divergence.** A command whose effective
    directory the parser resolves differently from the shell would judge the
    wrong branch or the wrong tree.
    _Why accepted:_ the parser resolves only exact `cd <one-token>` segments
    and `-C <dir>`, and abandons to the payload cwd on anything else, so a
    divergence requires a parse bug rather than a crafted command.
    _Mitigation:_ a table-driven parser test covering `cd a && git commit`,
    `cd a && cd b && git commit`, `cd /abs && git commit`,
    `git -C b commit`, `cd a && git -C b commit`, `cd $X && git commit`,
    `cd && git commit`, `cd -`, quoted paths with spaces, and
    `echo cd x; git commit`.

  - **RISK-RSE-03 - an adversarial `git init` carves files out of scope.** An
    agent could run `git init` in a subdirectory to make its dirty files a
    separate working tree that Mode C's commit-tree scope no longer sees.
    _Why accepted:_ hooks are anti-accident, not anti-adversary - the same
    posture the checksum salt is documented under. An agent willing to do this
    can already write files with Bash to avoid Mode A entirely.
    _Mitigation:_ WORRIES row only.

  - **RISK-RSE-04 (friction, not weakness) - leads must now run gates in their
    worktree.** With FR-RSE-24 and FR-RSE-07, a commit from
    `.claude/worktrees/x` requires a stamp fingerprint for that tree, which
    requires the gate suite to have run there. Delegated builds that today run
    the suite from the main checkout will start blocking.
    _Why accepted:_ today they are gating the wrong tree, which is a false
    green; blocking is the correct new behavior.
    _Mitigation:_ FR-RSE-28 puts the obligation in `company/GIT.md` and
    `ORCHESTRATOR.md`; FR-RSE-27 makes the block message the recipe.

  - **RISK-RSE-05 - `stop_gate` stays root-scoped.** A red or unfingerprinted
    sibling tree does not block Stop through `stop_gate` (FR-RSE-25).
    _Why accepted:_ at Stop there is no acted-on thing, and the gate suite is
    umbrella-configured; Mode D's dirty-plus-audit check covers unverified work
    in sibling trees.
    _Mitigation:_ WORRIES row; escalation is to extend `stop_gate` to require
    coverage for the session tree set, which is a four-line change once
    `session_tree_set` exists.

  - **RISK-RSE-06 - the `git -C` fix surfaces new blocks in the field.**
    Commands that previously slipped past `guard_commit`, `guard_secrets`, and
    Mode C will now be gated on the first release that carries this.
    _Why accepted:_ they were never meant to slip; this is the P3 WORRIES row
    graduating.
    _Mitigation:_ named in the release notes for the target version so a field
    report is diagnosed as intended behavior.

  - **RISK-RSE-07 - stamp tree discovery can miss a deeply nested repo.**
    Discovery covers depth-1 children, `.claude/worktrees/*`, and trees named
    in `self_authored`. A first commit into a repo missed by all three blocks
    with no fingerprint.
    _Why accepted:_ the miss direction is BLOCK, and the recipe is reachable -
    edit one file in that tree through Edit or Write, then run the suite, and
    discovery picks it up on the next stamp.
    _Mitigation:_ FR-RSE-27's message states that recipe explicitly.

- **Open questions and chosen fallbacks:** every OQ has ONE decided fallback
  that every agent implements and tags `# OQ-RSE-NN assumption` in Python (or
  `// OQ-RSE-NN assumption` elsewhere). None blocks the build.

  - **OQ-RSE-01**: What is a tree's stable key in logs, messages, and the
    stamp? FALLBACK: **`"."` for the project root; otherwise the tree's path
    relative to the project root with forward slashes; otherwise the absolute
    path when the tree is not under the project root.** Keys are compared as
    strings and are never normalized further, so a relocated umbrella
    invalidates its stamp entries, which is the safe direction.
  - **OQ-RSE-02**: Should resolution confirm the walk with
    `git rev-parse --show-toplevel`? FALLBACK: **no.** The walk is the answer
    (FR-RSE-02). If review finds the walk insufficient, add ONE memoized
    confirming call whose failure substitutes the walk's answer and whose
    absence of a `.git` ancestor substitutes the project root - never an empty
    scope.
  - **OQ-RSE-03**: What does the Stop hook scope to, given it has no path?
    FALLBACK: **the session tree set - the working tree of the session cwd
    (always present, the floor) union the working tree of every
    `self_authored` record in the ledger** (FR-RSE-14). Rejected alternatives
    and why: the session cwd alone drops trees the session edited through a
    subagent path and is the narrowest option; the union of trees touched
    during THIS session needs session-keyed state, which is out of scope; every
    tree carrying an active task entry needs a `tree` field on entries, which
    BR-RSE-09 forbids; the umbrella as today is the bug.
  - **OQ-RSE-04**: Should `self_authored` records be pruned once their path is
    clean, so Mode D's scope shrinks back? FALLBACK: **no pruning this pass.**
    The list stays append-only; the scope over-includes trees the company once
    edited, which is the safe direction. Escalation if the sticky scope bites:
    prune at `write_ledger` when the path is neither dirty nor untracked in its
    tree.
  - **OQ-RSE-05**: How much shell does the effective-git-directory parser
    understand? FALLBACK: **exact `cd <one-token>` segments applied
    cumulatively, plus `-C <dir>` on the git invocation; every other form
    abandons to the payload cwd** (FR-RSE-10, BR-RSE-08). No `pushd`, no
    variables, no substitution, no subshells.
  - **OQ-RSE-06**: Does `git -C x commit` now count as a commit for every Bash
    gate? FALLBACK: **yes** - `git_subcmd` consumes option arguments
    (FR-RSE-09). This arms gates that today miss the command entirely and
    graduates the P3 WORRIES row.
  - **OQ-RSE-07**: Which trees does a Mode B-post audit record claim to cover?
    FALLBACK: **the session tree set at the moment the audit is recorded**,
    written as a `trees` map; a record with no map covers `"."` only. The
    auditor is not asked to declare its scope, because a self-declared scope is
    exactly the kind of self-grading METHOD.md forbids.
  - **OQ-RSE-08**: Does `pr_mode` (the origin-remote rollout switch) become
    per-tree? FALLBACK: **no, it stays at the project root.** It gates
    FR-DE-15 tracking, which is a task fact; per-tree resolution could arm or
    disarm that gate in either direction, and neither direction is justified by
    this change.
  - **OQ-RSE-09**: Does `guard_frozen` resolve its patterns per tree?
    FALLBACK: **no.** Frozen-surface patterns are project-root relative and
    stay so; a sibling repo's file matches only if its project-root-relative
    path matches. Unchanged behavior.
  - **OQ-RSE-10**: What happens when the project root is not itself a git
    repository and no sibling `.git` exists on an acted-on path's chain?
    FALLBACK: **the tree is the project root**, every `_git` call returns None,
    and every consumer keeps today's fail-open answer (`work_hash` returns
    `no-git`, `dirty_source_paths` returns `[]`, `current_branch` returns
    None). No new behavior.
  - **OQ-RSE-11** (owner-facing, business-policy flavored): Is a polyrepo
    umbrella install a SUPPORTED, documented configuration of claude-company,
    with the promises that implies (docs, installer support, per-tree gate
    configuration on the roadmap)? This is a product-promise question, not an
    engineering one. FALLBACK: **supported for enforcement scoping only** -
    the hooks resolve trees correctly, `company/state` and `gates.config`
    remain single and umbrella-level, the installer is unchanged, and
    `docs/glossary.md` documents the scoping without a marketing claim.
    Recorded for `company/state/DECISIONS.md` as an owner item to confirm or
    veto at delivery; the build does not wait on it and a veto costs only a
    wording edit.
  - **OQ-RSE-12** (owner-facing): Does this ship in 0.2.6 as dispatched, or in
    0.2.7? `STATUS.md` records v0.2.6 as PREPARED and awaiting the owner's tag,
    and `WORRIES.md` names 0.2.7 as the candidate. FALLBACK: **ship in the next
    unreleased minor - do not reopen a tagged release.** If v0.2.6 is still
    untagged when this merges, it lands there; otherwise 0.2.7. Recorded for
    `DECISIONS.md`; nothing in the build depends on the answer.

- **Verification plan:** each FR is proven by a named, executable check. Gate
  ladder first, all green before any commit per CLAUDE.md:
  `python3 -m unittest discover -s tests/hooks -q`, `npm test`,
  `bash tests/install/run_tests.sh`, `bash tests/install/test_update.sh`.

  - **FR-RSE-01, FR-RSE-04, FR-RSE-05, BR-RSE-04**:
    `tests/hooks/test_working_tree.py` drives every row of the BR-RSE-04 table
    against real `git init` fixtures (plain repo, nested repo, linked worktree
    via `git worktree add`, submodule-shaped `.git` file, nonexistent path,
    path outside root, `.git` above root) and asserts the exact returned
    directory and `tree_key`.
  - **FR-RSE-02, FR-RSE-03, SM-2**: a test that monkeypatches
    `_common._git` to record every invocation, runs each hook against a
    single-repo fixture, and asserts zero calls carrying `rev-parse
    --show-toplevel` and no increase in total `_git` calls versus the golden;
    plus a memoization test asserting one walk per distinct directory.
  - **FR-RSE-06, FR-RSE-07, BR-RSE-06**: `tests/hooks/test_stamp_trees.py` -
    `check_stamp(root)` and `check_stamp(root, root)` return identical tuples
    for green / red / stale / tampered / missing stamps; a stamp with no
    `trees` map plus a sibling tree returns the no-fingerprint reason; a stamp
    with a matching `trees` entry returns `(True, "green")`; a stamp with a
    stale `trees` entry returns the stale reason.
  - **FR-RSE-08, FR-RSE-09, OQ-RSE-06**: a parser table asserting
    `git_subcmd("git -C x commit -m y") == ("commit", ["-m", "y"])`, the same
    for `--git-dir=`, `--work-tree`, `-c user.name=x`, and that plain
    `git commit` is unchanged; plus a grep test failing on any residual
    `guard_commit.segments`, `guard_commit.git_subcmd`, `git_cwd(`, or a second
    copy of the parser under `.claude/hooks/`.
  - **FR-RSE-10, RISK-RSE-02, OQ-RSE-05**: the ten-case parser table named in
    RISK-RSE-02, asserting the exact resolved directory for each.
  - **FR-RSE-11, SM-5**: `tests/hooks/test_worktree_commit.py` - payload cwd on
    `main`, worktree on `task/x`; `cd .claude/worktrees/x && git commit`
    allowed with a `tree=` log segment; bare `git commit` blocked with today's
    exact message text (byte-compared against the golden); `git -C
    .claude/worktrees/x commit` allowed; a `cd` into a nonexistent directory
    blocked (falls back to the payload cwd).
  - **FR-RSE-12, FR-RSE-13, SM-4**: `tests/hooks/test_umbrella_scope.py` -
    root `R` plus sibling `B`; commit in `B` with `B` dirty and no audit exits
    2 naming `B` and `B`'s paths; commit in `B` with `B` clean and `R` dirty
    exits 0; commit in `R` with `R` dirty exits 2 with today's exact message
    (no `tree=` segment).
  - **FR-RSE-14, BR-RSE-05**: `session_tree_set` returns a non-empty list for
    an empty ledger, an unreadable ledger, a payload with no cwd, and a payload
    whose cwd is outside the project root; and returns exactly `[root]` in a
    single-repo fixture.
  - **FR-RSE-15, SM-3**: Stop with `B` dirty and unaudited but the session in
    `R` and `self_authored` empty exits 0 with no decision printed; the same
    with one `self_authored` record tagged `B` blocks; the same with `R` dirty
    blocks with today's exact reason text.
  - **FR-RSE-16**: the SCOPE line is present with the exact expected key list
    when the tree set is not `[root]`, and absent in a single-repo fixture.
  - **FR-RSE-17, FR-RSE-18, FR-RSE-19, BR-RSE-07**: a legacy audit record with
    only a scalar `work_hash` satisfies a single-tree query and does NOT
    satisfy a two-tree query; an audit covering `{".", "repo-b"}` satisfies
    both; an audit covering only `repo-b` fails a query including `"."` with
    reason `audit does not cover .`; a `do-not-ship` verdict still fails.
  - **FR-RSE-20, SM-7**: for `guard_spec`, `guard_tests`, `guard_models`,
    `stop_gate`, Mode A, Mode B-pre, and Mode E, a test that runs the identical
    blocking fixture in a two-tree umbrella with the acted-on path inside the
    sibling tree and asserts the SAME block, the same exit code, and the same
    message.
  - **FR-RSE-21, SM-8**: a staged secret in `B` committed from `B` exits 2; the
    identical fixture in a single repo exits 2 with byte-identical output.
  - **FR-RSE-22, FR-RSE-23**: a stamp written in a single-repo fixture is
    byte-identical to the golden except for `trees: {".": <same hash>}` and its
    checksum; a stamp written in an umbrella fingerprints the sibling and the
    worktree; a pre-change stamp still verifies and is read as covering `"."`;
    `--check --tree` exits 0 and 1 correctly.
  - **FR-RSE-24**: `run-gates.sh` run from a worktree executes the gate command
    in the worktree (proved with a gate command that prints `pwd`), writes the
    stamp under `PROJECT_ROOT`, and prints both roots; run from a single-repo
    root, its stdout is byte-identical to the golden.
  - **FR-RSE-25**: `stop_gate` output is byte-identical in a single-repo and a
    two-tree fixture with the same stamp state.
  - **FR-RSE-26, FR-RSE-27, BR-RSE-10**: a grep-style assertion that no
    `adherence.log` line produced in any single-repo fixture contains `tree=`,
    and that every umbrella-fixture block line does; message golden comparison
    for the two new message shapes.
  - **BR-RSE-01, SM-1**: `tests/hooks/test_repo_scope_parity.py` -
    goldens for every hook and every event captured at the merge base by
    `tests/hooks/make_repo_scope_goldens.sh` and committed under
    `tests/hooks/goldens/`; each case asserts identical exit code, stdout,
    stderr, and appended `adherence.log` line. Plus the standing assertion that
    `git diff --stat` over `tests/hooks/` shows only ADDED files.
  - **BR-RSE-02**: an inventory test asserting the PER-TREE call sites are
    exactly the ones named in the table - `dirty_source_paths`, `work_hash`
    with a tree, `check_stamp` with a tree, `current_branch` from the effective
    git directory, the `guard_secrets` staged scan - and that no other hook
    imports `working_tree`.
  - **BR-RSE-03**: the FORBIDDEN list is checked by SM-7's per-gate tests plus
    the FR-RSE-18 ALL test plus the FR-RSE-14 non-empty test; the PR body
    states, per accepted narrowing, which test proves its log visibility.
  - **BR-RSE-11**: covered by SM-2's subprocess count.
  - **FR-RSE-28**: `no_slop`-clean read of every doctrine edit; a test
    asserting the scope sentence is present in the shipped doctrine files and
    contains no polyrepo-only phrasing that would read wrong in a single-repo
    install.
  - **FR-RSE-29**: `python3 .claude/hooks/witness_check.py` green with the
    three new witnesses; registry checksum valid.
  - **FR-RSE-30**: the two P1 rows and the `git -C` P3 row are gone from
    `WORRIES.md`; one row per RISK-RSE-NN is present.
  - **FR-RSE-31, SM-9**: the four suites green, and every new `.sh` suite (if
    any) named explicitly in `.github/workflows/ci.yml`.
  - **Live end-to-end check on this repo before the delivery report** (evidence
    for the report, not a substitute for tests): create a scratch umbrella with
    this repo plus a second `git init` sibling; confirm a dirty sibling does not
    block Stop, that a commit in the sibling does, and that a worktree commit
    is judged by the worktree's branch.

## Options considered

Divergence ran 16 candidate directions across six pattern categories:
assumption challenge (the mandatory one), inversion, SCAMPER, constraint
variation, perspective multiplication, analogical transfer, and extreme
scaling. The top-level shape (the enforcement unit is the working tree
containing the acted-on thing) was owner-decided in the dispatch and is not
reopened; the divergence was run to test whether the decided shape survives the
alternatives and to surface the requirements they imply.

It produced five things this spec would not otherwise contain. The inversion
pass ("how would we guarantee a gate silently disarms?") produced the FORBIDDEN
list in BR-RSE-03, the ALL-over-trees quantifier in FR-RSE-18, and the
never-empty-scope rule in BR-RSE-05 - the three answers were: scope by
something the agent controls, let one tree's evidence speak for another, and
fail open to nothing. The constraint-variation pass ("zero new dependencies,
zero new subprocesses") produced the filesystem walk in FR-RSE-02, which
removed the entire `git rev-parse` failure surface the dispatch asked me to
handle. Analogical transfer (build systems resolve a target's workspace from
the nearest marker file above it) confirmed the same mechanism. The
support-engineer perspective produced BR-RSE-10 and the SCOPE line. The
assumption challenge on "the scope must be a directory-shaped thing at all"
produced Option 2 below, which is the strongest rejected option.

Notable non-survivors, briefly: declare the repo list in `company/gates.config`
(config the owner maintains, and drift is a silent narrowing - it also
collides with the dual-nature CONFIGURE-ME rule); per-tree `company/state/`
directories (N ledgers, N task lists, and the one-company model is the
product); per-tree `gates.status` files (a new shipped file surface per repo
for a fact that fits in one map); scope everything per-tree unless proven
global (the reverse default silently splits task facts); drop the dirty check
entirely and rely on the ledger (adopted as Mode D's scope INPUT, rejected as
the whole mechanism); and do nothing, which leaves the umbrella unusable and
#37's false green in place.

| # | Option | Reasoning | Production risks | Trade-offs |
|---|---|---|---|---|
| 1 | **Resolve the tree from the acted-on path or command; keep `company/state` and every task fact global; carry per-tree fingerprints inside the one stamp file** | The acted-on thing always exists for the events that matter (a path for Edit/Write, an effective git directory for a Bash commit), so the scope is derived rather than declared - nothing for an owner to configure and nothing to drift. Task facts stay where the multi-session spec put them, so the two specs compose along orthogonal axes rather than fighting. The resolver is a filesystem walk with a hard floor at the project root, so it has no failure mode that yields an empty scope. In a single-repo install every resolution returns the project root and the change is provably invisible. | Stop has no acted-on thing, so its scope is inferred (RISK-RSE-01) - the one place the design is weaker than the rest. The `cd` parser is a second inference surface (RISK-RSE-02). Per-tree stamping adds a discovery rule that can miss deeply nested repos (RISK-RSE-07). | Five files of hook change plus the gate runner; the compatibility risk concentrates in one 20-line resolver that is independently reviewable as a pure function with a table test. |
| 2 | **Per-path session footprint: enforce over the exact paths this session edited, with no tree concept at all** | It is the theoretically correct scope for Mode C and Mode D both - the gate asks "did YOU leave unaudited work", and the honest answer is the set of paths this session authored, which the ledger already half-records. It needs no tree resolution, no `cd` parsing, no stamp format change, and it makes RISK-RSE-01's hole structural rather than accidental. | Requires session-keyed state to distinguish "this session" from "the company", which the multi-session spec deliberately scoped out and which reintroduces the lifecycle problem it rejected (a crashed session's footprint has no owner). Misses every Bash-written file, and unlike Option 1 it has no tree-wide backstop to catch them. Says nothing about the branch check or the stamp, so both P1s and #37 would need a separate mechanism anyway. | Best scope precision, worst coverage and worst fit with shipped doctrine. |
| 3 | **One claude-company install per repository; no umbrella enforcement at all** | Every fact becomes honest by construction with zero new code - each install's project root IS its working tree, so the bug cannot exist. No resolver, no narrowing, no monotonicity risk, and it needs no spec beyond documentation. | N gate suites, N ledgers, N task lists, and N sets of state for one CEO running one program across the repos - the cross-repo coordination the product exists to provide is deleted. A task spanning two repos has no home. The worktree P1 is untouched, because a worktree is a second working tree of the SAME install. | Zero implementation risk in exchange for abandoning the polyrepo client. |

**Winner: Option 1.** It is the only survivor that fixes all three defects with
one concept, keeps the single-repo install provably unchanged, needs nothing
from the owner to configure, and composes with the shipped multi-session
semantics instead of contradicting them. It is also the only one where the
riskiest part (the Stop scope) is isolated to one helper with a floor, so the
residual is bounded and auditable rather than diffuse.

**Strongest rejected option: Option 2 (per-path session footprint).** It wins
on the exact question Option 1 is weakest at - the Stop scope - and it wins
decisively: a footprint of authored paths is what Mode D is actually asking
about, and Option 1's tree set is a proxy for it. It lost on three things.
Session-keyed state was scoped out by the shipped multi-session spec for
lifecycle reasons that have not changed. It has no backstop: where Option 1
falls back to a whole tree, Option 2 falls back to nothing, so its failure mode
is a silent allow rather than extra friction. And it answers only one of the
three defects, leaving the branch check and the stamp needing Option 1 anyway.
If RISK-RSE-01 bites in the field, reopen this - but reopen it in the cheaper
order: first record Bash-written paths into `self_authored` (which improves
Option 1's tree set for free), and only then consider a session-keyed
footprint.

## Spec-ready checklist (the Phase 0 gate)

- [x] **Every FR has a stable ID and at least one acceptance criterion.**
  FR-RSE-01 through FR-RSE-31, each mapped to a named executable check in the
  Verification plan; US-RSE-1 through US-RSE-7 and SM-1 through SM-9 carry the
  given/when/then form.
- [x] **Out-of-scope is explicit.** Thirteen exclusions in Scope > Out,
  including every rejected mechanism (per-tree state, per-tree gate config,
  per-tree stamp files, session-keyed state, `pr_mode` scoping, git env-var
  handling, shell parsing beyond `cd` and `-C`, anti-adversarial hardening,
  installer changes).
- [x] **Every open question has a single decided fallback.** OQ-RSE-01 through
  OQ-RSE-12, each with one fallback a builder implements without asking.
  OQ-RSE-11 and OQ-RSE-12 are the owner-facing pair and are recorded for
  `DECISIONS.md`; both fallbacks let the build proceed and a veto on either
  costs only a wording or a version-label edit.
- [x] **Owned directories are named and disjoint from other in-flight work.**
  Named in Part 2, with an explicit not-owned list. The v0.2.6 close-out branch
  must merge or tag first; it is the only other in-flight item and it touches
  `company/state/` bookkeeping.
- [x] **Frozen-surface needs are identified and CRs filed.** None touched, no
  CR required: `surfaces` is empty, and the `always` entries this build writes
  (`gates.status`, `provenance-ledger.json`) are written by Python, not by the
  `Edit` / `Write` tools `guard_frozen` intercepts. Re-confirmed by reading
  `company/frozen-surfaces.json` before the first commit.
- [x] **Data/contract impact stated.** Three additive JSON fields, all
  defaulted on read, no file migrated, no version bump, no salt bump;
  `_common` gains six functions and two keyword arguments; `guard_commit`
  loses `git_cwd`, `segments`, and `git_subcmd` to `_common`; `guard_secrets`
  loses its copies; one new CLI flag; no pack-list change.
- [x] **Verification plan covers every FR.** One named executable check per FR
  and per BR, plus the nine SM signals and the live end-to-end check.

Prerequisite to confirm before branching: `company/frozen-surfaces.json` still
has an empty `surfaces` list, and the v0.2.6 close-out is merged. If either is
false, the build does not start.

## Part 3 - Brief handoff

Derive one brief with `company/templates/BRIEF-TEMPLATE.md`; the brief links
this spec and does not embed it. One workstream, one tech lead.

Read-first for the builder: the project `CLAUDE.md` (dual-nature rule, the two
gate suites, commit discipline), `company/METHOD.md`,
`.claude/hooks/_common.py`, `.claude/hooks/guard_provenance.py` (Modes C and D
and the ledger helpers), `.claude/hooks/guard_commit.py`,
`.claude/hooks/guard_secrets.py`, `.claude/hooks/gate_stamp.py`,
`company/run-gates.sh`, `company/frozen-surfaces.json`, and
`tests/hooks/test_v1_v2_parity.py` (the golden-comparison idiom this build
reuses).

### Commit bands (one per tracking issue, ascending blast radius)

1. **Resolver and one command parser - no semantic change.**
   `_common.working_tree`, `tree_key`, `scope_dir`, `reset_tree_cache`; the
   `tree=None` keyword on `work_hash` and `check_stamp` with the default path
   byte-identical; `segments` / `git_subcmd` / `effective_git_dir` consolidated
   into `_common` with the option-argument fix; `guard_commit`,
   `guard_secrets`, and `guard_provenance` migrated to the single copy. Every
   existing test passes untouched. FR-RSE-01 to FR-RSE-10, BR-RSE-04,
   BR-RSE-05, BR-RSE-08, BR-RSE-11. The compatibility risk lives here.

2. **Commit-tree scoping - closes the worktree-commit P1.**
   `guard_commit` branch check, bare-push check, and worktree exemption on the
   effective git directory; Mode C scoping and its exemption; `guard_secrets`
   staged scan. FR-RSE-11, FR-RSE-12, FR-RSE-13, FR-RSE-21, plus the FR-RSE-26
   log segment. Verifiable on its own against SM-4, SM-5, SM-8.

3. **Stop scoping and ledger tree tagging - closes the umbrella dirty P1.**
   `session_tree_set`, Mode D scoping, the SCOPE line, `self_authored` tree
   tags, audit `trees` maps, `fresh_audit` and `staleness_reason` over a tree
   set. FR-RSE-14 to FR-RSE-20, BR-RSE-07. **This band alone fixes the reported
   P1** and should be verifiable independently against SM-3 and SM-7.

4. **Per-tree gate stamp - closes #37.** `gates.status` `trees` map,
   `gate_stamp.py` discovery and `--tree`, `run-gates.sh` `RUN_DIR`,
   `guard_commit`'s per-tree stamp call, the coverage block message.
   FR-RSE-07 (its multi-tree half), FR-RSE-22 to FR-RSE-25, FR-RSE-27,
   BR-RSE-06. Deliberately last and independently revertible: bands 1 to 3
   close both P1s without it, and this band is the one that adds new blocking
   behavior for existing delegated builds (RISK-RSE-04).

5. **Doctrine, witnesses, WORRIES, docs, and the parity goldens.**
   FR-RSE-28 to FR-RSE-31, BR-RSE-01, BR-RSE-02, BR-RSE-03. The goldens are
   generated at the merge base and committed at the start of band 1; this band
   is where the final comparison, the doctrine text, and the WORRIES
   graduation land.

Gates for this repo: `python3 -m unittest discover -s tests/hooks -q` and
`npm test`, both green before any commit, plus
`bash tests/install/run_tests.sh` and `bash tests/install/test_update.sh`.
No CR is required.
