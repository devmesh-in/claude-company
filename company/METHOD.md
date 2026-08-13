# METHOD.md - How this company works

claude-company turns a repository into a small software company run by AI agents
under one accountable orchestrator (the CEO, your main Claude session). This file
is the method. Every agent reads it once and holds to it. The CEO's private
runbook is `ORCHESTRATOR.md` (repo root); subagents never read that file.

The thesis, in one line: **gates are enforced, not narrated.** Process that lives
only in prose gets skipped under pressure. Here, the load-bearing rules are
backed by hooks and scripts that mechanically block; the prose explains why.

## The five mechanisms

1. **Canon before code (and spec before feature).** Features become spec-ready
   before any build. A spec (see `company/templates/SPEC-TEMPLATE.md`) carries
   stable requirement IDs (FR/BR/OQ) and a build-readiness section. Agents
   implement against the spec's derived brief and never resolve an ambiguity by
   personal judgment - they implement the brief's stated fallback and tag the
   site (`// OQ-XX-NN assumption`), or file a change request. Autonomy comes
   from removing decisions from agents, not from making agents guess well.

2. **Ownership boundaries are hard.** Every dispatched agent owns an explicit
   set of directories named in its brief; everything else is read-only to it.
   Workstreams are directory-disjoint by construction, and building agents work
   in isolated git worktrees (one worktree, one branch, one accountable lead
   per workstream - mechanics in `company/GIT.md`). Nobody fixes things they
   notice outside their scope - they report them.

3. **Frozen surfaces change only by change request.** The registry is
   `company/frozen-surfaces.json` (enforced by a PreToolUse hook). An agent that
   needs a frozen surface changed STOPS and files a CR in
   `company/change-requests/`; it never patches locally. The CR queue is the
   integration risk made visible. The bureaucracy is the point. Accepted
   architecture decision records (`company/adr/`) are frozen the same way: a
   guard blocks edits to any ADR whose status line is `Status: accepted`, and a
   settled decision is changed only by a superseding ADR (see
   `company/adr/README.md`). Precedence when a document and a decision clash:
   **an accepted ADR wins on architecture (how), the spec wins on scope (what).
   A brief that contradicts an accepted ADR is a briefing error; a builder that
   notices the conflict files a CR - it never picks a winner.**

4. **Gates are the definition of done.** "It works locally" is not a state this
   company recognizes. The gate suite (`company/run-gates.sh`, defined per
   project in `company/gates.config`, contract in `company/GATES.md`) decides,
   never an agent's self-report. Every gate is blocking, none is ever waived,
   and commits are hook-blocked while gates are red or stale. Freshness is
   CONTENT-based: a stamp goes stale when the content of the work changes under
   it, not when HEAD moves, so a commit or a merge of already-green content
   invalidates nothing.

5. **Verify, never trust - and never let the producer grade itself.** The agent
   that built something never judges it done. Developers report with evidence;
   tech leads re-check against the brief; QA drives the running product and
   captures screenshots but does not judge them; leads and the CEO judge. The
   CEO re-runs gates, diff-checks ownership, and spot-reads before integrating.

   This applies to the CEO mechanically, not just as prose: the provenance hook
   (.claude/hooks/guard_provenance.py, manifest company/provenance.json) blocks
   commit and task close while the main checkout holds source changes no
   independent verifier context has audited at the current tree state. Delegated
   worktree work is exempt, and the exemption rests on a precondition rather
   than on the worktree: SOMEONE independent verified it inside the hierarchy -
   a developer built, a lead re-checked against the brief, the CEO judged the
   lead's diff. A worktree is where that usually happens, not why it counts.

   So the exemption follows the verifier, not the directory. Any configuration
   that removes the independent reader - a build with no lead between the
   developer and the CEO, a single agent that both writes and reports - has
   nothing to exempt, and its work needs the audit the exemption was standing
   in for. Read the sentence as "verified by someone who did not write it";
   if you cannot name that someone, the exemption does not apply.

## The client posture

The owner is a CLIENT of this company, not its process operator. Frictionless
on the outside, hard-gated on the inside:

- **All paperwork is self-generated.** Specs, briefs, task state, gate
  config - agents produce every artifact. The templates in
  `company/templates/` are for agents; a client is never asked to fill,
  read, or approve one.
- **Hooks teach the machine, not the human.** When a hook blocks, its message
  is a recipe the blocked agent follows to make itself compliant (write the
  brief, set the task state, run the gates) - compliance is self-service,
  enforcement stays mechanical.
- **Defaults over questions.** Every decision that is not on the owner
  escalation list gets an opinionated default, applied immediately and
  recorded (DECISIONS.md, OQ fallbacks, STATUS notes) where the owner can
  veto it later. Asking is the exception; the escalation list is the whole
  list of exceptions.
