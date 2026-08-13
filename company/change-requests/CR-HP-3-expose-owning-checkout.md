# CR-HP-3: expose-owning-checkout

_Requesting agent/task: tech-lead, task hp-provenance (brief `company/briefs/brief-hp-provenance.md`, issue #101). Date: 2026-08-13._
_Status: PROPOSED_

## Frozen surface affected

`.claude/hooks/_common.py` - the L1 state kernel. Not in
`company/frozen-surfaces.json`, but it is another lane's owned path (L1,
`hp-kernel`), and hp-provenance's "You own" list does not include it. Filing a
CR is the visible route rather than reaching across an ownership boundary.

## Why (cite the requirement)

Scope item 8 of the hp-provenance brief: "Use the kernel's derivation rather
than a second implementation; if the primitive you need is not exposed, report
it rather than reimplementing it."

`guard_provenance.in_worktree_or_out_of_tree` answers the same question
`_common.rel_path` answers - which checkout owns this path - and until this lane
it answered it by matching the literal string `/.claude/worktrees/`. `git
worktree add` accepts any path, so a worktree created anywhere else lost its
delegated exemption while the kernel resolved it correctly. Two answers to one
question is the bug class the #107 P0 just fixed, so the fix is to call the
kernel's derivation, not to copy it.

The kernel's derivation is `_common._enclosing_checkout(candidate, root_norm)`.
It is underscore-prefixed, so `guard_provenance` now depends on a private name.
That dependency is real and load bearing: if L1 renames or re-signatures it,
`guard_provenance` silently degrades to "no path is ever in a worktree", which
is fail-open and would re-arm the commit gate against every delegated lane in
this program at once. A private name carrying that much weight should be public.

Two shape mismatches, both of which `guard_provenance` currently paper over at
its own call site, and both of which belong in the kernel:

1. `_enclosing_checkout` starts its walk at `os.path.dirname(candidate)`, so a
   candidate that IS a checkout root (a payload `cwd`, which is exactly what
   Modes B-post and C pass) resolves to its parent and answers None.
   `guard_provenance` works around this by appending a probe segment when the
   candidate is a directory.
2. It answers with the checkout path, so every caller that wants the boolean
   writes `bool(...)` plus its own out-of-tree test.

## Exact proposed change

Add to `_common.py`, beside `rel_path`:

```python
def owning_checkout(root, path):
    """The checkout that owns `path`: a nested checkout under root, or None.

    Public form of _enclosing_checkout, and tolerant of `path` being a
    DIRECTORY (a payload cwd may be the worktree root itself, which the
    dirname-first walk would otherwise resolve to its parent). Relative paths
    resolve against root. Never raises; None on anything unresolvable.
    """
```

Implemented over the existing `_enclosing_checkout` with the directory probe
folded in, so there remains exactly one derivation. `_enclosing_checkout` stays
where it is; `rel_path` keeps calling it directly.

`guard_provenance.in_worktree_or_out_of_tree` then reduces to: outside root ->
True; else `bool(c.owning_checkout(root, path))`.

## Blast radius

Additive. No existing signature changes and no existing behaviour changes:
`rel_path` and the `build/elsewhere/wt2` test L1 added keep their current
answers, because the new function is a wrapper over the same walk.

Consumers today: `guard_provenance` (Modes A, B-post, C, E) once this lands.
`rel_path`'s own callers - `no_slop`, `guard_frozen`, `guard_spec`,
`guard_tests`, `guard_models` - are untouched.

Gates re-run: `tests/hooks/` (both `test_state_kernel.py` and
`test_guard_provenance.py`).

## Owner sign-off needed?

no. It is an internal helper's visibility, not an invariant, a surface
guarantee or a behaviour change.

## Workaround if rejected

Shipped as of this lane: `guard_provenance` calls `_common._enclosing_checkout`
directly and carries the directory probe at its own call site, inside a
fail-open `try`. It is correct today. The residual risk is coupling to a private
name with no test asserting the coupling, and it belongs in `WORRIES.md` if this
CR is rejected.
