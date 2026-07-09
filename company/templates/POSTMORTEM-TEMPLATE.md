# POSTMORTEM: <incident-slug>

_Incident: <slug>. Filed: <YYYY-MM-DD>. Author: <role>._

Filed after a hotfix, per `company/METHOD.md` (a `hotfix` runs with logged
bypasses; the retroactive spec, tests, and this postmortem land within a day).
Facts, not adjectives. No hotfix task closes until this is filed and its
prevention line names a real mechanical change.

## Timeline

Timestamps in UTC. If a step's time is unknown, write "unknown", do not guess.
- **Detected:** <YYYY-MM-DD HH:MM> - <how it surfaced: alert, user report, gate>
- **Mitigated:** <YYYY-MM-DD HH:MM> - <what stopped the bleeding, even if temporary>
- **Resolved:** <YYYY-MM-DD HH:MM> - <the hotfix landed and the fix is verified>

## Root cause

One honest paragraph: what actually broke, at what layer, and the chain from
change to failure. Name the mechanism, not a person. <...>

## Blast radius

Who and what was affected, and for how long.
- **Affected:** <users / endpoints / data / money touched>
- **Scope:** <how many, which environments>
- **Duration:** <detected-to-resolved window>
- **Residual:** <anything still degraded or needing follow-up, or "none">

## Why the gates did not catch it

Be specific about the rung.
- **Which rung should have caught it:** <G-number and gate, e.g. G3 tests / G6
  trace / G8 audit> - and why it did not (missing case, positive-only test,
  stale stamp, ...).
- **Or which rung did not exist:** <the check that was never wired>.

## THE PREVENTION LINE

The mechanical change that now stops this from recurring. This is the point of
the postmortem. It MUST name a real, checkable change - a new witness, a new
gate row, a new frozen-surface pattern - OR state explicitly why no mechanical
prevention is possible (and what human discipline replaces it).

**Prevention:** <exact command or file change - see the example below>

EXAMPLE (the shape - one of these, filled in for real):
```text
# a load-bearing witness pinning the spot that broke first
witness_check.py --add W-042 "SessionStore.evict expires idle tokens"

# a new blocking gate row in company/gates.config
{"name": "token-expiry-test", "command": "pytest tests/test_session_expiry.py", "blocking": true}

# a new frozen-surface pattern in company/frozen-surfaces.json
"surfaces": ["src/auth/session_store.py"]

# no mechanical prevention possible - state why, and the discipline that replaces it
No gate can catch a third-party API changing its response shape without notice.
Replaced by: a contract-conformance check (G4) added against the vendor schema,
run on the vendor's published version pin.
```

A vague prevention line ("be more careful", "add more tests") is not done. Name
the ID, the row, or the pattern.

## Close

No hotfix task closes without this postmortem filed. The CEO checks the
prevention line at close: it names a real mechanical change (a `W-NNN` witness,
a `company/gates.config` row, a `company/frozen-surfaces.json` pattern), or it
states plainly why none is possible and what discipline stands in its place.
