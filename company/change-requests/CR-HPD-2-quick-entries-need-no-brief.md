# CR-HPD-2: guard_spec must exempt `quick` entries, or the new doctrine is false on disk

_Requesting agent/task: tech-lead, task/hp-doctrine (L6, issue #102). Date: 2026-08-13._
_Status: PROPOSED_

## Surface affected

`.claude/hooks/guard_spec.py`, the brief check at lines 118-131 (step (c), the
ALL over non-hotfix entries). Outside this lane's "You own" list; the hp-guards
lane holds `is_source` in the same file, and the rest is unassigned.

## Why (cite the requirement)

Brief `brief-hp-doctrine.md` scope item 7, authorized by DECISIONS #19 (a):
"`quick` entries need no brief", to land in METHOD's ceremony table and
ORCHESTRATOR's classify step. Both are now written.

The hook says otherwise, and it is not a near miss:

```python
        non_hotfix = [e for e in tasks if e.get("type") != "hotfix"]
        ...
        for entry in non_hotfix:
            brief = entry.get("brief")
            if not brief:
                offenders.append((entry, None))
```

`quick` is not exempt - only `hotfix` is - so a `quick` entry with no `brief`
field is an offender and every source edit is blocked with `no active brief`.

The multi-entry consequence is the part that makes this urgent rather than
cosmetic. The check is an ALL over non-hotfix entries and the block is on the
EDIT, not on the offending entry: one briefless `quick` entry in
`active-task.json` blocks source edits for EVERY concurrent session in that
working tree, including lanes whose own briefs are perfectly in order. A CEO
that follows the new doctrine literally - open a `quick` entry, skip the brief -
bricks source editing for the whole checkout until it notices and writes the
brief the doctrine just told it it did not need.

This is the same defect class this lane exists to close: canon and mechanism
disagreeing, with the mechanism winning silently.

## Exact proposed change

Exempt `quick` from the brief requirement the way `hotfix` is exempted from the
whole gate - per entry, never as an ANY waiver:

```python
        offenders = []  # (entry, brief-or-None)
        for entry in non_hotfix:
            # DECISIONS #19 (a): a quick entry needs no brief - the request is
            # the work order. Per-entry, like the hotfix exemption: a briefless
            # quick entry exempts ITSELF and never the tree.
            if entry.get("type") == "quick" and not entry.get("brief"):
                continue
            brief = entry.get("brief")
            ...
```

A `quick` entry that DOES name a brief keeps being checked - a named brief file
that does not exist stays a block, because that is a typo, not a choice.

Tests: `tests/hooks/test_multi_task_gates.py` (GuardSpecMultiEntry) needs a case
for a briefless `quick` entry alongside a briefed feature entry - edit allowed,
and the FR-MST-05 empty-list-first ordering untouched.

## Blast radius

- `guard_spec.py` only. No other hook reads `brief` for a gating decision.
- Single-entry byte-identity (BR-MST-02) is preserved for every existing
  shape: a lone `feature` entry with no brief still blocks with the same
  message. Only the briefless-`quick` shape changes, and today that shape is
  unreachable by anything except a doctrine-following CEO.
- Gates to re-run: the hooks suite.

## Owner sign-off needed?

No. DECISIONS #19 (a) already carries the owner's authorization for the rule;
this is the mechanism catching up with it.

## Workaround if rejected

Two, both worse:

1. The doctrine stands and every `quick` entry keeps carrying a brief in
   practice, which means shipping canon the machine contradicts - the exact
   thing this lane's new CI canon check exists to make loud.
2. This lane softens the doctrine to "a quick entry needs no SPEC, and a
   one-paragraph brief is still required". That is a scope change against
   DECISIONS #19 and is not a call this lane can make.

Either way, tell the lane which, because the doctrine text is already written
and the difference is one sentence.

---
_CEO decision and remarks:_