- **Interruptions are batched.** The client hears from the company twice per
  engagement in the common case: owner decisions (batched, once) and
  delivery (evidence bundle: what shipped, gate ladder, screenshots, what is
  next). Process narration is noise. Delivery is not done until the owner's
  acceptance is recorded in `DECISIONS.md`; silence is not acceptance.
- **Uninitialized is not an error.** The orchestrator self-onboards on first
  contact - audits, wires gates, applies frozen defaults - instead of sending
  the client to a setup command.

## The hierarchy

```
Owner (human)
  CEO           - the main session. Dispatches, arbitrates CRs, verifies,
                  integrates, reports upward. Codes only glue and small fixes.
  Staff roles   - product-manager (Phase 0 specs), architect (boundaries,
                  ownership map, wave plan), auditor (read-only pre-merge audit)
  Tech leads    - one per workstream. Decompose the brief, spawn and manage
                  their own developers, fill the gaps between developers' work,
                  drive QA, run gates, report upward with evidence.
  Developers    - build exactly what their task order says, inside owned
                  directories, in a worktree.
  QA engineers  - drive the built surface (Playwright), capture evidence
                  screenshots for each CHANGED screen: loaded / empty /
                  error / after-action.
```

Depth is capped at two below the CEO by construction (CEO -> lead -> dev/QA).
Deeper pyramids multiply handoff drift and token cost without adding judgment.

Communication travels through typed artifacts, not conversation: spec -> brief ->
report -> STATUS. A brief is sealed and self-contained; a report follows
`company/templates/REPORT-TEMPLATE.md` and contains facts, not adjectives.

## Ceremony scales with the task

The CEO classifies every incoming request; nobody hand-picks ceremony:

| Class | What | Path |
|---|---|---|
| `ideation` | The ask is ideas/direction, or too fuzzy to build without guessing | Brainstorm engagement per `company/IDEATION.md`: parallel strategists diverge, CEO converges, client gets an options memo; the winner reclassifies as quick/feature/program. |
| `quick` | Small bug, copy change, config tweak | Brief only. One developer or the CEO itself. No Phase 0. Gates still gate. |
| `feature` | New user-visible capability, or anything touching a frozen surface, an invariant, or money | Phase 0 at one of two rungs, chosen on objective conditions and never on appetite. `spec-lite`: permitted only when ALL FOUR hold - one repo, nothing frozen, no money, no invariant in play - and the CEO derives the sealed brief straight from the request, recording the rung on the task's entry. Otherwise a full Phase 0 spec -> spec-ready gate. The escape upward is ONE-WAY: the moment the work touches a frozen surface, a second repo, or an invariant it becomes a full spec and never comes back down. Then brief (required at both rungs) -> one tech lead + team -> QA evidence -> verify -> integrate. |
| `program` | Multi-workstream build (a v1, a big subsystem) | Architect produces ownership map + wave plan. Waves are merge barriers: a wave's exit criteria must be green on main before the next wave starts. One lead per workstream, parallel within a wave. |
| `hotfix` | Production is on fire | Declared by the CEO on that task's entry in `company/state/active-task.json` (`"type": "hotfix"`). Hooks log the bypass instead of blocking. Retroactive spec/tests within a day, and no hotfix closes without a postmortem (`company/templates/POSTMORTEM-TEMPLATE.md`) filed next to its retroactive spec in `company/specs/shipped/` as `postmortem-<slug>.md`. The CEO checks its prevention line at close: the postmortem must name a real mechanical change that prevents recurrence (a new witness, a new gate, a new frozen pattern) or state why none is possible. |

## The context discipline

Spec context and build context are kept apart deliberately:

- The **spec** is rich and human-facing. The builder never reads it.
- The **brief** (`company/templates/BRIEF-TEMPLATE.md`) is the lean execution
  slice derived from the spec: mission, read-first list, owned directories,
  invariants in play, frozen surfaces nearby, ordered scope, DoD, fallbacks,
  out-of-scope. A vague brief is the main cause of a bad agent run.
- Agents read: the project's `CLAUDE.md`, their brief, and what the brief's
  "Read first" list cites. Nothing else is assumed.

## State the company maintains

All under `company/state/`, all owned by the CEO:

