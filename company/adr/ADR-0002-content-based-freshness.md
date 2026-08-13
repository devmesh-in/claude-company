# ADR-0002: Freshness is content, not history position

Status: proposed
Date: 2026-08-13

_Born proposed on purpose. The brief for task hp-kernel (FR-HP-08) asked for
`Status: accepted`, which contradicts accepted ADR-0001 and the born-proposed
rule that `guard_frozen` enforces on new ADRs. A builder does not pick a winner
between a brief and an accepted ADR, so this ships proposed with CR-HP-1 asking
the CEO to flip the status at integration._

## Context

Two things in this company key off `_common.work_hash(root)`: the gate stamp in
`company/state/gates.status` (green only while the recorded hash still matches
the tree) and the provenance ledger's audit records (an audit covers the tree at
the hash it names). Both answer one question - has the work changed since this
evidence was produced.

The original hash answered a different question. It digested `rev-parse HEAD`,
`status --porcelain`, `diff` and `diff --cached`, which fingerprints where a
tree sits in git HISTORY, not what the tree CONTAINS. Three consequences
followed, and all three were paid in ceremony rather than in safety:

- `git add` of an unchanged file moved the hash, because staging moves content
  between `diff` and `diff --cached`. Staging audited work staled its own audit.
- Committing moved the hash, because HEAD moved. Green gates and a fresh audit
  died at the moment the work was committed - exactly when nothing had changed.
- A merge or a rebase producing byte-identical content moved the hash too.

Each of those forced a re-run of the ladder, or a re-audit, to prove a tree
identical to one already proven. A freshness check that fires when nothing
changed teaches its operators to re-run gates reflexively, which is how a real
staleness signal stops being read.

## Decision

A work hash is the git tree object the working copy WOULD commit as, minus
`HASH_EXCLUDES`, and nothing else (FR-HP-05). It is built in a throwaway index
(`GIT_INDEX_FILE` pointed at a temp path, `read-tree HEAD` when HEAD exists,
`add -A`, drop the excludes, `write-tree`) and returned as `tree:<oid>`; the
repository's real `.git/index` is never touched. Identical content therefore
hashes identically no matter where it sits in history, so staging, committing,
merging and rebasing stale neither a gate stamp nor an audit, while any real
content change still does.

`HASH_EXCLUDES` is exactly `("company/state",)` (FR-HP-06). Prose stays INSIDE
the fingerprint here. The implementation this kernel was ported from also
excludes `*.md` and `*.txt`, on the sound argument that in a product application
no doc edit can change a gate outcome. That argument inverts in this repository:
markdown is the product. The agent definitions, the skills, `ORCHESTRATOR.md`,
`company/METHOD.md` and the rest of the doctrine are shipped artifacts, and
`no_slop`, `trace_check` and `guard_models` all gate them. Excluding prose would
mean a doctrine rewrite stales nothing and ships behind a green stamp that never
saw it. `company/state` is excluded for the opposite and mechanical reason: the
stamp and the logs live there and would self-invalidate the hash the moment they
were written.

The mechanism fails open. On any git trouble the hash falls back to the legacy
HEAD-plus-status-plus-diff digest - which is STRICTER, so a degraded git costs
false staleness, never false freshness - and to `no-git` when git answers
nothing at all.

## Consequences

- Committing audited, gated work no longer invalidates the evidence for it. The
  standing P2 worry "staging stales a provenance audit" is closed by
  construction rather than by discipline.
- The stamp now says something narrower and truer: this exact content was
  proven. It says nothing about which commit carries it, and nothing about
  `company/state`.
- Cost accepted, and it is real: two trees with identical content but different
  history are indistinguishable to every freshness check. A revert that restores
  byte-identical content re-validates a stamp produced before it. That is
  correct under this decision - the gates test content - but anyone who needs
  "this COMMIT was gated" must record the commit, not the hash.
- Cost accepted: the hash now costs a `git add -A` into a throwaway index rather
  than three cheap plumbing calls, and that call writes loose objects into the
  real object store for dirty files. Healthy repositories measure well under a
  second (this one measures about 0.07s); a call over `SLOW_HASH_SECONDS` (1.5)
  leaves one TIMING line in `adherence.log` (FR-HP-07) so a pathological tree is
  visible rather than merely slow. The breadcrumb reaches no decision.
- Every gate stamp written before this lands reads stale exactly once, because
  the hash format changes from a bare sha256 digest to `tree:<oid>`. One ladder
  re-run per checkout clears it. Nothing downstream parses the hash - every
  consumer compares it for equality - so no other code changes.
- Prose edits keep staling stamps and audits in this repository, deliberately. A
  future reader who ports the fork's `HASH_EXCLUDES` verbatim would silently
  disarm gating for most of what this product ships, so the constant carries the
  reason in a comment and a test pins the tuple.
- The throwaway index is load-bearing safety, not an implementation detail. A
  content hash built in the real index would corrupt a developer's staged state
  on every hook invocation, so a test asserts the real index is byte-identical
  across a `work_hash` call.

## Scope

- `.claude/hooks/_common.py` - `work_hash`, `HASH_EXCLUDES`, `SLOW_HASH_SECONDS`
- `.claude/hooks/gate_stamp.py` - the `work_hash` field of the stamp
- `.claude/hooks/guard_provenance.py` - audit freshness and staleness reasons
- `company/state/gates.status` - the stamped hash

## Supersedes

none
