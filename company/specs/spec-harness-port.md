# SPEC: harness port (DevMesh fork -> upstream)

_Type: program. Author: product-manager. Date: 2026-08-13._
_Status: SPEC-READY._
_Slug: `harness-port`. Target release: 0.2.7._
_Source catalog: `/Users/redomic/Documents/Projects/DevMesh/company/harness-changes-2026-08-12.md`._
_Reference implementation (NOT a specification): `/Users/redomic/Documents/Projects/DevMesh/.claude/hooks/`._
_This spec is the requirements source of record. `company/state/harness-port-checklist.md` is the CEO's status board and cites these FR IDs; it is not edited from here._

The spec is rich and human-facing; it can be long. The builder agent NEVER
reads it - it reads the brief derived from it. Reference, do not embed.

## Part 1 - Product requirements

### Problem

The DevMesh fork ran this harness under real load for a week - four to five
concurrent Claude Code sessions in one checkout, a polyrepo umbrella, a
4-minute test suite - and the load exposed defects that this repo's own usage
never surfaces. Three classes of them:

1. **Guards that can be walked around or that fire on the wrong evidence.**
   `guard_commit.git_subcmd` reads `git -C x commit` as the subcommand `x`, so
   every Bash-gated commit check is skipped by a form of the command agents
   type routinely; `guard_secrets` carries a duplicate of that same parser, so
   the escape also bypasses the staged-secret scan. `guard_spec.is_source`
   exempts any path containing a `company/`, `docs/`, `.claude/` or `.github/`
   segment ANYWHERE, so `app/company/x.py` and `src/docs/y.py` are ungated
   source. `guard_provenance` decides an audit's verdict with a substring test,
   so an auditor report that merely NAMES the verdict vocabulary is recorded as
   a failure. That last one has already cost this repo four blocked commits
   against passing audits (WORRIES P1, raised from P3 on evidence).

2. **State that loses writes under concurrency.** Every shared state file
   (provenance ledger, witness registry, cost cursor, gate stamp) is
   read-modify-written with no lock and written non-atomically. Under
   concurrent sessions DevMesh saw dispatch credits vanish (producing false
   "delegated but no dispatch" blocks), torn task-file reads produce false "no
   active brief" blocks, and torn stamp reads produce false "malformed stamp"
   merge blocks. Upstream is one release away from recommending parallel
   sessions to users; the state layer still assumes one.

3. **Ceremony that costs more than the work.** Freshness fingerprints history
   position, so committing audited work stales the audit that covered it and
   staging a file stales it again (WORRIES P2). A green gate ladder emits
   roughly 2,600 transcript lines that every later turn of that session re-reads
   as cache. `stop_gate` reads every active entry and checks ONE global stamp,
   so with N concurrent sessions any session's stale tree blocks every other
   session at every turn end, with a recipe that tells the wrong session to fix
   work it does not own.

What it costs today: false blocks that consume real dispatches, a verification
tail measured in hours, and - the expensive one - a CEO that starts routing
around the harness. The v0.2.6 close-out records a 4,791-line feature touching
every enforcement hook that no auditor ever read, because the trigger never
armed and nobody noticed.

The DevMesh fork fixed these and measured the result. This program ports the
verified fixes back, minus the parts that are true only for a polyrepo working
copy and false for a single-repo product that ships to strangers.

### Goal and success metrics

Binary, checkable at integration:

- G1. `git -C <dir> commit` is gated exactly as `git commit` is, and the same
  parse is used by the secrets scan (one parser, one behavior).
- G2. An auditor report that names SHIP / SHIP-WITH-FIXES / HALT in prose is
  never recorded as a failing verdict; a labeled `Verdict:` line is.
- G3. Two concurrent processes performing a ledger, witness or cost-cursor
  read-modify-write lose zero updates in a repeated race test.
- G4. Committing audited work, and merging a content-identical branch, leave a
  green stamp green and a fresh audit fresh.
- G5. A fully green ladder run emits at most 60 transcript lines, and every
  gate's full output is retrievable at `company/state/gate-output/<gate>.log`.
- G6. `guard_models.py --check` turns red when any shipped enforcement hook is
  missing from `.claude/settings.json` wiring.
- G7. With two gating entries active and one stale tree, `stop_gate` does not
  block the other session's turn end.
- G8. A ladder run started from a worktree gates and stamps THAT worktree, not
  the main checkout.
- G9. Every FR in this spec is implemented, tested, or explicitly deferred at
  the traceability gate, and both suites plus CI are green on integrated main.

Non-metric that decides nothing but is worth recording at close-out: the wall
clock of a no-change re-verification pass, before and after.

### Users and personas