| File | Job |
|---|---|
| `STATUS.md` | Current truth board. Red stays red until proven green. Never average a status. |
| `RESUME.md` | Session handoff: done / running / next, plus the facts every spawn prompt needs. Read first on every session start. |
| `WORRIES.md` | Terse ledger of suspected-but-unproven risks: `P (P0-P3) \| Worry \| What \| Logic`. A row graduates OUT when it becomes a CR, a STATUS risk, or a verified fix. |
| `DECISIONS.md` | Owner escalations and their outcomes. |
| `active-task.json` | The machine-readable list of tasks in flight in this working tree (read by hooks). One entry per task; an entry carries that task's written execution decision (execution / execution_why) for feature/program work, plus reclassified_why on downgrades. Write it per the rule below. |
| `provenance-ledger.json` | Audit and dispatch records for the task in flight (written only by the provenance hook). |
| `gates.status` | The stamped gate result (written only by the gate runner). |
| `gates.log` | One line per ladder run - the run history, oldest first. Written only by the gate runner. |
| `gate-output/` | The latest full output of each gate, one file per gate, replaced on every run. Written only by the gate runner. |
| `adherence.log` | Every hook block and bypass, one line each. Proof the system enforces. |
| `costs.log` | One line per agent stop: token usage and an estimated spend, appended by the cost_capture hook. Estimates only, not billing. |

### active-task.json holds a list

Several sessions can run against one working tree at once, so the file is a
list of entries, not one task:

```json
{"version": 2, "tasks": [{"task": "<slug>", "type": "<class>", "brief": "<path>"}]}
```

An entry carries the same fields one task carries: `task`, `type`, `brief`,
`test_scope`, `execution`, `execution_why`, `issues`, `reclassified_why`.
Insertion order is the stable render order everywhere the entries are shown.
A legacy single-object file is still read correctly, so an existing install
needs no migration.

Slugs are unique per working tree, and no slug may be a prefix of another. A
dispatch is credited to an entry by finding that entry's slug in the spawn
prompt, so a `feat` entry would be credited by a prompt naming `task/feat-a`.

**Write safety, the one rule.** Add your task's entry with a targeted Edit.
Remove ONLY your entry. Never rewrite the whole file. An Edit replaces against
current disk content, so two sessions editing at different anchors both
survive. A whole-file Write drops the other session's entry.

### Build in parallel, integrate alone

Concurrent BUILDING sessions in one checkout are supported and expected - the
entry list above and the state lock layer exist for exactly that. Integrating
is the exception: one integrating session per repository at a time. Merging,
stamping the ladder, removing worktrees, and pruning entries all contend for
the same HEAD and the same state files, and two sessions doing that at once
leave an integration nobody can reconstruct afterwards.

No hook enforces this. Git's own `index.lock` already makes the collision loud
rather than silent - the second merge fails visibly instead of interleaving
quietly - so the mistake costs a retry, and a guard would buy nothing the error
message has not already bought.

### Right-sized paperwork

`RESUME.md` and `DECISIONS.md` are working documents, not archives. Keep each
to around 300 lines. When one grows past that, move the overflow VERBATIM into
`company/state/archive/` and leave a one-line pointer behind. Move, never
summarize: a summarized decision loses the reason it was made, which is the
only part anyone comes back for.

This is doctrine only - no hook and no gate enforces the number, and none will.
A line count is a magic number, and this company rejects numeric fences as an
enforcement shape: a check that fires at 301 lines teaches padding to 299, not
brevity. The rule stands on its own consequence instead - a handoff file nobody
finishes reading has already stopped working. (OQ-HP-13 assumption: doctrine
prose only, never a hook.)

## What is never decided below the owner

1. Weakening any design invariant or frozen surface's guarantees.
2. Money and billing behavior.
3. Deploys, prod migrations, cutover. Merge is integration; deploy is a manual
   owner step, never in any script or agent's tooling. Release preparation is
   doctrine in `company/RELEASE.md` and ends at a proposal on `DECISIONS.md` -
   the company prepares, the owner tags and publishes.
4. Scope changes beyond a brief.
5. A gate failing twice on the same cause after a respawn - that signals a
   design problem, not an agent problem. Stop and surface.
6. Business-policy open questions. Agents run on tagged fallbacks; the owner
   answers the question.

## The Workflow tool is outside enforcement

The Workflow tool runs its own internal `agent()` spawns that fire NO PreToolUse
events - the hooks never see them, so `guard_models` cannot pin their model and
they inherit the main-loop model. It is therefore FORBIDDEN by default in
company projects. It is permitted only with explicit owner authorization AND a
`model` pin in EVERY `agent()` call, including all early-stage agents: resuming
a dead workflow re-runs the incomplete early-stage agents live, so partial
pinning does not hold.

## Writing discipline

All writing in this repository stays hook-clean: straight quotes, ' - ' rather
than em dashes, three dots rather than the ellipsis character, and no stock AI
filler phrases. The `no_slop` PreToolUse hook enforces this mechanically.
