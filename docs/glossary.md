# Glossary

The vocabulary claude-company uses, in one place. The company runs on a small
set of typed documents and enforced rules, and each has a precise meaning here
that is worth pinning down. Terms are grouped by what they belong to; most link
back into [How it works](how-it-works.md) and [Customizing](customizing.md)
where the mechanism is shown in full.

New to the system? Read the lifecycle section first, then roles. The rest is
reference you can jump into from any doc.

## The lifecycle

### SDLC

Software development lifecycle: the ordered path a change travels from idea to
shipped code. Here that path is spec -> brief -> build -> verify -> gate ->
ship, and every stage is backed by a hook rather than left to habit. The point
of the company shape is to force a change through the stages in order instead of
letting an agent skip from idea to commit.

### Phase 0

The specification stage that runs before any code. A `feature` is not built
until its spec is spec-ready: requirements have stable IDs and every open
question has a decided fallback. A `quick` task skips Phase 0; a `program` adds
an architecture stage on top of it.

### Definition of done (DoD)

The condition that ends work: the gate suite passes on the integrated result,
and for a delivery, the owner's acceptance is recorded. "It works locally" is
not a state the company recognizes.

### Wave

In a `program`, a set of workstreams built in parallel. A wave is a merge
barrier: its exit criteria must be green on `main` before the next wave starts.

### Exit criteria

The conditions a wave must satisfy before the following wave may begin. Set by
the architect in the wave plan, checked on the integrated result.

### Workstream

A directory-disjoint slice of a program, owned by exactly one tech lead.
Workstreams never share a directory, so agents working in parallel cannot
collide.

### Ownership map

The architect's assignment of disjoint directories to each workstream, drawn
before any lead is spawned. It is what lets parallel work stay conflict-free.

## Roles

### Owner (client)

The human. A client of the company, not its operator: the owner states what to
build, answers the short escalation list, and presses the buttons no agent may
press (deploy, publish, anything touching money). The company does its own
process.

### CEO

The main Claude session. Dispatches the other roles, arbitrates change requests,
verifies and integrates finished work, and reports upward. Writes only glue code
and small fixes itself.

### Product manager

Owns Phase 0. Turns a request into a spec-ready document with requirement IDs
and a decided fallback for every open question.

### Architect

Owns structure before build. For a `program`, produces the ownership map, the
frozen-surface list, and the wave plan with hard exit criteria.

### Tech lead

Runs one workstream. Decomposes its brief, spawns and manages its own
developers on disjoint directories, fills the gaps between their pieces, drives
QA, runs the gates, and reports upward with evidence.

### Developer

Builds exactly what its task order says, inside its owned directories, in an
isolated worktree. Never redefines the plan, because it does not own the plan.

### QA engineer

Drives the running product through a real browser (Playwright) and captures
evidence screenshots: loaded, empty, error, and after-action. Captures the
evidence; it does not judge it.

### Auditor

An independent, read-only reviewer. Rechecks a risky or large merge with fresh
context and returns a ship / ship-with-fixes / do-not-ship verdict. It cannot
write code, which is the point.

### Ideation strategist

Divergent thinker for fuzzy or open-ended asks. The CEO spawns several in
parallel with different assigned lenses and synthesizes an options memo.

### Optional roles

`devops-engineer` (CI, build tooling, release preparation), `security-reviewer`
(adversarial read-only pass before a release), and `docs-librarian` (sync docs
and canon to merged code). Present when a project needs them.

## Task classes

The CEO classifies every request; ceremony scales with the class.

### ideation

The ask is ideas or direction, or is too fuzzy to build without guessing.
Parallel strategists diverge, the CEO converges, the client gets an options
memo, and the winning idea reclassifies as quick, feature, or program.

### quick

A small bug, copy change, or config tweak. Brief only, one developer or the CEO,
no Phase 0. Gates still gate.

### feature

A new user-visible capability, or anything touching a frozen surface, an
invariant, or money. Runs the full path: Phase 0 spec, brief, one tech lead and
team, QA evidence, verify, integrate.

### program

A multi-workstream build such as a v1 or a large subsystem. The architect
produces an ownership map and wave plan; leads run in parallel within each wave.

### hotfix

Production is on fire. Declared by the CEO in `active-task.json`. Hooks log the
bypass instead of blocking, but `guard_secrets` still holds. A retroactive spec
and tests follow within a day, and no hotfix closes without a postmortem.

## Documents and artifacts

The company communicates through typed documents, not long conversations.

### Options memo

Numbered ideas with reasoning, a scored recommendation, and the strongest
rejected option. Written by strategists and the CEO for the owner.

### Spec

The rich, human-facing requirements document produced in Phase 0. Carries stable
requirement IDs, acceptance criteria, and the options considered. Builders never
read the spec directly; they read the brief derived from it.

### Requirement ID (FR / BR / OQ)

A stable label on one requirement so code, tests, and reports can all point at
the same line. `FR` is a functional requirement (what the software does), `BR` a
business requirement (a rule the business imposes), `OQ` an open question with a
decided fallback. An `// OQ-XX-NN` tag in code marks where a fallback was
assumed.

### Brief

The lean execution slice derived from the spec: mission, read-first list, owned
directories, invariants in play, nearby frozen surfaces, ordered scope,
definition of done, fallbacks, and out-of-scope. This is what a builder actually
reads. A vague brief is the main cause of a bad agent run.

### Work order (task order)

The directive that puts an agent to work inside named directories with a defined
scope. A brief is the work order for a whole workstream; a task order is the
developer-level slice a tech lead hands down. Source-code changes with no
approved work order are hook-blocked.

### Report

