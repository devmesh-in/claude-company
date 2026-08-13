# CR-HPD-3: agent memory is a build INPUT and must not stale the gate stamp

_Requesting agent/task: tech-lead, task/hp-doctrine (L6, issue #102). Date: 2026-08-13._
_Status: PROPOSED_

## Surface affected

`HASH_EXCLUDES` in `.claude/hooks/_common.py` (L1's kernel, merged as #107).
Alternatively `.gitignore`. Both are outside this lane's "You own" list, which
is why this is a CR and not a local edit.

## Why (cite the requirement)

DECISIONS #19 (c) added `company/briefs/**` and `company/specs/**` to
`HASH_EXCLUDES` on the stated ground that "paperwork is a build INPUT and has
now cost two full ladder runs in one day, roughly fifteen minutes, for edits
that changed no code."

`.claude/agent-memory/` is the same class of artifact and was missed. It is
untracked, NOT gitignored, and NOT excluded, so `git add -A` in
`_content_tree_hash` picks it up and every memory write changes the work_hash
of the whole checkout.

This is not theoretical. It blocked this lane's final commit at 09:0x today,
and the cause was identified by diffing the two content trees rather than by
guessing - both hashes are real git tree objects, so:

```
git diff-tree -r --name-status 3aec22f 2be45ad
M	.claude/agent-memory/developer/MEMORY.md
M	.claude/agent-memory/developer/project_npm_test_pack_block_red_locally.md
M	.claude/agent-memory/developer/project_worktree_cwd_pins_to_main.md
```

Three memory files, written by developer agents doing exactly what the system
prompt instructs them to do, staled a green stamp that was 
minutes old and blocked an unrelated commit on a task branch in a worktree.

The loop this creates is the important part: the CEO ran the ladder to clear
the block, agents wrote memory during the next turn, and the stamp went stale
again. Re-running the ladder cannot escape it, because the thing that stales
the stamp is a side effect of agents working.

## Exact proposed change

Add one entry to `HASH_EXCLUDES`:

```python
HASH_EXCLUDES = (
    "company/state",
    "company/briefs",
    "company/specs",
    ".claude/agent-memory",
)
```

Rationale to record next to it: agent memory is a build INPUT written as a side
effect of agents working, never a build OUTPUT that a gate could verify. A
memory file cannot break a test, so it must not be able to invalidate a test
run.

`.gitignore` is the weaker alternative. It would also work mechanically, but it
changes whether memory is committable at all, which is a separate decision that
belongs to whoever owns the memory feature - and the exclusion is correct even
if memory is later tracked deliberately.

## Blast radius

- `_common.py` only, one tuple entry. Every consumer of `work_hash` inherits
  it: `check_stamp`, `guard_commit`, `stop_gate`, and the provenance
  freshness check.
- It makes the freshness check strictly LESS sensitive, so the risk is a stamp
  that stays green across a memory-only change. That is the intent, and it is
  the same trade already accepted for briefs and specs.
- Gates to re-run: the hooks suite, which owns the content-hash tests.
- A test belongs with it: writing a file under `.claude/agent-memory/` leaves
  `work_hash` unchanged, mirroring the existing brief/spec cases.

## Owner sign-off needed?

No. DECISIONS #19 (c) already settled the principle for build inputs; this
applies it to an artifact class that did not exist in that decision's evidence.

## Workaround if rejected

None that holds. Every agent turn that writes a memory file re-stales the
stamp, so the block returns on the next commit no matter how many ladders are
run. The only alternative is instructing agents to stop writing memory, which
disables a shipped feature to protect a hash.

---
_CEO decision and remarks:_
