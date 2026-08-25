# 0.5.0 - intent replication

The harness compressed intent at every layer: the spec proxied the owner's
idea, the brief proxied the spec, the task order proxied the brief. A builder
optimizes hard against the proxy it was handed and hits it perfectly, which is
why long projects produced work that passed every gate and was hollow
underneath.

One spec now travels to every spawn at every depth. The brief is a pathspec
pointer that restates nothing. A builder's definition of done is the outcome
plus a mechanical evidence floor, not a checklist to optimize against.

## Breaking

- `company/templates/BRIEF-TEMPLATE.md` and `company/templates/SPEC-TEMPLATE.md`
  ship in the overwrite payload. An install that modified either receives a
  `.new` sibling to merge by hand.
- The `product-manager` agent is removed from the payload. Existing installs
  keep their copy until they update.

## Changed

- **Brief is a pointer.** Spec link, `## You own`, the outcome, and a short
  evidence floor. Mission, Read first, ordered Scope and the DoD checklist are
  gone.
- **Tech lead lands the shared contract in code** (types, schema, tests that
  fail on a second shape) before cutting interiors, applies the split test -
  would a builder need to see the other slice? - and hands down the same spec
  plus a pathspec. The sealed mini-brief rule is deleted.
- **Developers read the spec** and own the quality of their slice.
  Cross-lane ambiguity still uses the spec's written fallback so parallel
  lanes converge; slice-interior questions are the builder's to decide and
  report.
- **METHOD Law 1 rewritten.** Attention is scarce, so the WRITE-SET is narrow.
  A pathspec narrows what an agent may write, never what it may know.
- **Phase 0 folds into the CEO.** Stable FR/BR/US ids, binary acceptance
  criteria, explicit out-of-scope, one decided fallback per open question,
  Part 2 build readiness and the spec-ready checklist are now the CEO's own
  job. Divergence fires only when the owner's ask is open; a stated idea goes
  straight to requirements.
- **Architect narrowed** to multi-lane programs. Its deliverable is the landed
  waist plus the ownership map, not a plan document.
- **`builtins.Explore` pinned to sonnet.** Read-only fan-out search does not
  need the top tier. The other built-ins stay on opus.

## Requirements

FR-ASR-01, FR-ASR-15 and FR-ASR-17 revised in place. FR-ASR-23..28 added for
intent replication, the outcome DoD, waist-as-code, the product-manager
deletion, conditional divergence, and the architect narrowing.

FR-HP-60's test-quality clauses moved from the brief template to
`.claude/agents/developer.md`, where they are replicated on every spawn, and
the doctrine test follows them there.