| Persona | Posture | What changes for them |
|---|---|---|
| The CEO session (main checkout) | Full tool access, hook-gated | Fewer false blocks, a quiet ladder, freshness that survives a commit |
| A dispatched lead or developer (worktree) | Owns its directories only | Its dispatch credit stops vanishing under concurrency; its brief gating stops failing open on a torn read |
| The auditor | Read-only, no Edit/Write | Verifies the stamp instead of duplicating the ladder; gains a delta-scoped re-audit mode and a vocabulary that cannot poison the ledger |
| The owner | Client, not operator | Sees three parked decisions batched into DECISIONS.md, not asked mid-build |
| A field install (a stranger's repo on npm) | Inherits every hook verbatim | Inherits the fixes on `claude-company update`; inherits stricter `is_source` behavior, which is a deliberate behavior change worth a release note |

### Options considered

_Patterns used (company/IDEATION.md): assumption challenge (10), perspective
multiplication (1), constraint variation (3), inversion (5)._

Full divergence, 14 directions:

| # | Direction | Reasoning | Production risks | Trade-offs |
|---|---|---|---|---|
| 1 | Merge the fork's `.claude/hooks/` wholesale | Fastest; the fork is a superset and is proven under load | Imports polyrepo assumptions and one false-green generator (see below); imports a model-tiering veto violation | Zero adaptation cost, unbounded correctness cost |
| 2 | Do not port; make the fork upstream | Removes a whole class of drift permanently | The fork is a working copy with project-specific gates, agents and a conda toolchain; it is not a shippable product | Kills the product to save a merge |
| 3 | Port the doctrine only, leave the hooks alone | Cheapest; catalog says speed disciplines are prose anyway | Leaves every guard escape and every lost write in place | Buys habits, not correctness |
| 4 | Port the code only, doctrine later | Hooks are the enforcement; prose is the narration | Auditor vocabulary and parser must ship as a PAIR or the negative verdict stops recording | Splits a coupled change across releases |
| 5 | Attacker lens: port only the guard-escape fixes (`git -C`, `is_source`) | Smallest diff that closes real holes | Leaves the false blocks that are actively costing dispatches | Correct but under-scoped |
| 6 | Support lens: port only the false-block eliminations (verdict parser, torn reads, stop_gate) | Attacks the failure that costs the most today | Leaves the escapes open; leaves concurrency losses | Under-scoped in the other direction |
| 7 | CFO lens: port only the token and time savings (content hash, quiet-pass) | Largest measured saving per line changed | Content hashing without the lock layer makes concurrent staleness races more likely, not less | Optimizes the thing that is not broken first |
| 8 | Scale lens: land the concurrency layer alone in 0.2.7, everything else in 0.2.8 | Mandatory before recommending parallel sessions; self-contained | Two releases of churn through the same files; the verdict parser keeps costing dispatches for another cycle | Safe and slow |
| 9 | Zero-new-mechanism constraint: only modify existing functions, add no new file, no new gate | Minimal review surface, no install-path changes | Forfeits the wiring assertion, which is the one change that prevents the drift class DevMesh actually hit | Cheap, and forecloses the best idea |
| 10 | Reversibility constraint: every change behind a manifest flag | Field installs can turn any of it off | Flags are waivers with a nicer name; DECISIONS #5 rejected exactly this shape of knob twice | Adds a permanent surface to maintain |
| 11 | Assumption challenge: the fork's `HASH_EXCLUDES` (drop `*.md`, `*.txt`) is a saving here too | It is a large part of the fork's measured win | FALSE here: markdown IS this product. Agent definitions, skills, COMPANY.md and doctrine are gated by no_slop, trace_check and guard_models. Excluding prose would let a doctrine rewrite stale nothing | Would import a false-green |
| 12 | Assumption challenge: keep `stop_gate` as-is and delete it instead (the fork's answer) | Removes the multi-session block entirely | Deletion removes the only check on three paths `guard_commit` cannot see: a session that edits and never commits, a session that commits green then edits more, and closing an entry with red gates | Cures the symptom by removing the organ |
| 13 | Inversion: design for "how would we ship a false green or a silent bypass", read as a checklist | Surfaces the traps in the source material rather than trusting it | Not a plan on its own | Becomes the review discipline layered on whichever plan wins |
| 14 | Six workstreams, two waves, each item adapted on its merits against upstream's single-repo product posture | Keeps the proven wins, rejects the polyrepo-shaped ones item by item; wave 1 is file-disjoint and wave 2 depends only on wave 1's kernel | Largest coordination surface of the candidates; two lanes convert BLOCKs into ALLOWs and need independent reads | Highest value, highest process cost |

Survivors:

| # | Option | Reasoning (why it could win) | Production risks | Trade-offs |
|---|---|---|---|---|
| 14 | Six-workstream adapted port, two waves | Everything the fork proved, minus what is only true for a polyrepo; wave 1 is file-disjoint so it parallelizes cleanly; the kernel lands first because every other lane leans on it | Two lanes (L2 verdict parser, L5 provenance scope) turn BLOCKs into ALLOWs - the monotonicity class that needs a spec and an independent read | Coordination cost, and a release note for the stricter `is_source` |
| 6 | Correctness-only port (false blocks + escapes), efficiency deferred | Smallest surface that stops the bleeding; no ceremony changes to argue about | Leaves the staleness cascade that produces the shortcuts the correctness fixes exist to prevent | Two releases through the same files |
| 8 | Concurrency layer alone | Mandatory before recommending parallel sessions; one lane, one reviewer | Ships the lock without the content hash it makes safe, and leaves the P1 verdict parser live for another cycle | Safe, slow, and leaves the loudest defect in place |

Scoring:

| # | Value | Prod risk | Build cost | Op cost | Reversible | Verdict |
|---|---|---|---|---|---|---|
| 14 | High | Medium (two monotonicity lanes, both gated by an auditor pass) | High | Low | Yes, per lane (each lane is one PR) | WINNER |
| 6 | Medium | Low | Medium | Low | Yes | Rejected |
| 8 | Low-Medium | Low | Low | Low | Yes | Rejected |

**Recommendation: option 14.** It is the only candidate that carries the
measured wins and refuses the fork's project-specific parts item by item. The
work decomposes into six file-disjoint owned surfaces, so the coordination cost
is real but bounded, and the two lanes that weaken a gate are named up front and
gated by an independent auditor read. The one risk to watch: `is_source`
anchoring makes previously-ungated paths gated in field installs, which will
produce new blocks in projects that have an `app/company/` or `src/docs/`
directory. That is the fix working, and it needs a release note.

**Strongest rejected option: #6, correctness-only.** It loses because the
efficiency defects are themselves a correctness risk. The staleness cascade is
what makes a CEO batch, skip, or route around verification - the v0.2.6
close-out has a 4,791-line feature that no auditor read - and the content hash
(L1) is the dependency the rest of the port leans on. If #6 keeps winning
arguments during the build, reopen this section.

**Decisions that are yours (owner):** the three parked items in "Out of scope"
below - merge-only gating, a risk-scaled audit band, and the Phase 0 spec-lite
rung. None is required for this program to land.

### User stories and acceptance criteria

- **US-HP-1:** As the CEO, I can commit audited work and merge a
  content-identical branch without re-running gates or re-dispatching the
  auditor.
  - AC: given a green stamp and a fresh audit at tree T, when the work is
    committed with no content change, then `gate_stamp.py --check` exits 0 and
    `guard_provenance` mode C allows the next commit at the same content.
- **US-HP-2:** As the CEO, I can run the gate ladder without flooding the
  transcript.
  - AC: given a ladder where every gate passes, when the runner finishes, then
    stdout carries at most 3 lines per gate plus a pointer line, and
    `company/state/gate-output/<gate>.log` holds each gate's full output.
- **US-HP-3:** As the CEO, I am never blocked at commit by an audit that
  actually passed.
  - AC: given an auditor response whose body contains the sentence "return
    SHIP, SHIP-WITH-FIXES or HALT" and a line `Verdict: SHIP`, when the
    PostToolUse hook records it, then the ledger verdict is `ship` and mode C
    allows the commit.
- **US-HP-4:** As a session sharing a checkout with others, my dispatch credits
  and witness rows survive concurrent writes.
  - AC: given two processes each appending a dispatch to the ledger
    concurrently, when both finish, then both dispatches are present.
- **US-HP-5:** As a session sharing a checkout, another session's stale tree
  does not end my turn with a block that names work I do not own.
  - AC: given two gating entries active and a stale stamp, when this session's
    turn ends, then `stop_gate` emits no block decision and writes one WARN
    line to `company/state/adherence.log`.
- **US-HP-6:** As the owner, an enforcement hook cannot quietly stop being
  wired while the doctrine still cites it.
  - AC: given `.claude/settings.json` with the Stop group's `stop_gate.py`
    command removed, when `guard_models.py --check` runs, then it exits 1 and
    names the missing binding.
- **US-HP-7:** As a delegated lead, main-checkout debris that I did not author
  does not demand an audit of my clean delegated build.
  - AC: given dirty source paths none of which appear in the ledger's
    `self_authored` list, when mode C evaluates a commit, then it allows and
    logs the reason.

### Functional requirements

Grouped by workstream so briefs derive cleanly. Every FR is independently
testable; each carries at least one falsifiable acceptance criterion.

Observability and logging changes, called out as a set because they are read
as one by the owner - four items, four FRs:

| # | Change | FR | Lane |
|---|---|---|---|
| 1 | `gates.log` - one append-only line per ladder run, the "where does the time go" record | FR-HP-22 (plus FR-HP-23 for the freeze and the ignore) | L3 |
| 2 | Quiet-pass runner - a passing gate prints its tail plus a pointer; a failing gate echoes everything; the full output is PRESERVED rather than deleted | FR-HP-20, FR-HP-21 | L3 |
| 3 | Slow-hash breadcrumb - `work_hash` calls over 1.5s leave a TIMING line | FR-HP-07 | L1 |
| 4 | Block-message ergonomics - the branch recipe warns that a compound `switch && commit` is judged against the CURRENT branch | FR-HP-17 | L2 |

#### L1 - kernel (`.claude/hooks/_common.py`)

- **FR-HP-01:** `_common.state_lock(root, timeout=2.0)` returns a context
  manager holding an exclusive `flock` on `company/state/.state.lock`, creating
  the directory and file when absent. It fails OPEN: on missing `fcntl`, on
  lock timeout, or on any internal error it yields WITHOUT the lock rather than
  raising or blocking. The descriptor is closed on exit, including on the
  exception path.
  - AC: two processes that each enter the lock, sleep 0.2s and exit take
    strictly more than 0.2s in total, proving serialization.
  - AC: with `fcntl` import forced to fail, the context still yields and the
    body still runs.
  - AC: raising inside the body releases the lock - a second acquisition
    immediately afterwards succeeds within the timeout.
- **FR-HP-02:** `_common` gains an atomic JSON write helper (`mkstemp` in the
  destination directory, write, `os.replace`) that every non-append state
  writer uses. On any write failure the temp file is removed and the original
  destination is left byte-unchanged.
  - AC: a reader that opens the destination in a loop while the helper writes a
    large payload 200 times never observes a partial or unparseable file.
  - AC: forcing `json.dump` to raise leaves the pre-existing destination
    content byte-identical and leaves no temp file behind in the directory.
- **FR-HP-03:** `active_tasks(root)` retries a torn read: when the file exists
  but does not parse, it re-reads up to 3 times with a 0.06s pause before
  giving up and returning `[]`.
  - AC: a file that is unparseable on the first read and valid on the second
    returns the parsed entries.
  - AC: a file that never parses still returns `[]` (today's fail-open) and the
    call returns in under 0.5s.
- **FR-HP-04:** `_common.active_tasks_unreadable(root)` returns True iff
  `company/state/active-task.json` EXISTS and does not parse, and False both
  when the file is absent and when it parses.
  - AC: all three cases asserted directly.
- **FR-HP-05:** `work_hash(root)` becomes CONTENT-based: it builds the git tree
  the working copy would commit as, in a THROWAWAY index (`GIT_INDEX_FILE` to a
  temp path, `read-tree HEAD` when HEAD exists, `add -A`, strip
  `HASH_EXCLUDES` from that index, `write-tree`), and returns `tree:<oid>`. The
  real index is never touched. On any git trouble it falls back to the legacy
  HEAD+status+diff+cached digest, and to `no-git` when git answers nothing.
  - AC: `git add` of an already-tracked unchanged file does not change the hash
    (closes the staging-stales-an-audit worry).
  - AC: committing the working tree with no content change does not change the
    hash.
  - AC: the repository's real `.git/index` mtime and content are unchanged
    across a `work_hash` call.
  - AC: a source edit DOES change the hash.
  - AC: with `git` unavailable on PATH the function returns `no-git` and does
    not raise.
- **FR-HP-06:** `HASH_EXCLUDES` is exactly `("company/state",)`. Prose is NOT
  excluded. The constant carries a comment stating why: markdown is the product
  in this repo (agent definitions, skills, COMPANY.md, doctrine) and
  `no_slop`, `trace_check` and `guard_models` all gate it, so excluding it
  would let a doctrine rewrite stale nothing.
  - AC: editing `COMPANY.md` changes `work_hash`.
  - AC: editing `.claude/agents/auditor.md` changes `work_hash`.
  - AC: writing `company/state/adherence.log` does NOT change `work_hash`.
- **FR-HP-07:** A `work_hash` call slower than `SLOW_HASH_SECONDS` (1.5) writes
  one TIMING line to the project's `company/state/adherence.log` naming the
  elapsed seconds and the threshold. Faster calls write nothing. The breadcrumb
  never raises and never changes the returned hash.
  - AC: with the implementation stubbed to sleep past the threshold, exactly
    one line matching `timing | SLOW` is appended; under the threshold, zero
    lines.
- **FR-HP-08:** `company/adr/ADR-0002-content-based-freshness.md` records the
  freshness-semantics change: what a work hash now means, why committing and
  content-identical merges no longer stale a stamp or an audit, and why prose
  stays inside the fingerprint here while the fork excludes it.
  - AC: the file exists, its status line reads `Status: accepted`, and it cites
    FR-HP-05 and FR-HP-06.

#### L2 - guards (`guard_commit.py`, `guard_secrets.py`, `guard_spec.py` is_source, `guard_provenance.py` verdict parsing)

- **FR-HP-10:** `guard_commit.git_subcmd` consumes the ARGUMENT of
  separated-argument git globals - `-C`, `-c`, `--git-dir`, `--work-tree`,
  `--namespace`, `--exec-path` - when scanning for the subcommand. Attached
  forms (`-Cdir`, `--git-dir=x`) consume one token only.
  REPRODUCED against current code on 2026-08-13, and this is the acceptance
  baseline: `git_subcmd("git -C sub commit -m x")` returns `('sub', ['commit',
  '-m', 'x'])`; `git_subcmd("git -c user.name=x commit")` returns
  `('user.name=x', ['commit'])`. It is WORSE than a commit-gate escape:
  `git_subcmd("git -C sub push origin main")` returns `('sub', ['push',
  'origin', 'main'])`, so the protected-branch PUSH check - the owner-only
  rule - is evaded by the same parse, as is every other Bash-gated check that
  keys on the subcommand (`guard_secrets`, `guard_provenance` mode C).
  - AC: `git -C x commit -m y` parses subcommand `commit`.
  - AC: `git -c user.name=z commit` parses `commit`.
  - AC: `git -C x push origin main` parses `push`, and the protected-branch
    push BLOCK fires for it.
  - AC: `git --git-dir=/tmp/g commit` parses `commit`.
  - AC: `git -C x` alone parses `(None, [])`.
  - AC: `git commit -C HEAD~1` (the `--reuse-message` form) still parses
    `commit`, not `HEAD~1`.
- **FR-HP-11:** The branch and stamp checks for a git segment carrying a global
  `-C <path>` are judged against THAT directory, not the project root. A
  relative path resolves against the payload cwd, falling back to root; only
  tokens BEFORE the subcommand are scanned; a path git cannot answer for falls
  back to the payload cwd, then root. ADAPTATION, beyond the dispatched line
  item: without it FR-HP-10 creates a NEW false block, because
  `git -C .claude/worktrees/<slug> commit` on a task branch would be judged
  against the main checkout's protected branch.
  - AC: with the main checkout on `main` and a worktree on `task/x`,
    `git -C .claude/worktrees/x commit -m y` is NOT blocked as a
    protected-branch commit.
  - AC: with the main checkout on `main`, a bare `git commit` is still blocked
    as a protected-branch commit while a non-hotfix entry is active.
- **FR-HP-12:** `guard_secrets` deletes its own copy of the git-segment parser
  and calls `guard_commit.git_subcmd`, so the two cannot diverge.
  - AC: `guard_secrets` source contains no second definition of the option-skip
    loop, and `git -C x commit` with a staged secret is BLOCKED by the secrets
    scan.
  - AC: monkeypatching `guard_commit.git_subcmd` changes what `guard_secrets`
    sees, proving delegation rather than duplication.
- **FR-HP-13:** `guard_spec.is_source` anchors the exempt-directory test to the
  FIRST path segment (`segs[0] in EXEMPT_DIRS`). The fork's `_SUBREPOS`
  depth-two rule is NOT ported.
  REPRODUCED against current code on 2026-08-13, and this is the acceptance
  baseline: `is_source("app/company/billing.py")`,
  `is_source("src/docs/handler.py")` and `is_source("pkg/.claude/x.py")` all
  return False. Those are ungated source today - no brief required
  (`guard_spec`), no execution decision required (`guard_provenance` mode E),
  and they never count as dirty source for the audit demand
  (`dirty_source_paths` filters through this same function).
  - AC: `app/company/billing.py` is source (True). Today it is False.
  - AC: `src/docs/handler.py` is source (True). Today it is False.
  - AC: `pkg/.claude/x.py` is source (True). Today it is False.
  - AC: `company/state/x.py`, `.claude/hooks/x.py`, `docs/x.py` and
    `.github/x.py` remain non-source (False).
  - AC: a root-level `service.py` remains source, and `README.md` remains
    non-source.
  - AC: no `_SUBREPOS` constant exists in the file.
- **FR-HP-14:** `guard_provenance.audit_verdict(text)` replaces the substring
  test. A labeled verdict line - a line whose leading non-word characters are
  followed by `verdict` (optionally `final verdict`), case-insensitive,
  carrying a verdict token - is authoritative; disagreeing labeled lines fail
  closed to the negative verdict. Without a labeled line, a token counts only
  when it is the SOLE verdict token present in the text. Anything ambiguous
  returns `unknown`, and `unknown` is treated as passing by `fresh_audit`,
  matching this hook's fail-open posture. The recognized tokens are
  `DO-NOT-SHIP`, `HALT`, `SHIP-WITH-FIXES`, `SHIP`; both `DO-NOT-SHIP` and
  `HALT` record the ledger verdict `do-not-ship` (the stored value does not
  change, so old ledgers keep working).
  - AC: `"Verdict: SHIP"` in a body that also contains the sentence "returns
    SHIP / SHIP-WITH-FIXES / HALT" records `ship`.
  - AC: `"Verdict: HALT"` records `do-not-ship`.
  - AC: `"Final verdict: DO-NOT-SHIP"` records `do-not-ship`.
  - AC: a body containing only the enumeration of all three tokens and no
    labeled line records `unknown`, and `fresh_audit` accepts it.
  - AC: a body with no labeled line and exactly one token, `SHIP-WITH-FIXES`,
    records `ship-with-fixes`.
  - AC: `SHIPPING` and `RESHIP` do not match the `SHIP` token.
- **FR-HP-15:** `guard_provenance.response_text(resp)` flattens a Task
  `tool_response` into text: strings pass through, lists and tuples join their
  flattened elements with newlines, dicts flatten their `text`, `content`,
  `result` and `output` values (falling back to `str(resp)` when none are
  present), and None becomes the empty string. Mode B-post classifies the
  verdict from this flattened text, not from `str(resp)`.
  - AC: `[{"type": "text", "text": "Verdict: SHIP\nfindings..."}]` yields text
    containing a real newline, and `audit_verdict` over it returns `ship`.
    Under `str()` the same input yields `\n` as two characters and the anchor
    fails - the test asserts the difference.
- **FR-HP-16:** The mode D (Stop) block reason names the offending
  self-authored dirty paths: the first 5 sorted paths plus a `(+N more)` count
  when there are more, introduced by wording that says the work may predate
  this session.
  - AC: with 7 self-authored dirty paths, the reason contains exactly 5 path
    strings and the text `(+2 more)`.
  - AC: with 0 self-authored dirty paths in the intersection, no path list is
    appended.
- **FR-HP-17:** Block-message ergonomics. `guard_commit`'s branch recipe tail
  warns that this gate judges EVERY segment of a compound command against the
  CURRENT branch, so the switch must run as its own command first:
  `git switch -c task/x && git commit` blocks even though the switch comes
  first. The warning sits in the shared tail, so it renders in both the
  one-entry and the many-entry recipe.
  - AC: the block message produced at one active entry contains the sentence
    naming the compound-command behavior and the `switch -c ... && git commit`
    example.
  - AC: the same sentence is present in the message produced at three active
    entries.
  - AC: `git switch -c task/x && git commit` on `main` with one non-hotfix
    entry still BLOCKS (the behavior is documented, not changed).

#### L3 - runner and wiring (`company/run-gates.sh`, `gate_stamp.py`, `guard_models.py`, `guard_frozen.py`, `company/frozen-surfaces.json`, `.gitignore`)

- **FR-HP-20:** `run-gates.sh` becomes quiet-pass. A PASSING gate prints the
  last 3 non-empty lines of its output plus one pointer line naming
  `company/state/gate-output/<gate>.log`. A FAILING gate echoes its entire
  output. The ladder table, the stamp step and the final exit code are
  unchanged. Note for the builder: today's runner writes the gate output to a
  temp file, `cat`s it in full, and then DELETES it (`rm -f "$OUT_FILE"`), so
  preserving that output is part of this change, not a side effect of it - the
  pointer line is worthless if the file it names is gone.
  - AC: a configured gate printing 500 lines and exiting 0 produces at most 5
    lines of runner stdout for that gate; the same gate exiting 1 produces at
    least 500.
  - AC: the runner's exit code is 0 with all gates green and 1 with any gate
    red, unchanged from today.
- **FR-HP-21:** Every gate's full output is written to
  `company/state/gate-output/<gate>.log`, replacing the previous run's file,
  for passing and failing gates alike. The directory is created when absent.
  - AC: after a run, the file exists for every gate and its content equals the
    gate command's combined stdout and stderr.
- **FR-HP-22:** The runner appends exactly one line per ladder run to
  `company/state/gates.log`: an ISO-8601 UTC timestamp
  (`YYYY-MM-DDTHH:MM:SSZ`), the total suite duration in seconds, the overall
  status, and one `NAME:RESULT:DURATION` field per gate in ladder order. This
  is the "where does the time go" record, and it answers that question without
  stdout scrollback. Nothing else writes this file - it is runner-only, the
  same single-writer rule the stamp has. A failure to append never changes the
  runner's exit code.
  - AC: three runs produce exactly three lines, in order, each naming every
    configured gate with its result and duration.
  - AC: the timestamp field of each line parses as ISO-8601 UTC.
  - AC: a red ladder writes `status=red`, a green one `status=green`.
  - AC: with `company/state` read-only, the ladder still exits with its gate
    result.
- **FR-HP-23:** `company/state/gates.log` and `company/state/gate-output/` are
  frozen and ignored: added to `guard_frozen.ALWAYS_DEFAULTS` (the hardcoded
  baseline that reaches existing installs on update), to the `always` list in
  `company/frozen-surfaces.json` (what a fresh install inherits), and to this
  repo's `.gitignore`.
  - AC: an Edit targeting `company/state/gates.log` is blocked by
    `guard_frozen` and logged, both with and without
    `company/frozen-surfaces.json` present.
  - AC: `git status --porcelain` is empty after a ladder run on an otherwise
    clean tree.
- **FR-HP-24:** `gate_stamp.write_stamp` writes `company/state/gates.status`
  atomically through the FR-HP-02 helper. A concurrent reader never sees a
  partial stamp.
  - AC: a reader loop calling `check_stamp` while 200 stamps are written never
    returns the reason `gates.status is malformed`.
- **FR-HP-25:** `guard_models.py --check` asserts the FULL expected hook
  wiring, not just the Task spawn hook. The expectation is a declarative table
  of `(event, tool matcher, hook filename)` rows in `guard_models.py`. A row is
  checked only when `.claude/hooks/<filename>` exists in the project, so an
  older install missing a newer hook is not failed for it. Only
  `.claude/settings.json` counts; `settings.local.json` is ignored. Extra hooks
  and extra groups are allowed. A missing binding exits 1 and prints every
  missing row plus the `claude-company update` fixit. RATIONALE recorded in the
  file: DevMesh un-wired a hook while its doctrine still cited that hook as a
  live integrity point, and no test caught it because the code never changed.
  This gate is the mechanical answer to that class of drift.
  - AC: with the shipped `.claude/settings.json`, `--check` exits 0.
  - AC: removing the `stop_gate.py` command from the Stop group makes `--check`
    exit 1 with a message naming `Stop` and `stop_gate.py`.
  - AC: removing the entire `PreToolUse` `Bash` group makes `--check` exit 1
    and name all of its expected hooks.
  - AC: deleting `.claude/hooks/guard_tests.py` from the project makes its rows
    unchecked rather than failing.
  - AC: adding an unrelated extra hook command to a group keeps `--check` at 0.
  - AC: the existing spawn-wiring assertion still fails as it does today
    (regression on the shipped behavior).
- **FR-HP-26:** The documentation of the runner changes is OWNED BY L6
  (FR-HP-62 for `company/GATES.md`, FR-HP-63 for `company/METHOD.md`), and L3
  changes no doctrine file. This FR exists to make the seam explicit so
  neither lane assumes the other did it.
  - AC: the L3 lane's ownership diff touches no file under `company/` except
    `company/run-gates.sh`, `company/frozen-surfaces.json` and its
    `company/change-requests/CR-2-*.md`.
- **FR-HP-27:** The change request freezing the two new state paths is filed
  and applied before the L3 lane merges: `company/change-requests/CR-2-*.md`
  covering `company/state/gates.log` and `company/state/gate-output/**`.
  - AC: the CR file exists, names both patterns, and is referenced in the L3
    report.
- **FR-HP-28 (CORRECTED 2026-08-13 by the CEO - the original text below the
  rule was IMPLEMENTED, FAILED CI, and was replaced. Do not build or document
  the superseded rule):** `run-gates.sh` resolves the project root from the
  RUNNER'S OWN LOCATION. The script always lives at
  `<root>/company/run-gates.sh`, so the root is the parent of the directory
  containing the script, resolved through symlinks, and accepted only when that
  containing directory is actually named `company`. Git is NOT consulted.
  `CLAUDE_PROJECT_DIR` and then `pwd` remain ordered fallbacks, reachable only
  when the script path cannot be resolved (piped stdin, `bash -c`).
  WHY THE FIRST ATTEMPT FAILED, recorded so nobody re-derives it: resolving
  from the cwd's git top level broke 13 tests in `tests/install/run_tests.sh`,
  which invokes the runner by ABSOLUTE PATH against a non-git fixture with
  `CLAUDE_PROJECT_DIR` pointed at that fixture while the cwd sits inside this
  repo. Resolving from the cwd gated this repo instead of the fixture and
  silently overrode an explicitly-named project directory. The three candidate
  rules answer different questions: the cwd answers "which tree am I standing
  in", and the cwd is incidental; `CLAUDE_PROJECT_DIR` answers "what did the
  harness say", and the harness lies inside a worktree, which was the original
  bug; the script location answers "which project's runner am I executing", and
  `gates.config`, `.claude/hooks` and `company/state` are all siblings of that
  script. The runner IS part of the project it gates - a structural invariant,
  not a heuristic. Verified safe by grepping every invocation in the repo: all
  are relative (`bash company/run-gates.sh`), none uses a harness-pinned
  absolute path, so a worktree run executes the worktree's own copy.
  ~~SUPERSEDED: resolves the project root from the WORKING TREE
  that actually contains the cwd (`git rev-parse --show-toplevel`), falling
  back to `CLAUDE_PROJECT_DIR` and then to `pwd`.~~ The harness pins `CLAUDE_PROJECT_DIR` to
  the MAIN checkout even for a subagent whose cwd is a worktree, so today a
  lead running the ladder from `.claude/worktrees/<slug>` gates and stamps
  SOMEBODY ELSE'S tree and receives a green stamp for code it did not build.
  This is a false-green fix and is strictly more correct, so it needs no owner
  decision. The resolved root must also reach the stamper: `gate_stamp.py`
  resolves its own root from `CLAUDE_PROJECT_DIR` or cwd, so the runner
  invokes it with `CLAUDE_PROJECT_DIR` set to the resolved root, or the stamp
  lands in the main checkout while the gates ran in the worktree - the exact
  false-green in a different place.
  - AC: run from a worktree at `.claude/worktrees/x` with
    `CLAUDE_PROJECT_DIR` pointing at the main checkout, the runner reads the
    worktree's `company/gates.config`, runs the gates from the worktree, and
    writes the stamp to the worktree's `company/state/gates.status`. The main
    checkout's stamp file is byte-unchanged.
  - AC: run from the main checkout with `CLAUDE_PROJECT_DIR` set, behavior is
    unchanged from today.
  - AC (CORRECTED): the installer-suite fixture shape works - a NON-git fixture
    directory holding only `company/run-gates.sh` and `company/gates.config`,
    invoked by absolute path with `CLAUDE_PROJECT_DIR` set to it while the cwd
    is inside a DIFFERENT git repo carrying a decoy gate, reads the fixture's
    config, never runs the decoy, and leaves the other repo unstamped. This is
    the exact case the superseded rule broke; it is the load-bearing AC.
  - AC: when the script path cannot be resolved (piped to `bash -s`, so `$0` is
    `bash`), the runner falls back to `CLAUDE_PROJECT_DIR`, and then to `pwd`
    when that is unset. The fallbacks must be reachable, not dead code - a
    confidently wrong root is worse than an honest fallback.
  - AC: the work hash written into the worktree stamp equals
    `work_hash(<worktree>)`, not `work_hash(<main checkout>)`.

#### L4 - state writers (`witness_check.py`, `cost_capture.py`, `guard_spec.py` torn read)

- **FR-HP-30:** `witness_check.py --add` and `--remove` perform the whole
  read-modify-write inside `state_lock`, and the registry is written through
  the FR-HP-02 atomic helper.
  - AC: two concurrent `--add` calls produce a registry containing BOTH rows
    with DISTINCT `W-NNN` ids, and the checksum validates.
  - AC: `--check` output on a single-writer registry is byte-identical to
    today's.
- **FR-HP-31:** `cost_capture` performs its cursor read-modify-write inside
  `state_lock` using a `with` block, and writes `.cost-cursor.json` through the
  atomic helper. It must NOT enter and exit the context manager manually - the
  fork does, which leaks the descriptor on the exception path.
  - AC: two concurrent stops for different session ids leave both cursor
    entries present.
  - AC: an exception raised inside the locked region releases the lock - a
    subsequent acquisition succeeds inside the timeout.
  - AC: the source contains no `__enter__(` or `__exit__(` call.
- **FR-HP-32:** `guard_spec` fails OPEN with a logged BYPASS when
  `active-task.json` exists but does not parse, instead of blocking with
  NO_BRIEF. The empty check stays FIRST (FR-MST-05 ordering is unchanged); the
  unreadable case is evaluated inside it.
  - AC: with an unparseable `active-task.json`, a source Edit is ALLOWED and
    one BYPASS line naming `active-task.json unreadable` is appended to
    `adherence.log`.
  - AC: with NO `active-task.json` at all, a source Edit is still BLOCKED with
    today's byte-identical NO_BRIEF message.
- **FR-HP-33:** Every remaining non-append state writer in the L4 surface uses
  the atomic helper; append-only logs (`adherence.log`, `costs.log`,
  `gates.log`) stay `O_APPEND` and are NOT locked.
  - AC: a grep-style test asserts no `open(..., "w")` followed by `json.dump`
    remains in the L4-owned files.

#### L5 - provenance scope (`guard_provenance.py`) - HIGHEST RISK IN THE PROGRAM

- **FR-HP-40:** Mode A's ledger read-modify-write runs inside `state_lock`.
  - AC: two concurrent mode A invocations for different paths leave BOTH paths
    in `self_authored`.
- **FR-HP-41:** Mode B-pre's ledger read-modify-write runs inside `state_lock`.
  - AC: two concurrent builder spawns credited to the same slug leave TWO
    dispatches on that slug's record.
- **FR-HP-42:** Mode B-post's ledger read-modify-write runs inside
  `state_lock`.
  - AC: a concurrent mode A write and mode B-post write leave both the audit
    and the self-authored path present.
- **FR-HP-43:** A builder spawn arriving while `active-task.json` is unreadable
  records an UNATTRIBUTED dispatch (appended to `unattributed_dispatches`) and
  logs it, rather than recording nothing.
  - AC: with an unparseable task file, a builder spawn appends exactly one
    entry to `unattributed_dispatches` and writes one DISPATCH line to
    `adherence.log`.
- **FR-HP-44:** The audit demand in mode C (commit) and mode D (Stop) is
  computed over `dirty_source_paths` INTERSECTED WITH the ledger's
  `self_authored` path list, not over every dirty path. An empty intersection
  means no audit is demanded, and the allow is logged. This is the fix the
  parked `company/specs/spec-repo-scoped-enforcement.md` identified as the
  cheaper and more principled one: the doctrine says "nothing SELF-AUTHORED
  integrates unaudited", and the code has never asked that question. It makes
  the gate correct for any layout without scoping machinery because it stops
  asking a tree-shaped question.
  - AC: dirty paths `["a.py"]` with `self_authored = []` -> mode C ALLOWS and
    writes a BYPASS line naming the empty intersection.
  - AC: dirty paths `["a.py"]` with `self_authored = ["a.py"]` and no fresh
    audit -> mode C BLOCKS, byte-identical to today's message apart from the
    path list.
  - AC: dirty paths `["a.py", "b.py"]` with `self_authored = ["b.py"]` -> mode
    C BLOCKS and the message names `b.py` only.
  - AC: the same three cases hold for mode D's Stop decision.
- **FR-HP-45:** `delegated_with_dispatches(ledger, tasks, gated, dirty)` grants
  an exemption via the entry-shape route METHOD mechanism 5 already gives
  delegated work. It returns True only when ALL of: `gated` is non-empty; every
  gated entry's execution decision is `delegated`; every gated entry has at
  least one HOOK-RECORDED credited dispatch (`credited_dispatches`, per slug);
  and no dirty path appears in the ledger's `self_authored` list. Mode C and
  mode D both consult it, and every grant is a logged BYPASS.
  - AC: two gated entries, both delegated, both with a credited dispatch, no
    self-authored dirty path -> True, and mode D allows with a BYPASS line.
  - AC: the same with one entry's execution set to `self` -> False.
  - AC: the same with one entry's dispatch list empty -> False.
  - AC: the same with one dirty path present in `self_authored` -> False.
  - AC: `gated == []` -> False (never vacuously true).
- **FR-HP-46:** The accepted hole is characterized by a test, not left implicit:
  source written through Bash (heredoc, `sed`, a script) never passes through
  mode A, so it is absent from `self_authored` and therefore stops arming the
  audit requirement under FR-HP-44 and satisfies FR-HP-45's fourth condition.
  The test asserts the CURRENT behavior and carries a comment naming
  OQ-HP-05 so that a future change closing the hole fails visibly rather than
  silently.
  - AC: a test writes a source file by subprocess (not through the hook path),
    marks the tree dirty, leaves `self_authored` empty, and asserts mode C
    ALLOWS - with a comment naming this as the known accepted limitation.
- **FR-HP-47:** `company/adr/ADR-0003-self-authored-audit-scope.md` records the
  narrowing: what the audit demand now asks, why the tree-shaped question was
  wrong, the accepted Bash hole, and the fact that this supersedes the premise
  of the parked repo-scoped spec.
  - AC: the file exists, its status line reads `Status: accepted`, it cites
    FR-HP-44 through FR-HP-46, and it links the parked spec.

#### L6 - stop_gate and doctrine (`stop_gate.py`, `COMPANY.md`, `company/METHOD.md`, `company/GATES.md`, `company/templates/BRIEF-TEMPLATE.md`, `.claude/agents/{auditor,docs-librarian,qa-engineer,tech-lead}.md`)

- **FR-HP-50:** `stop_gate` scopes its block. DECIDED by the owner
  (DECISIONS #18): `stop_gate` gets SCOPED, not unwired and not deleted - this
  is a requirement, not a proposal. When exactly ONE gating entry
  (type not in quick/hotfix) is active, behavior is byte-identical to today: a
  red, stale or missing stamp emits the block decision and the BLOCK line.
  When MORE than one gating entry is active, it emits NO block decision and
  instead appends one WARN line to `adherence.log` naming the stamp reason and
  every gating slug. Deletion and un-wiring are forbidden: `stop_gate` is the
  only check on three paths `guard_commit` cannot see - a session that edits
  and never commits, a session that commits green then edits more, and closing
  an entry with red gates.
  - AC: one gating entry plus a stale stamp -> stdout is the exact JSON block
    decision shipped today, and one BLOCK line is written.
  - AC: two gating entries plus a stale stamp -> stdout is empty, exit 0, and
    exactly one WARN line naming both slugs is written.
  - AC: two gating entries plus a GREEN fresh stamp -> stdout empty, no WARN
    line.
  - AC: `stop_gate.py` remains wired in `.claude/settings.json` and the
    FR-HP-25 wiring assertion covers it.
- **FR-HP-51:** `.claude/agents/auditor.md` step 2 verifies the stamp
  (`python3 .claude/hooks/gate_stamp.py --check`) instead of re-running the
  ladder the CEO runs in parallel, and runs `bash company/run-gates.sh` itself
  ONLY when the stamp is missing, red, or stale for the tree under audit.
  - AC: the file contains the `gate_stamp.py --check` invocation and the
    missing/red/stale condition, and no longer instructs an unconditional
    ladder run.
- **FR-HP-52:** `auditor.md` gains a delta-scoped re-audit mode: given a prior
  verdict plus the fix delta, the auditor checks each prior finding against the
  delta, checks the delta for new problems, and confirms the stamp - never a
  full re-read. The section states that a re-audit is a FRESH DISPATCH, never a
  SendMessage resume, because only Task and Agent spawns fire the PostToolUse
  event that records the audit in the ledger.
  - AC: the section exists, names all three re-audit steps, and carries the
    fresh-dispatch sentence.
- **FR-HP-53:** `auditor.md` grades test VALUE, not volume: padding
  (tautological tests, restated implementation, duplicate seam coverage) is a
  finding; on rework diffs, tests deleted together with the behavior they
  proved are CORRECT, and the ones NOT deleted are what to flag.
  - AC: both sentences present in the protocol section.
- **FR-HP-54:** The auditor's verdict vocabulary becomes SHIP /
  SHIP-WITH-FIXES / HALT, in both the frontmatter description and the Verdict
  section, and the file instructs the auditor never to emit the negative token
  `DO-NOT-SHIP` in prose. This is the proven workaround for the verdict-parser
  trap, and it lives in the agent definition so no CEO has to remember it. It
  MUST NOT merge before FR-HP-14 is on main (BR-HP-04).
  - AC: `.claude/agents/auditor.md` contains no occurrence of the string
    `DO-NOT-SHIP` outside a single line that explicitly forbids emitting it.
  - AC: a test feeds the file's own Verdict section text to `audit_verdict` and
    asserts the result is not `do-not-ship`.
- **FR-HP-55:** `COMPANY.md` gains a "Parallel discipline" section with
  four rules: dispatch a wave in ONE message; never idle while lanes build
  (draft next briefs, pre-read verification targets, decide CRs); integrate
  per-lane as each goes green rather than barrier-waiting; CRs are
  interrupt-priority.
  - AC: the section exists and each of the four rules is present as its own
    bullet.
- **FR-HP-56:** `COMPANY.md` gains a "Don't fight the harness" section:
  the block message is the recipe and is followed before reading hook source;
  work happens on task branches; a content edit between audit and commit stales
  the audit and fixes are batched so the audit runs once; a gate blocking twice
  on the same cause is an escalation, not a decoding exercise; never edit,
  disable or tunnel around a guard - file a CR.
  - AC: the section exists and each of the five rules is present.
- **FR-HP-57:** Right-sized paperwork, doctrine only: `company/METHOD.md`
  records that `RESUME.md` and `DECISIONS.md` stay around 300 lines with
  overflow archived VERBATIM to `company/state/archive/`, and COMPANY's
  operating loop names the archive step. No hook and no gate enforces the
  number (BR-HP-05 rationale: a line count is a magic number, and DECISIONS #5
  rejected numeric fences as an enforcement shape).
  - AC: both files carry the rule; a grep across `.claude/hooks/` finds no
    line-count constant for either file.
- **FR-HP-58:** QA evidence is four states per CHANGED screen:
  `.claude/agents/qa-engineer.md` and `company/GATES.md`'s "eyes" section both
  say the captures cover the screens the task order names and the diff touched,
  and that a full-surface sweep happens only when the task order explicitly
  asks for one.
  - AC: both files carry the CHANGED-screen wording and the on-demand
    full-sweep exception.
- **FR-HP-59:** docs-librarian is dispatched BATCHED - one dispatch per
  delivery covering everything merged since the last sync. The rule lands in
  `COMPANY.md` AND in the `description` frontmatter of
  `.claude/agents/docs-librarian.md`, whose current text still says "use after
  any merge" (the fork changed the doctrine and left the agent definition
  contradicting it).
  - AC: the agent description contains "BATCHED" and no longer contains "after
    any merge".
  - AC: `guard_models.py --check` stays green (the frontmatter `model:` line is
    untouched).
- **FR-HP-60:** `company/templates/BRIEF-TEMPLATE.md` gains test-quality DoD
  lines: each test proves a falsifiable claim of its FR; no
  restating-implementation or trivial-shape tests; extend the existing test
  file for a surface before creating a parallel one; rework DELETES the tests
  of removed behavior, listed in the report, because accreting dead tests is a
  defect.
  - AC: all four clauses present in the Definition of Done block.
- **FR-HP-61:** `.claude/agents/tech-lead.md`: spawn ALL developers in ONE
  message where paths are disjoint, sequencing only on a real dependency; drive
  QA on the FIRST finished surface rather than after the last developer
  reports; scale the review to risk (full line-read for invariants, money and
  state machines; ownership diff plus spot-reads for mechanical slices).
  - AC: all three rules present.
- **FR-HP-62:** `company/GATES.md` documents the runner changes: quiet-pass
  output with the `gate-output/` pointer, the `gates.log` run history and its
  single writer, and the G7 rung's extension from the spawn-hook assertion to
  the full wiring assertion.
  - AC: all three documented, and the G7 row text names the full wiring check.
- **FR-HP-63:** `company/METHOD.md`'s state table gains `gates.log` (one line
  per ladder run, written only by the runner) and `gate-output/` (the latest
  full output per gate), and its freshness wording matches content-based
  hashing.
  - AC: both rows present; no sentence in METHOD.md claims a commit stales a
    green stamp.
- **FR-HP-64:** `COMPANY.md` gains a short repair procedure for lost
  dispatch credits: re-credit through `guard_provenance`'s own functions,
  UNDER `state_lock`, and write an `adherence.log` REPAIR line naming what was
  repaired. Never hand-edit `company/state/provenance-ledger.json` - a hand
  edit resets the checksum, which wipes the recorded audit history. The
  acceptance criterion is documentary; no hook enforces it.
  - AC: the section exists, names the three elements (own functions, under the
    lock, REPAIR line), and states the checksum-reset reason for the
    prohibition.
- **FR-HP-65:** `COMPANY.md` and `company/METHOD.md` carry the standing
  advisory: concurrent BUILDING sessions in one checkout are fine and are what
  the lock layer exists for; concurrent INTEGRATING sessions are not - one
  integrating session per repository at a time. Git's own `index.lock` makes
  that collision loud rather than silent, which is why the advisory is prose
  and not a hook.
  - AC: the line is present in both files and distinguishes building from
    integrating.

### Business rules and validations

- **BR-HP-01:** At exactly ONE active entry, every hook's exit code, stdout,
  stderr and `adherence.log` line stay byte-identical to today wherever this
  spec does not deliberately change them. This extends BR-MST-02 and is the
  regression contract for the whole program.
- **BR-HP-02:** Fail-open posture is preserved everywhere. `state_lock` never
  blocks an action; every new code path exits 0 or allows on internal error.
  The two integrity CLIs (`witness_check.py`, `trace_check.py`) keep their
  fail-loud exception.
- **BR-HP-03:** No change that converts a BLOCK into an ALLOW ships without an
  enumerated decision-table test covering the negative space - every
  combination of the inputs that reach the decision, with its expected verdict.
  This applies to FR-HP-14, FR-HP-44, FR-HP-45 and FR-HP-50.
- **BR-HP-04:** The auditor vocabulary (FR-HP-54) and the verdict parser
  (FR-HP-14) ship as a PAIR, parser first. `HALT` and `DO-NOT-SHIP` both record
  the ledger value `do-not-ship`, so ledgers written before this program keep
  their meaning.
- **BR-HP-05:** The dual-nature rule holds: `company/` stays generic, tracked
  `company/gates.config` keeps its `CONFIGURE ME` placeholders, and no real
  gate command for this repo is committed. Enforcement thresholds introduced by
  this program derive from a stated invariant, never from a tuned number;
  `SLOW_HASH_SECONDS` is a LOG threshold and reaches no decision.
- **BR-HP-06:** Every FR ID in this spec appears verbatim in an implementing
  code comment or a test name, so `trace_check.py` can see it. The v0.2.6
  close-out shipped 27 orphan requirement IDs; this program does not repeat it.
- **BR-HP-07:** In wave 1, each lane owns a DISJOINT test file. In wave 2, a
  lane extends the existing test file for its surface where it is the sole
  owner of that file for the wave. The BRIEF-TEMPLATE rule (extend, do not
  parallelize) yields to file-disjointness only inside a parallel wave, and the
  brief says so.
- **BR-HP-08:** Prose is product in this repository. No requirement, constant,
  or optimization introduced here may exclude `*.md` or `*.txt` from a
  freshness fingerprint, a gate, or an audit scope.
- **BR-HP-09:** L5 does not merge without an independent auditor pass over its
  diff (verdict SHIP, or SHIP-WITH-FIXES with every fix applied and one
  delta-scoped re-audit). It converts BLOCKs into ALLOWs, which the WORRIES row
  on the umbrella-scoped dirty check names as the class needing a spec and an
  independent read rather than a patch.
- **BR-HP-10:** Hooks stay Python 3.8 stdlib only, with no new dependency. No
  new runtime state file is added to the packed payload (`package.json` already
  negates `company/state/**`; the pack-manifest assertions must stay green).

### Scope

**In:**

- Six workstreams L1 through L6 exactly as specified above, in two waves.
- Two accepted ADRs (FR-HP-08, FR-HP-47) and one change request (FR-HP-27).
- Regression tests for every FR, and decision-table tests for every
  BLOCK-to-ALLOW change.
- A release note for 0.2.7 stating the `is_source` behavior change for field
  installs.

**Out (explicit - each line exists to stop a downstream agent from helpfully
expanding):**

Non-requirements carried over from the source catalog, with the reason each is
refused here:

1. **`HASH_EXCLUDES` must NOT gain `*.md` or `*.txt`.** The fork excludes prose
   on the grounds that it decides no gate outcome. That is FALSE in this repo:
   markdown IS the product (agent definitions, skills, COMPANY.md,
   doctrine, templates), and `no_slop`, `trace_check` and `guard_models` all
   gate it. Excluding it would let a doctrine rewrite stale nothing - a
   false-green generator. Do not "fix" this later without superseding
   ADR-0002.
2. **`_SUBREPOS` depth-two exemption in `is_source` is NOT ported.** It exists
   so `backend/docs/**` is exempt in a polyrepo working copy. This repo is
   single-repo; the rule would re-open the hole FR-HP-13 closes.
3. **Repo-scoped cached gate skips, the `"repo"` field in `gates.config`, and
   `tree_hashes` stamp keying are NOT ported.** Three reasons. (a) This repo is
   single-repo, so the mechanism has nothing to key on. (b)
   `company/specs/spec-repo-scoped-enforcement.md` is PARKED with measured
   evidence refuting the premise: git does not recurse into nested
   repositories, all 71 blocking paths in the real polyrepo install were
   umbrella-level, and the dirty-INTERSECTED-WITH-self-authored fix (now
   FR-HP-44) was identified there as the cheaper and more principled one. (c)
   The reference `check_stamp` returns green UNCONDITIONALLY when its
   `tree_hashes` map is present and empty, which is every non-polyrepo project
   - it never reaches the `work_hash` comparison. Porting it would ship a
   false-green generator to every install. CORRECTION to the dispatch note:
   the reference DOES include `tree_hashes` inside the stamp checksum payload
   (`gate_stamp.write_stamp` computes the checksum after adding the field), so
   "written outside the checksum" is not among the reasons - verified
   2026-08-13. The empty-map false-green is sufficient on its own.
4. **Model tiering is NOT ported.** DECISIONS #1 (2026-07-09) vetoed
   qa-engineer and docs-librarian to sonnet and it stands; the fork also tiers
   the builtins. Every role stays opus. The only portable crumb is the
   `pricing.sonnet` data block in `company/models.json` for cost estimates,
   which is data, not routing - and it is out of scope for this program
   because no L-lane owns `models.json` data. File it as a quick task if cost
   estimates need it.
5. **The worktree-native-suite rewiring (catalog item 6) is NOT in scope.**
   The fork stops builders and leads from running `run-gates.sh` in a worktree
   and points them at the repo's native suite. It is defensible, but it is
   coupled to the parked merge-gating decision and to the wiring of the ladder
   in a worktree, and it changes the DoD every existing brief was written
   against. Separate task.
6. **`guard_spec` quick-type entries needing no brief is NOT in scope.** It
   arrived in the fork as part of the low-band waiver package, which is parked
   decision 2 below.
7. **Polyrepo commit-target resolution (`commit_repo_root`, per-sub-repo dirty
   scanning, per-repo audit tree hashes) is NOT ported.** FR-HP-11 ports only
   the `-C`-aware BRANCH resolution, which is a worktree concern in a
   single-repo product, not a polyrepo one.
8. **No `stop_gate` deletion or un-wiring.** Named here because the fork did
   exactly that and the catalog recommends it. Now also settled by the owner
   (DECISIONS #18): scoped, not unwired. See FR-HP-50 for the three paths that
   would go unchecked.
9. **The writing-discipline rule is NOT duplicated into a second hook.** The
   fork carries `.claude/hooks/guard_invariants.py`, which re-implements an em
   dash check that `no_slop` already enforces, and it is wired only in
   `.claude/settings.local.json` - so nobody reading `.claude/settings.json`
   would know it runs. Two enforcers of one rule drift, and an enforcer hidden
   in a local settings file is invisible to the FR-HP-25 wiring assertion by
   construction. `no_slop` remains the single writer of this rule. Do not port
   the file, and do not add a local-settings hook to compensate for anything
   in this program.

Parked owner decisions - recorded, NOT specified. No requirement in this spec
implements any of them, and no agent may start one:

- **P1. Move the green-stamp requirement from commit to merge.** It amends
  METHOD mechanism 4 ("commits are hook-blocked while gates are red or
  stale"). Unparks when the owner rules on it AND it lands paired with a
  `stop_gate` decision and with the fork's own later correction: a low-band
  waiver must itself require a green fresh stamp, or waived commits touch no
  gate verification at all.
- **P2. A risk-scaled audit band.** The fork's low-band line-count waiver as
  built is REJECTED: DECISIONS #5 vetoed exactly this shape of numeric fence.
  Unparks only if it derives from `risk_score.py`'s existing bands rather than
  a new constant, and only if the same change ARMS a mandatory audit in the
  HIGH band - which is what closes the standing WORRIES row about a clean
  delegated build getting no independent audit. Note that FR-HP-45 WIDENS that
  row's exposure, which is why the pairing matters.
- **P3. The Phase 0 spec-lite rung.** Two rungs on objective conditions (one
  repo, nothing frozen, no money, no invariant) with the CEO deriving the
  sealed brief directly. It amends METHOD mechanism 1. Unparks on an owner
  ruling.
- **P4. Splitting the ladder into worktree-meaningful gates versus
  integration-only gates.** FR-HP-28 makes a worktree ladder run gate and
  stamp the tree it actually ran against, which is strictly more correct but
  leaves the question of WHICH rungs are meaningful inside a worktree
  unanswered (see OQ-HP-14). The doctrine change - builders and leads prove
  their work with the repo's native suite and the full ladder runs once at
  integration - is the fork's catalog item 6 and stays PARKED. Unparks on an
  owner ruling, and it must land with the brief and agent-definition DoD
  changes it implies.

### UX notes

The only surfaces a human sees are the transcript and the block messages.

- A green ladder reads as a table plus one pointer line per gate. A red ladder
  reads exactly as today, because that is when detail is load-bearing.
- Every new ALLOW is a logged BYPASS line, never silence. `adherence.log` stays
  the proof the system enforces, and a bypass that is not greppable is a
  regression.
- Block messages stay recipes: FR-HP-16 names the offending paths and says the
  work may predate this session, because an unnamed block reads as an
  accusation against the wrong session.
- The FR-HP-25 failure message names the missing bindings and points at
  `claude-company update`, so the fix is self-service.
- The FR-HP-50 warning is deliberately quiet: at N > 1 the session that would
  have been blocked cannot act on the block, so the record goes to the log
  where the CEO reads it, not to the turn that cannot use it.

## Part 2 - Build readiness

### Owned directories and files, per workstream

Wave 1 lanes are file-disjoint by construction; verify with the ownership diff
at integration.

| Lane | Owns (exclusive) | Tests |
|---|---|---|
| L1 kernel | `.claude/hooks/_common.py`, `company/adr/ADR-0002-content-based-freshness.md` | `tests/hooks/test_state_kernel.py` (new) |
| L2 guards | `.claude/hooks/guard_commit.py`, `.claude/hooks/guard_secrets.py`, `.claude/hooks/guard_spec.py` (is_source only), `.claude/hooks/guard_provenance.py` (verdict parsing and the mode D reason string only) | `tests/hooks/test_guard_parsers.py` (new) |
| L3 runner | `company/run-gates.sh`, `.claude/hooks/gate_stamp.py`, `.claude/hooks/guard_models.py`, `.claude/hooks/guard_frozen.py`, `company/frozen-surfaces.json`, `.gitignore`, `company/change-requests/CR-2-*.md` | `tests/hooks/test_gate_runner.py` (new) |
| L4 state writers | `.claude/hooks/witness_check.py`, `.claude/hooks/cost_capture.py`, `.claude/hooks/guard_spec.py` (torn-read path only) | `tests/hooks/test_state_writers.py` (new) |
| L5 provenance | `.claude/hooks/guard_provenance.py`, `company/adr/ADR-0003-self-authored-audit-scope.md` | extends `tests/hooks/test_guard_provenance.py` |
| L6 doctrine | `.claude/hooks/stop_gate.py`, `COMPANY.md`, `company/METHOD.md`, `company/GATES.md`, `company/templates/BRIEF-TEMPLATE.md`, `.claude/agents/{auditor,docs-librarian,qa-engineer,tech-lead}.md` | `tests/hooks/test_stop_gate_scope.py` (new) plus doctrine assertions there |

Read-only to every lane: `tests/hooks/test_hooks.py` and the other existing
suites are extended only where the owning lane's table row says so. Nobody
touches `company/gates.config`, `package.json`, `install.sh`, `update.sh`, or
`.github/workflows/`.

Two shared-file seams to manage, both sequential rather than parallel:

- `guard_spec.py`: L2 owns `is_source` in wave 1; L4 owns the torn-read path in
  wave 2. Disjoint functions, disjoint waves.
- `guard_provenance.py`: L2 owns the verdict parser and the mode D reason in
  wave 1; L5 owns the ledger locking and the audit scope in wave 2.

### Invariants in play

- Hooks fail OPEN; the two integrity CLIs fail LOUD. FR-HP-01 and FR-HP-32
  extend fail-open into new territory and must not narrow it anywhere.
- Only `run-gates.sh` writes `gates.status`; only `guard_provenance` writes the
  ledger; only `witness_check.py --add/--remove` mutates the witness registry.
  FR-HP-22 adds a second runner-only file and no second writer.
- `company/` ships verbatim and stays generic; `gates.config` keeps its
  placeholders.
- Python 3.8, stdlib only.
- BR-MST-02 single-entry byte-identity (extended as BR-HP-01).
- Accepted ADRs are immutable. ADR-0001 is untouched; ADR-0002 and ADR-0003 are
  NEW and become immutable on merge.
- `CLAUDE.md` stays out of the pack list.

### Frozen surfaces touched, and the CRs needed

- `company/frozen-surfaces.json` `always` list gains
  `company/state/gates.log` and `company/state/gate-output/**`. Changing the
  frozen registry is itself a change-request action (METHOD mechanism 3, and
  CR-UPD-1 is the precedent). **CR-2 must be filed and approved before the L3
  lane merges** (FR-HP-27). Next free CR number is CR-2 per STATUS.md.
- `guard_frozen.ALWAYS_DEFAULTS` is the hardcoded baseline that reaches
  EXISTING installs, because `install.sh` copies `frozen-surfaces.json` with
  `copy_if_absent` and `update.sh` restores it only when absent. Both lists
  must be updated or the freeze reaches fresh installs only. This is a fact,
  verified in the code, not an assumption.
- `company/state/gates.status` is already frozen; `gate_stamp.py` writes it
  through the filesystem, not the Edit tool, so FR-HP-24 does not interact with
  `guard_frozen`.
- No other frozen surface is touched. `.claude/settings.json` is READ by
  FR-HP-25 and written by nobody in this program.

### Data model impact

No database. State-file shape changes, all forward-compatible:

- `company/state/gates.log` - NEW, append-only text, one line per ladder run.
  Untracked, ignored, frozen. No reader in the harness; it is a human and
  post-hoc analysis record.
- `company/state/gate-output/<gate>.log` - NEW, replaced per run. Untracked,
  ignored, frozen.
- `company/state/.state.lock` - NEW, zero-byte lock file. Untracked. Not
  frozen (it carries no information and is created on demand).
- `company/state/gates.status` - unchanged shape. The `work_hash` VALUE changes
  format from a bare sha256 hex digest to `tree:<oid>`. Any stamp written
  before the upgrade compares unequal to the new hash and reads as STALE, which
  is the correct and safe direction: the first ladder run after the upgrade
  re-stamps. Document it in the release note.
- `company/state/provenance-ledger.json` - unchanged shape (version 2). Verdict
  VALUES are unchanged (`ship`, `ship-with-fixes`, `do-not-ship`, `unknown`).
  Audits recorded before the upgrade carry old-format work hashes and therefore
  read as stale, same safe direction.
- `company/witnesses.json` and `company/state/.cost-cursor.json` - unchanged
  shape; write path becomes atomic.

Migration required: none. Field installs get the new behavior through
`claude-company update`, which replaces the hook files. The one visible
consequence is one extra ladder run after upgrading, and new blocks in projects
carrying `app/company/**` or `src/docs/**` source (FR-HP-13).

### Contracts impact

- `_common` gains `state_lock`, the atomic write helper,
  `active_tasks_unreadable`, `active_tasks_path`, `HASH_EXCLUDES` and
  `SLOW_HASH_SECONDS`. All additive; no existing signature changes.
- `guard_commit.git_subcmd` keeps its `(sub, args)` signature; only its parse
  changes. `guard_secrets` becomes a consumer of it (new intra-package
  dependency, matching the existing `guard_provenance` -> `guard_commit`
  import).
- `guard_provenance` gains `audit_verdict`, `response_text`,
  `self_authored_set` and `delegated_with_dispatches`. `fresh_audit` and
  `staleness_reason` keep their signatures - the polyrepo `repo=` parameter is
  NOT ported.
- `guard_models.py --check` keeps its exit-code contract (0 green, 1 red) and
  gains failure reasons. It is gate G7; a new red reason is a behavior change
  for every install, which is the intent.
- `run-gates.sh` keeps its CLI (no arguments) and its exit-code contract. The
  fork's `--all` flag belongs to cached skips and is NOT ported.

### Open questions and chosen fallbacks

Every OQ has ONE decided fallback that every agent implements and tags at the
site as `// OQ-HP-NN assumption`. The owner may overrule later.

- **OQ-HP-01:** Which `stop_gate` scoping shape - block only when attributable
  to this session's own work, or block only when a single gating entry is
  active? FALLBACK: **single-gating-entry rule** (FR-HP-50). Attribution needs
  session-keyed state, which the multi-session spec deliberately scoped out,
  and the single-entry case (the overwhelmingly common one) keeps today's
  behavior byte-identical. If the fallback proves wrong, the escalation is the
  attribution shape with session-keyed state.
- **OQ-HP-02:** Should a project be able to declare a deliberate un-wiring
  exempt from the FR-HP-25 assertion? FALLBACK: **no exemption mechanism.** A
  project that removes a shipped hook has a red G7 and files a CR. An
  exemption list is a waiver with a nicer name, and DECISIONS #5 rejected that
  enforcement shape. OWNER-FACING: this is an enforcement-design call in the
  DECISIONS #5 family; record it for the owner rather than deciding it
  permanently.
- **OQ-HP-03:** Is 1.5s the right slow-hash threshold? FALLBACK: **1.5s**, and
  it stays a LOG threshold that reaches no decision, so a wrong value costs a
  noisy or a silent log line and nothing else.
- **OQ-HP-04:** How many tail lines does a passing gate print? FALLBACK:
  **3 lines plus the pointer**, no configuration knob.
- **OQ-HP-05:** Should the Bash-authored-source hole in `self_authored` be
  closed in this program? FALLBACK: **no.** It is accepted, characterized by
  the FR-HP-46 test, named in ADR-0003, and given a WORRIES row at
  integration. Closing it means recording provenance for arbitrary shell
  writes, which is a different program.
- **OQ-HP-06:** Does `gates.log` need rotation? FALLBACK: **no rotation in
  0.2.7.** One line per ladder run; revisit if a real install passes 10,000
  lines.
- **OQ-HP-07:** Should installs gitignore the new state paths? FALLBACK:
  **repo-local `.gitignore` only.** `install.sh` does not manage a target's
  `.gitignore` today and this program does not start; `company/state` is
  excluded from the work hash, so untracked state files stale nothing.
- **OQ-HP-08:** Does the delegated exemption (FR-HP-45) apply at commit as
  well as at Stop? FALLBACK: **both**, gated by the same four conditions and
  the same decision-table test. A delegated build that may finish its turn but
  not commit is an incoherent rule.
- **OQ-HP-09:** Should an ambiguous audit verdict be treated as passing?
  FALLBACK: **yes, `unknown` passes**, matching this hook's fail-open posture
  and today's behavior for any response not containing the negative token.
- **OQ-HP-10:** Torn-read retry budget? FALLBACK: **3 retries, 0.06s apart**
  (about 0.18s worst case on a genuinely broken file).
- **OQ-HP-11:** `state_lock` timeout? FALLBACK: **2.0s, then proceed
  unlocked** (fail open). A lock that can jam a session is worse than a lost
  update, and the atomic writes bound the damage.
- **OQ-HP-12:** Is FR-HP-11 (`-C`-aware branch resolution) in scope, given the
  dispatch named only the parser fix? FALLBACK: **yes, build it in L2.**
  FR-HP-10 alone creates a new false-block class for `git -C <worktree>
  commit`, and false blocks are the cost this program exists to remove. The L2
  report must flag it as an addition beyond the dispatched line item so the
  CEO can veto it without unpicking FR-HP-10.
- **OQ-HP-13:** Is the ~300-line paperwork cap a magic number? FALLBACK:
  **doctrine prose only, never a hook or a gate.** The number is guidance with
  an archive procedure attached; nothing mechanical reads it.
- **OQ-HP-14:** After FR-HP-28, a ladder run inside a worktree stamps that
  worktree, so it does NOT satisfy the main checkout's commit-time or
  Stop-time stamp check (those resolve their root from `CLAUDE_PROJECT_DIR`).
  Is that acceptable? FALLBACK: **yes, and it is the intended reading.** A
  worktree's green ladder is evidence about the worktree, and the main
  checkout's gates are the integrator's. The alternative - a worktree run
  writing the main checkout's stamp - is the false-green FR-HP-28 exists to
  kill. The real resolution is parked decision P4 (which rungs are meaningful
  inside a worktree at all); until it unparks, the CEO runs the ladder at
  integration, which is already the doctrine.

### Verification plan

Two suites gate this repo and both must be green before any commit:

```bash
python3 -m unittest discover -s tests/hooks -q   # the hooks
npm test                                          # CLI + install + pack manifest
```

`tests/hooks/run_tests.sh` discovers every `test_*.py` under `tests/hooks/`, so
new files in that directory reach CI without a workflow edit. No new
`tests/install/*.sh` file is created by this program, which is what would
require a manual CI step (the known W-030 class hole).

How each FR is proven:

| FR | Proof |
|---|---|
| FR-HP-01 | Two-process serialization timing test; forced `fcntl` failure; exception-in-body release test |
| FR-HP-02 | Concurrent reader loop over 200 writes; forced `json.dump` failure leaves destination and directory clean |
| FR-HP-03, FR-HP-04 | Fixture task files: valid, absent, unparseable-then-valid, permanently unparseable |
| FR-HP-05 | Temp git repo: hash invariance under `git add` and under commit; hash change under a source edit; `.git/index` untouched; git-absent fallback |
| FR-HP-06 | Hash changes for `COMPANY.md` and an agent file; does not change for `company/state/adherence.log` |
| FR-HP-07 | Stubbed slow implementation asserts exactly one TIMING line; fast path asserts zero |
| FR-HP-08, FR-HP-47 | Test asserts the ADR files exist, are `Status: accepted`, and cite their FRs |
| FR-HP-10 | Parse table over 8 command forms including the `commit -C HEAD~1` trap |
| FR-HP-11 | Subprocess end-to-end against a real worktree on a task branch, plus the bare-commit regression |
| FR-HP-12 | Source assertion (no duplicate parser) plus a monkeypatch proving delegation, plus a staged-secret block through `git -C` |
| FR-HP-13 | Path table: `app/company/service.py`, `src/docs/render.py`, the four root exempt dirs, a root source file, a README |
| FR-HP-14 | Verdict table over 10 texts including the poison sentence, `HALT`, disagreeing labels, `SHIPPING` |
| FR-HP-15 | Content-block list flattening asserted against `str()` behavior |
| FR-HP-16 | Reason string over 7 and over 0 self-authored dirty paths |
| FR-HP-17 | Recipe text asserted at one and at three entries; compound `switch && commit` still blocks |
| FR-HP-20, FR-HP-21 | Configured fixture gate emitting 500 lines, run green and red; stdout line count and `gate-output` content asserted |
| FR-HP-22 | Three runs, three lines, per-gate fields; read-only state dir keeps the exit code |
| FR-HP-23 | `guard_frozen` block on `gates.log` with and without the registry file; clean `git status` after a run |
| FR-HP-24 | Reader loop across 200 stamp writes never sees `malformed` |
| FR-HP-25 | Settings fixtures: shipped-green, missing Stop hook, missing Bash group, missing hook file, extra hook, plus the existing spawn assertion |
| FR-HP-27 | CR file exists and names both patterns |
| FR-HP-28 | Temp repo plus a real `git worktree`: run the ladder from the worktree with `CLAUDE_PROJECT_DIR` pointing elsewhere, assert the stamp lands in the worktree with the worktree's work hash and the other stamp is untouched; plus the main-checkout and no-git-tree fallbacks |
| FR-HP-30, FR-HP-31 | Two-process race tests for the registry and the cursor; `--check` byte-identity; source assertion on `with` usage |
| FR-HP-32 | Unparseable task file allows with a BYPASS line; absent task file still blocks byte-identically |
| FR-HP-33 | Source scan for non-atomic JSON writes in the owned files |
| FR-HP-40 to FR-HP-43 | Two-process ledger race tests per mode; unreadable-task-file spawn records an unattributed dispatch |
| FR-HP-44, FR-HP-45 | Decision-table tests (BR-HP-03): the full cross product of dirty paths x self_authored x execution decision x dispatch count x audit freshness, mode C and mode D, each row with its expected verdict |
| FR-HP-46 | Characterization test writing source outside the hook path, asserting the ALLOW and naming OQ-HP-05 |
| FR-HP-50 | Stop-hook fixtures at one and two gating entries, stale and green stamps; stdout and `adherence.log` asserted |
| FR-HP-51 to FR-HP-65 | Doctrine assertions in `tests/hooks/test_stop_gate_scope.py`: each file is read and the required clause asserted present (and, for FR-HP-54, absent) |

Beyond the suites:

- The CEO re-runs both suites on integrated main after each lane merges, and
  CI must be green on every PR.
- `python3 .claude/hooks/guard_models.py --check` green on integrated main.
- `python3 .claude/hooks/trace_check.py` green with zero orphan FR-HP IDs.
- `python3 .claude/hooks/witness_check.py --check` green, with 1 to 3 witnesses
  recorded per lane at integration.
- L5 additionally requires an independent auditor pass (BR-HP-09).
- Manual probe, once, on integrated main: create a second worktree on a task
  branch, run `git -C <worktree> commit`, and confirm it is neither silently
  ungated (today's bug) nor falsely blocked (the FR-HP-11 regression risk).

### Wave plan and exit criteria

**Wave 1 (parallel): L1, L2, L3.** File-disjoint. Exit criteria, all on
integrated main:

1. Both suites green plus CI green on each lane's PR.
2. `guard_models --check` green, including its own new assertion.
3. `trace_check` reports zero orphan FR-HP IDs for wave 1.
4. Decision-table test present for FR-HP-14 (the one wave-1 BLOCK-to-ALLOW).
5. CR-2 approved and applied.
6. ADR-0002 merged and accepted.
7. Ownership diff shows no lane touched another lane's files.

**Wave 2 (parallel): L4, L5, L6.** Starts when wave 1 is fully merged and
green on main - L4, L5 and L6 all depend on L1's `state_lock` and atomic
helper, and FR-HP-54 depends on L2's parser (BR-HP-04). Ordering constraint
INSIDE the wave: L6's FR-HP-54 does not merge before FR-HP-14 is on main,
which wave 1's exit already guarantees.

Exit criteria:

1. Both suites plus CI green on integrated main.
2. Decision-table tests present for FR-HP-44, FR-HP-45 and FR-HP-50.
3. An independent auditor pass over the L5 diff, verdict SHIP or
   SHIP-WITH-FIXES with fixes applied and one delta-scoped re-audit.
4. ADR-0003 merged and accepted.
5. Witnesses recorded for each lane and the registry checksum valid.
6. WORRIES rows graduated per the table below, with the two rows that do NOT
   graduate updated rather than deleted.

### WORRIES rows this program closes

Cited by their worry text so the CEO can graduate them at integration.

| Lane | Row | Disposition |
|---|---|---|
| L1 | P2 "staging stales a provenance audit" - `work_hash` includes `diff --cached`, so `git add` after the auditor pass stales the audit even with identical content | GRADUATES on FR-HP-05: content hashing removes staging from the fingerprint entirely |
| L2 | P3 "git -C evades guard_commit subcmd parse" | GRADUATES on FR-HP-10 plus FR-HP-12 (the secrets scan shares the fixed parser) |
| L2 | P1 "provenance audit verdict parser is substring-naive" - has cost four blocked commits against passing audits | GRADUATES on FR-HP-14 plus FR-HP-15, with FR-HP-54 supplying the doctrine half |
| L5 | P1 "provenance dirty check is umbrella-scoped, not repo-scoped" | GRADUATES on FR-HP-44: the gate stops asking a tree-shaped question, which is the resolution the parked spec's park note already identified |
| L6 | P2 "SendMessage-resumed audits record no provenance" | GRADUATES on FR-HP-52, whose re-audit mode states that a re-audit is a fresh dispatch and never a resume |
| L5 | P2 "a clean delegated build gets NO independent audit" | DOES NOT GRADUATE. FR-HP-45 makes the exemption explicit and therefore WIDER. Update the row to cite FR-HP-45 and parked decision P2 (the high-band mandatory audit) as its close-out path |
| L1 | P3 "background writers stale the gate stamp" | DOES NOT GRADUATE. Content hashing still includes untracked non-ignored files; `.gitignore` remains the mechanism. Leave the row as is |

New rows to ADD at integration:

- P3, from OQ-HP-05: source written via Bash is never recorded in
  `self_authored`, so it neither arms the FR-HP-44 audit demand nor denies the
  FR-HP-45 exemption. Accepted and characterized by a test; escalation is
  provenance recording for shell writes.
- P2, from FR-HP-13: field installs carrying `app/company/**` or `src/docs/**`
  source become newly gated on upgrade. Correct behavior, but it is a
  behavior change strangers did not ask for; watch for reports after 0.2.7.

## Spec-ready checklist (the Phase 0 gate)

- [x] Every FR has a stable ID and at least one acceptance criterion - 53 FRs,
      all with falsifiable criteria carrying concrete values
- [x] Out-of-scope is explicit - 9 non-requirements with reasons, 4 parked
      owner decisions with unpark conditions
- [x] Every open question has a single decided fallback - 14 OQs, 14 fallbacks
- [x] Owned directories are named and disjoint from other in-flight work -
      per-lane table; STATUS.md records nothing in flight as of 2026-07-29
- [x] Frozen-surface needs are identified and CRs filed - CR-2 specified as
      FR-HP-27, a wave-1 exit criterion
- [x] Data/contract impact stated - state-file table, no migration, one
      documented stamp-format transition
- [x] Verification plan covers every FR - per-FR proof table plus the
      integration checks

## Part 3 - Brief handoff

Derive six briefs with `company/templates/BRIEF-TEMPLATE.md`, one per lane,
each linking this spec rather than embedding it. Each brief carries: its FR
subset, its owned file list from the table above, BR-HP-01 through BR-HP-10 as
invariants in play, its OQ fallbacks, its named test file, and its wave's exit
criteria. L5's brief must carry BR-HP-09 (the auditor pass) as a DoD line, not
as prose.