Facts only, from an agent to whoever dispatched it: the diff, gate output,
screenshots, deviations. No adjectives. Follows `company/templates/REPORT-TEMPLATE.md`.

### Change request (CR)

The only way to change a frozen surface. An agent that needs one stops and files
a CR naming what, why, the exact diff, and the blast radius; the CEO approves
and applies it in a dedicated gated commit, or rejects it with a workaround. The
CR queue is integration risk made visible.

### Architecture decision record (ADR)

A record of how the structure holds together, in `company/adr/`, so a settled
choice is not relitigated from memory. Specs say what to build; ADRs say how.
Once marked `Status: accepted` an ADR is immutable.

### Postmortem

The document that closes a hotfix. It must name a real mechanical change that
prevents the same failure again - a new witness, a new gate, a new frozen
pattern - or state plainly why none is possible.

### Evidence report

The bundle a delivery ships with: what merged, the gate ladder result, QA
screenshots, and the decisions left for the owner. Delivery is not done until
the owner's acceptance is recorded.

## Gates and hooks

### Hook

A script that runs before a file edit or shell command (or when a session tries
to stop) and blocks the action if it breaks a rule. Hooks are where the
load-bearing rules live: the prose explains why, the hook supplies the no. Hooks
fail open (an internal error lets the action through) except the two integrity
checks, which fail loud.

### Gate

A single command that must exit successfully: a test suite, a linter, a build.
An agent's self-report never decides done; a gate does.

### Gate suite (gate ladder)

The ordered set of gates in `company/gates.config`, run cheap to expensive by
`company/run-gates.sh`. Beyond a project's own tests it includes the mechanical
rungs every install inherits.

### Rung

One gate in the ladder. The inherited rungs are witnesses, requirement
traceability, model routing, and the dependency audit (run last because it
reaches the network).

### Stamp (gates.status)

The recorded result of the last gate run, fingerprinted against the working
tree and written to `company/state/gates.status`. The stamp is what gives gates
teeth: a bare pass is not enough, the pass has to match the current tree.

### Stale

The state of a stamp after any tracked file changes since the gates ran. A stale
stamp counts as not-passing, so "it passed earlier" stops mattering. Nobody,
including the CEO, can commit past a red or stale stamp.

### Witness

The exact line or lines a shipped fix is pinned to - the code that would break
first if the fix regressed. Registered in `company/witnesses.json` (mutated only
through `witness_check.py`, never by hand). If a witness line vanishes while the
board reads green, the gate goes red, which is how a silently un-done fix gets
caught.

### Orphan (requirement traceability)

A spec requirement that has neither implementing code nor a test tracing to it,
and was not explicitly deferred. The traceability rung goes red on an orphan, so
a requirement cannot be quietly dropped.

### Model routing (model drift)

Each agent runs on the model its manifest declares (`company/models.json`).
Silent drift to a different model is red.

### no_slop

The writing-discipline hook. It blocks em dashes, smart quotes, the ellipsis
character, and stock AI filler in anything written, so the repo's prose stays
plain. A CI job scans every tracked text file for the same glyphs.

## Protected surfaces and decisions

### Frozen surface (protected file)

A file with exactly one legitimate writer - a shipped migration, the schema, a
lockfile, anything listed in `company/frozen-surfaces.json`. The hook blocks
every edit; change comes only through a CR.

### guard_secrets

The commit guard that scans a staged diff for API keys, tokens, private keys,
and JWTs and blocks the commit if one is present. The single rule a hotfix
cannot bypass, because a leaked credential does the most damage in exactly the
emergency a hotfix declares.

### Accepted

The status line that freezes an ADR. Once an ADR reads `Status: accepted`, a
guard blocks every edit to it; the decision changes only by a superseding ADR
that names what it replaced.

## Risk, cost, and provenance

### Risk score

A per-branch score across a handful of signals - diff size, nearness to a
protected file, share of tests, whether it touches sensitive paths. A low score
merges on the normal path; a high score makes an independent audit mandatory
rather than a judgment call.

### Provenance

The record that a change was independently verified. The provenance hook blocks
a commit or task close while the main checkout holds source changes no verifier
context has audited at the current tree state. Delegated worktree work is exempt,
because its verification already happened inside the hierarchy.

### Adherence log

`company/state/adherence.log`, one line per hook block and per hotfix bypass. It
is the difference between a system that claims discipline and one that shows it;
repeated blocks on the same agent or file are a signal that a work order was
vague or the design is fighting the rules.

### Worktree

An isolated git worktree where a builder works: one worktree, one branch, one
accountable lead per workstream. Isolation is why parallel builds do not
collide, and why verification reruns the gates on the integrated result rather
than trusting a worktree's own numbers.

## State the company maintains

All under `company/state/`, all owned by the CEO.

| File | What it holds |
|---|---|
| `STATUS.md` | The current-truth board. Red stays red until proven green; a status is never averaged. |
| `RESUME.md` | The session handoff: done, running, next, plus the facts every spawn needs. Read first on session start. |
| `WORRIES.md` | A terse ledger of suspected-but-unproven risks. A row graduates out when it becomes a CR, a STATUS risk, or a verified fix. |
| `DECISIONS.md` | Owner escalations and their outcomes, including recorded acceptance of a delivery. |
| `active-task.json` | The machine-readable pointer to the task in flight, read by hooks. |
| `provenance-ledger.json` | Audit and dispatch records for the task in flight, written only by the provenance hook. |
| `gates.status` | The stamped gate result, written only by the gate runner. |
| `adherence.log` | Every hook block and bypass, one line each. |
| `costs.log` | One line per agent stop: token use and an estimated spend. Estimates for visibility, never a bill. |

The board is `STATUS.md`: when a doc says the board is green, it means every
active task's gates pass and nothing red is outstanding.
