#!/usr/bin/env bash
# tests/install/test_update.sh - exercises update.sh (the disposition engine)
# and lib/manifest.py against a real install of this repo. Every flow from the
# brief's DoD gets at least one assertion: pristine, modified, bootstrap,
# --check byte-identity, updated (backup+overwrite), downgrade guard, second-run
# idempotency, user-state preservation, and the manifest determinism tripwire.
#
# Self-contained: installs this repo into temp targets via install.sh, then
# drives update.sh directly (the engine is testable without the Node CLI).
set -uo pipefail

TEST_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO="$(cd "$TEST_DIR/../.." && pwd)"

PASS=0
FAIL=0
pass() { PASS=$((PASS+1)); printf '  \033[32mPASS\033[0m %s\n' "$*"; }
fail() { FAIL=$((FAIL+1)); printf '  \033[31mFAIL\033[0m %s\n' "$*"; }
check() { local d="$1"; shift; if "$@" >/dev/null 2>&1; then pass "$d"; else fail "$d"; fi; }
nott()  { local d="$1"; shift; if "$@" >/dev/null 2>&1; then fail "$d"; else pass "$d"; fi; }

WORK="$(mktemp -d -t ccupdate.XXXXXX)"
cleanup() { rm -rf "$WORK"; }
trap cleanup EXIT

MAN_PY="$REPO/lib/manifest.py"
hashf() { python3 "$MAN_PY" hash "$1"; }
set_manifest_version() { # <manifest> <version>
  python3 - "$1" "$2" <<'PY'
import json, sys
m, v = sys.argv[1], sys.argv[2]
d = json.load(open(m)); d["version"] = v
json.dump(d, open(m, "w"), indent=2, sort_keys=True); open(m, "a").write("\n")
PY
}
set_manifest_hash() { # <manifest> <relpath> <hash>
  python3 - "$1" "$2" "$3" <<'PY'
import json, sys
m, rel, h = sys.argv[1], sys.argv[2], sys.argv[3]
d = json.load(open(m)); d["files"][rel] = h
json.dump(d, open(m, "w"), indent=2, sort_keys=True); open(m, "a").write("\n")
PY
}
snapshot() { # recursive content snapshot, excluding volatile files + .git
  local dir="$1"
  ( cd "$dir" && find . -type f ! -path './.git/*' ! -name 'adherence.log' \
      | LC_ALL=C sort | while IFS= read -r f; do
      printf '%s:' "$f"; python3 "$MAN_PY" hash "$f"
    done )
}
fresh_install() { # <target>
  local t="$1"; mkdir -p "$t"; git -C "$t" init -q
  bash "$REPO/install.sh" "$t" >/dev/null 2>&1
}
# issue-67 helpers - parsed from the JSON, never hardcoded names.
matcher_present() { # <file> <event> <matcher>
  python3 - "$1" "$2" "$3" <<'PY'
import json, sys
groups = json.load(open(sys.argv[1])).get("hooks", {}).get(sys.argv[2], [])
sys.exit(0 if any(g.get("matcher") == sys.argv[3] for g in groups) else 1)
PY
}
command_matcher_count() { # <file> <event> <substr> -> prints distinct-matcher count
  python3 - "$1" "$2" "$3" <<'PY'
import json, sys
groups = json.load(open(sys.argv[1])).get("hooks", {}).get(sys.argv[2], [])
ms = set()
for g in groups:
    for h in (g.get("hooks") or []):
        if sys.argv[3] in (h.get("command") or ""):
            ms.add(g.get("matcher"))
print(len(ms))
PY
}

# --- 0. manifest.py determinism (the parity tripwire) ---------------------
echo "== manifest.py determinism =="
. "$REPO/lib/payload_paths.sh"
cc_overwrite_relpaths "$REPO" | python3 "$MAN_PY" build --version 1.2.3 --root "$REPO" > "$WORK/m1.json"
cc_overwrite_relpaths "$REPO" | python3 "$MAN_PY" build --version 1.2.3 --root "$REPO" > "$WORK/m2.json"
check "build is byte-identical across runs" cmp -s "$WORK/m1.json" "$WORK/m2.json"
nott  "manifest carries no generated_at"    grep -q "generated_at" "$WORK/m1.json"
nott  "manifest carries no timestamp"        grep -qi "timestamp" "$WORK/m1.json"
check "manifest valid JSON"                  python3 -m json.tool "$WORK/m1.json"
echo "-- vercmp --"
[ "$(python3 "$MAN_PY" vercmp 0.1.1 0.1.2)" = "-1" ] && pass "vercmp older<newer = -1" || fail "vercmp older<newer"
[ "$(python3 "$MAN_PY" vercmp 1.0.0 0.9.9)" = "1" ]  && pass "vercmp newer>older = 1"  || fail "vercmp newer>older"
[ "$(python3 "$MAN_PY" vercmp 2.0 2.0.0)" = "0" ]    && pass "vercmp equal-padded = 0" || fail "vercmp equal-padded"

# --- 1. pristine: install then update -> no drift, no .new, no backup -----
echo "== pristine flow =="
T1="$WORK/t1"; fresh_install "$T1"
check "install wrote the manifest" test -f "$T1/company/state/install-manifest.json"
OUT="$(bash "$REPO/update.sh" "$T1" 2>&1)"; RC=$?
[ "$RC" -eq 0 ] && pass "pristine update exits 0" || fail "pristine update exits 0 (rc=$RC)"
grep -q "already up to date" <<< "$OUT" && pass "reports already up to date" || fail "reports already up to date"
nott "no .new files"       bash -c "find '$T1' -name '*.new' | grep -q ."
nott "no backup dir"       test -d "$T1/company/state/.update-backups"

# --- 2. modified: user edit preserved, .new holds packaged content --------
echo "== modified flow =="
T2="$WORK/t2"; fresh_install "$T2"
AG="$T2/.claude/agents/developer.md"
printf '\nUSER EDIT SENTINEL\n' >> "$AG"
BEFORE="$(hashf "$AG")"
OUT="$(bash "$REPO/update.sh" "$T2" 2>&1)"; RC=$?
[ "$RC" -eq 0 ] && pass "modified update exits 0 (.new is success)" || fail "modified update exits 0 (rc=$RC)"
[ "$BEFORE" = "$(hashf "$AG")" ] && pass "user edit survived byte-for-byte" || fail "user edit survived"
check "developer.md.new created"          test -f "$AG.new"
check ".new holds packaged content"       cmp -s "$AG.new" "$REPO/.claude/agents/developer.md"
nott  ".new does not contain user edit"   grep -q "USER EDIT SENTINEL" "$AG.new"
grep -q "preserved: 1" <<< "$OUT" && pass "report says preserved: 1" || fail "report says preserved: 1"
nott  "no backup dir for a preserved file" test -d "$T2/company/state/.update-backups"

# --- 3. bootstrap: no manifest -> safe mode -------------------------------
echo "== bootstrap (no manifest) flow =="
T3="$WORK/t3"; fresh_install "$T3"
rm -f "$T3/company/state/install-manifest.json"
printf '\nBOOTSTRAP EDIT\n' >> "$T3/.claude/agents/auditor.md"
OUT="$(bash "$REPO/update.sh" "$T3" 2>&1)"; RC=$?
[ "$RC" -eq 0 ] && pass "bootstrap update exits 0" || fail "bootstrap update exits 0 (rc=$RC)"
grep -q "unknown -> " <<< "$OUT" && pass "reports unknown -> version" || fail "reports unknown -> version"
check "edited file preserved to .new"     test -f "$T3/.claude/agents/auditor.md.new"
check "edited file kept its user content"  grep -q "BOOTSTRAP EDIT" "$T3/.claude/agents/auditor.md"
nott  "pristine sibling not clobbered"     test -e "$T3/.claude/agents/architect.md.new"
check "manifest recreated after apply"     test -f "$T3/company/state/install-manifest.json"

# --- 4. --check leaves the tree byte-for-byte unchanged -------------------
echo "== --check dry run =="
T4="$WORK/t4"; fresh_install "$T4"
printf '\nCHECK EDIT\n' >> "$T4/.claude/agents/qa-engineer.md"
SNAP_A="$(snapshot "$T4")"
OUT="$(bash "$REPO/update.sh" "$T4" --check 2>&1)"; RC=$?
SNAP_B="$(snapshot "$T4")"
[ "$RC" -eq 0 ] && pass "--check exits 0" || fail "--check exits 0 (rc=$RC)"
[ "$SNAP_A" = "$SNAP_B" ] && pass "--check leaves tree byte-identical" || fail "--check leaves tree byte-identical"
nott "--check wrote no .new"        bash -c "find '$T4' -name '*.new' | grep -q ."
nott "--check made no backup dir"   test -d "$T4/company/state/.update-backups"
grep -q "PRESERVED .claude/agents/qa-engineer.md" <<< "$OUT" && pass "--check plan flags the drift" || fail "--check plan flags the drift"

# --- 5. updated: tgt == baseline != packaged -> backup then overwrite -----
echo "== updated (pristine-but-stale) flow =="
T5="$WORK/t5"; fresh_install "$T5"
MAN5="$T5/company/state/install-manifest.json"
REL=".claude/agents/tech-lead.md"
printf 'STALE UPSTREAM\n' > "$T5/$REL"
set_manifest_hash "$MAN5" "$REL" "$(hashf "$T5/$REL")"
OUT="$(bash "$REPO/update.sh" "$T5" 2>&1)"; RC=$?
[ "$RC" -eq 0 ] && pass "updated flow exits 0" || fail "updated flow exits 0 (rc=$RC)"
grep -q "updated:   1" <<< "$OUT" && pass "report says updated: 1" || fail "report says updated: 1"
check "stale file overwritten with packaged" cmp -s "$T5/$REL" "$REPO/$REL"
check "backup dir created"                    test -d "$T5/company/state/.update-backups"
BK="$(find "$T5/company/state/.update-backups" -name 'tech-lead.md' | head -1)"
check "backup holds the prior (stale) content" grep -q "STALE UPSTREAM" "$BK"
nott  "no .new for an updated file"            test -e "$T5/$REL.new"

# --- 5b. restored: target file missing -> recreated from the package ------
echo "== restored (missing file) flow =="
T5B="$WORK/t5b"; fresh_install "$T5B"
RELB=".claude/agents/architect.md"
rm -f "$T5B/$RELB"
OUT="$(bash "$REPO/update.sh" "$T5B" 2>&1)"; RC=$?
[ "$RC" -eq 0 ] && pass "restored flow exits 0" || fail "restored flow exits 0 (rc=$RC)"
grep -q "restored:  1" <<< "$OUT" && pass "report says restored: 1" || fail "report says restored: 1"
check "missing file recreated with packaged content" cmp -s "$T5B/$RELB" "$REPO/$RELB"
nott  "no backup dir for a pure restore"             test -d "$T5B/company/state/.update-backups"
nott  "no .new for a restored file"                  test -e "$T5B/$RELB.new"

# --- 6. downgrade guard ---------------------------------------------------
echo "== downgrade guard =="
T6="$WORK/t6"; fresh_install "$T6"
set_manifest_version "$T6/company/state/install-manifest.json" "99.0.0"
bash "$REPO/update.sh" "$T6" >/dev/null 2>"$WORK/dg.err"; RC=$?
[ "$RC" -eq 4 ] && pass "bare downgrade refused (exit 4)" || fail "bare downgrade refused (exit 4, got $RC)"
grep -qi "refus" "$WORK/dg.err" && pass "refusal message printed" || fail "refusal message printed"
bash "$REPO/update.sh" "$T6" --check >/dev/null 2>&1; RC=$?
[ "$RC" -eq 0 ] && pass "--check on downgrade exits 0" || fail "--check on downgrade exits 0 (got $RC)"
bash "$REPO/update.sh" "$T6" --force >/dev/null 2>&1; RC=$?
[ "$RC" -eq 0 ] && pass "--force proceeds (exit 0)" || fail "--force proceeds (got $RC)"

# --- 7. second-run idempotency (all unchanged, no backup dir) -------------
echo "== idempotency =="
T7="$WORK/t7"; fresh_install "$T7"
bash "$REPO/update.sh" "$T7" >/dev/null 2>&1
SNAP_A="$(snapshot "$T7")"
OUT="$(bash "$REPO/update.sh" "$T7" 2>&1)"
SNAP_B="$(snapshot "$T7")"
[ "$SNAP_A" = "$SNAP_B" ] && pass "second run changes nothing" || fail "second run changes nothing"
grep -q "already up to date" <<< "$OUT" && pass "second run: already up to date" || fail "second run: already up to date"
nott "second run makes no backup dir" test -d "$T7/company/state/.update-backups"

# --- 8. user state and config are never touched ---------------------------
echo "== user state / config preserved =="
T8="$WORK/t8"; fresh_install "$T8"
python3 - "$T8/.claude/settings.json" <<'PY'
import json, sys
p = sys.argv[1]; d = json.load(open(p))
d.setdefault("hooks", {}).setdefault("PreToolUse", []).append(
    {"matcher": "Bash", "hooks": [{"type": "command", "command": "my-own-user-hook.sh"}]})
json.dump(d, open(p, "w"), indent=2); open(p, "a").write("\n")
PY
printf '{"gates":[{"name":"mine","command":"echo hi","blocking":true}]}\n' > "$T8/company/gates.config"
mkdir -p "$T8/company/specs"; printf '# my spec\n' > "$T8/company/specs/spec-mine.md"
printf '# STATUS\nRED: mine\n' > "$T8/company/state/STATUS.md"
GH="$(hashf "$T8/company/gates.config")"; SH="$(hashf "$T8/company/specs/spec-mine.md")"; TH="$(hashf "$T8/company/state/STATUS.md")"
bash "$REPO/update.sh" "$T8" >/dev/null 2>&1; RC=$?
[ "$RC" -eq 0 ] && pass "update over user state exits 0" || fail "update over user state exits 0 (rc=$RC)"
check "settings.json still valid JSON"     python3 -m json.tool "$T8/.claude/settings.json"
check "user settings hook survived merge"  grep -q "my-own-user-hook.sh" "$T8/.claude/settings.json"
check "company hook still present"          grep -q "guard_" "$T8/.claude/settings.json"
[ "$GH" = "$(hashf "$T8/company/gates.config")" ] && pass "gates.config untouched" || fail "gates.config untouched"
[ "$SH" = "$(hashf "$T8/company/specs/spec-mine.md")" ] && pass "user spec untouched" || fail "user spec untouched"
[ "$TH" = "$(hashf "$T8/company/state/STATUS.md")" ] && pass "user STATUS.md untouched" || fail "user STATUS.md untouched"
nott "no .new for gates.config"            test -e "$T8/company/gates.config.new"

# --- 9. provenance.json: update never arms, only informs (issue-64) -------
echo "== provenance.json never-arm rule =="
# 9a. target WITHOUT provenance.json -> update does NOT create it, prints the
# single notice line once, and counts nothing for it.
T9="$WORK/t9"; fresh_install "$T9"
rm -f "$T9/company/provenance.json"
OUT="$(bash "$REPO/update.sh" "$T9" 2>&1)"; RC=$?
[ "$RC" -eq 0 ] && pass "update without provenance exits 0" || fail "update without provenance exits 0 (rc=$RC)"
nott "provenance.json NOT created" test -f "$T9/company/provenance.json"
nott "no provenance.json.new" test -f "$T9/company/provenance.json.new"
[ "$(printf '%s\n' "$OUT" | grep -c "delegation enforcer installed but disarmed")" -eq 1 ] \
  && pass "notice line printed exactly once" || fail "notice line printed exactly once"
# same in --check mode
OUT="$(bash "$REPO/update.sh" "$T9" --check 2>&1)"; RC=$?
[ "$RC" -eq 0 ] && pass "--check without provenance exits 0" || fail "--check without provenance exits 0 (rc=$RC)"
grep -q "delegation enforcer installed but disarmed" <<< "$OUT" \
  && pass "--check prints the notice too" || fail "--check prints the notice too"
nott "--check still did not create provenance.json" test -f "$T9/company/provenance.json"

# 9b. target WITH a modified provenance.json -> left byte-identical, no .new,
# no backup, no notice.
T10="$WORK/t10"; fresh_install "$T10"
printf '{"version": 1, "verifier_roles": ["auditor"], "builder_roles": ["developer"], "USER": "EDIT"}\n' > "$T10/company/provenance.json"
PH="$(hashf "$T10/company/provenance.json")"
OUT="$(bash "$REPO/update.sh" "$T10" 2>&1)"; RC=$?
[ "$RC" -eq 0 ] && pass "update with present provenance exits 0" || fail "update with present provenance exits 0 (rc=$RC)"
[ "$PH" = "$(hashf "$T10/company/provenance.json")" ] && pass "modified provenance.json untouched" || fail "modified provenance.json untouched"
nott "no provenance.json.new when present" test -e "$T10/company/provenance.json.new"
nott "no backup dir for present provenance" test -d "$T10/company/state/.update-backups"
if grep -q 'delegation enforcer installed but disarmed' <<< "$OUT"; then
  fail "no notice when provenance present"
else
  pass "no notice when provenance present"
fi

# --- 10. settings.json merge: no churn on pristine, heals dropped groups ---
echo "== settings.json merge heal (issue-67) =="
# 10a. a pristine settings.json passes through update byte-identical (the merge
# is a true no-op, no MERGED churn) - proves the (matcher, command) dedup is
# idempotent against an already-correct file.
T11="$WORK/t11"; fresh_install "$T11"
SBEFORE="$(hashf "$T11/.claude/settings.json")"
OUT="$(bash "$REPO/update.sh" "$T11" 2>&1)"; RC=$?
[ "$RC" -eq 0 ] && pass "update over pristine settings exits 0" || fail "update over pristine settings exits 0 (rc=$RC)"
[ "$SBEFORE" = "$(hashf "$T11/.claude/settings.json")" ] && pass "pristine settings.json unchanged by update" || fail "pristine settings.json unchanged by update"

# 10b. a 0.2.0-style dropped-group settings.json is HEALED by update. Simulate
# the exact field damage the old command-per-event dedup caused: the whole
# Task|Agent PreToolUse group vanished and Bash lost guard_tests.
T12="$WORK/t12"; fresh_install "$T12"
python3 - "$T12/.claude/settings.json" <<'PY'
import json, sys
p = sys.argv[1]; d = json.load(open(p))
newpre = []
for g in d["hooks"]["PreToolUse"]:
    m = g.get("matcher")
    if m == "Task|Agent":
        continue  # whole group vanished in the field
    if m == "Bash":
        g = dict(g)
        g["hooks"] = [h for h in g["hooks"]
                      if "guard_tests" not in (h.get("command") or "")]
    newpre.append(g)
d["hooks"]["PreToolUse"] = newpre
json.dump(d, open(p, "w"), indent=2); open(p, "a").write("\n")
PY
nott "corrupted file really lost Task|Agent group" matcher_present "$T12/.claude/settings.json" PreToolUse "Task|Agent"
OUT="$(bash "$REPO/update.sh" "$T12" 2>&1)"; RC=$?
[ "$RC" -eq 0 ] && pass "heal update exits 0" || fail "heal update exits 0 (rc=$RC)"
check "healed: Task|Agent PreToolUse group restored" matcher_present "$T12/.claude/settings.json" PreToolUse "Task|Agent"
[ "$(command_matcher_count "$T12/.claude/settings.json" PreToolUse guard_models)" -ge 1 ] \
  && pass "healed: guard_models present under PreToolUse" || fail "healed: guard_models present under PreToolUse"
[ "$(command_matcher_count "$T12/.claude/settings.json" PreToolUse guard_provenance)" -eq 0 ] \
  && pass "healed: guard_provenance stays unwired" || fail "healed: guard_provenance stays unwired"
[ "$(command_matcher_count "$T12/.claude/settings.json" PreToolUse guard_tests)" -eq 2 ] \
  && pass "healed: guard_tests back under both its matchers" || fail "healed: guard_tests fanout == 2"
check "healed settings.json still valid JSON" python3 -m json.tool "$T12/.claude/settings.json"
# a re-run after heal must settle: no further settings churn
SAFTER="$(hashf "$T12/.claude/settings.json")"
bash "$REPO/update.sh" "$T12" >/dev/null 2>&1
[ "$SAFTER" = "$(hashf "$T12/.claude/settings.json")" ] && pass "healed settings.json stable on next update" || fail "healed settings.json stable on next update"

# --- 10c. settings.json env merge: spawn-depth ships + user pin survives ----
# Claude Code 2.1.21 defaulted CLAUDE_CODE_MAX_SUBAGENT_SPAWN_DEPTH to 1,
# flattening the org. The settings template ships it at "2" and both engines
# merge env additively: absent -> added, user-pinned -> never overwritten,
# second run -> no churn. Same byte-identical merge as install.sh (section 5).
echo "== settings.json env merge (spawn-depth) =="
env_depth() { python3 -c 'import json,sys
print(json.load(open(sys.argv[1])).get("env",{}).get("CLAUDE_CODE_MAX_SUBAGENT_SPAWN_DEPTH",""))' "$1"; }

# fresh install carries the env var at "2"
T15="$WORK/t15"; fresh_install "$T15"
[ "$(env_depth "$T15/.claude/settings.json")" = "2" ] \
  && pass "fresh install ships spawn-depth env = 2" || fail "fresh install ships spawn-depth env = 2"

# a settings.json that predates the env block gains the key on update
T16="$WORK/t16"; fresh_install "$T16"
python3 - "$T16/.claude/settings.json" <<'PY'
import json, sys
p = sys.argv[1]; d = json.load(open(p)); d.pop("env", None)
json.dump(d, open(p, "w"), indent=2); open(p, "a").write("\n")
PY
[ -z "$(env_depth "$T16/.claude/settings.json")" ] && pass "precondition: env stripped" || fail "precondition: env stripped"
bash "$REPO/update.sh" "$T16" >/dev/null 2>&1; RC=$?
[ "$RC" -eq 0 ] && pass "update over env-less settings exits 0" || fail "update over env-less settings exits 0 (rc=$RC)"
[ "$(env_depth "$T16/.claude/settings.json")" = "2" ] && pass "update adds spawn-depth env = 2" || fail "update adds spawn-depth env = 2"
check "healed env settings still valid JSON" python3 -m json.tool "$T16/.claude/settings.json"
[ "$(command_matcher_count "$T16/.claude/settings.json" PreToolUse guard_models)" -ge 1 ] \
  && pass "guard_models fanout intact after env merge" || fail "guard_models fanout intact after env merge"
# re-run must settle byte-identical (no churn)
SENV_AFTER="$(hashf "$T16/.claude/settings.json")"
bash "$REPO/update.sh" "$T16" >/dev/null 2>&1
[ "$SENV_AFTER" = "$(hashf "$T16/.claude/settings.json")" ] && pass "env settings stable on next update" || fail "env settings stable on next update"

# a user-pinned depth "3" survives update, and a user env key is untouched
T17="$WORK/t17"; fresh_install "$T17"
python3 - "$T17/.claude/settings.json" <<'PY'
import json, sys
p = sys.argv[1]; d = json.load(open(p)); d.setdefault("env", {})
d["env"]["CLAUDE_CODE_MAX_SUBAGENT_SPAWN_DEPTH"] = "3"
d["env"]["MY_OWN_VAR"] = "keep"
json.dump(d, open(p, "w"), indent=2); open(p, "a").write("\n")
PY
bash "$REPO/update.sh" "$T17" >/dev/null 2>&1; RC=$?
[ "$RC" -eq 0 ] && pass "update over user-pinned depth exits 0" || fail "update over user-pinned depth exits 0 (rc=$RC)"
[ "$(env_depth "$T17/.claude/settings.json")" = "3" ] && pass "user-pinned depth 3 survives update" || fail "user-pinned depth 3 survives update"
check "user env key preserved" grep -q "MY_OWN_VAR" "$T17/.claude/settings.json"

# install-over-existing shares the byte-identical merge: never overwrites a user pin
T18="$WORK/t18"; fresh_install "$T18"
python3 - "$T18/.claude/settings.json" <<'PY'
import json, sys
p = sys.argv[1]; d = json.load(open(p))
d.setdefault("env", {})["CLAUDE_CODE_MAX_SUBAGENT_SPAWN_DEPTH"] = "3"
json.dump(d, open(p, "w"), indent=2); open(p, "a").write("\n")
PY
bash "$REPO/install.sh" "$T18" >/dev/null 2>&1; RC=$?
[ "$RC" -eq 0 ] && pass "re-install over user-pinned depth exits 0" || fail "re-install over user-pinned depth exits 0 (rc=$RC)"
[ "$(env_depth "$T18/.claude/settings.json")" = "3" ] && pass "re-install keeps user-pinned depth 3" || fail "re-install keeps user-pinned depth 3"

# --- 11. record trees: user records untouched, empty dirs restored (issue-68) -
echo "== record trees never import our records (issue-68) =="
# 11a. a project with its OWN specs/briefs/CRs: update leaves each byte-identical
# and never adds this package's records alongside them.
T13="$WORK/t13"; fresh_install "$T13"
mkdir -p "$T13/company/specs" "$T13/company/briefs" "$T13/company/change-requests"
printf '# their spec\n'  > "$T13/company/specs/spec-theirs.md"
printf '# their brief\n' > "$T13/company/briefs/brief-theirs.md"
printf '# their CR\n'    > "$T13/company/change-requests/CR-theirs.md"
SPH="$(hashf "$T13/company/specs/spec-theirs.md")"
BRH="$(hashf "$T13/company/briefs/brief-theirs.md")"
CRH="$(hashf "$T13/company/change-requests/CR-theirs.md")"
OUT="$(bash "$REPO/update.sh" "$T13" 2>&1)"; RC=$?
[ "$RC" -eq 0 ] && pass "update over user records exits 0" || fail "update over user records exits 0 (rc=$RC)"
[ "$SPH" = "$(hashf "$T13/company/specs/spec-theirs.md")" ] && pass "user spec untouched" || fail "user spec untouched"
[ "$BRH" = "$(hashf "$T13/company/briefs/brief-theirs.md")" ] && pass "user brief untouched" || fail "user brief untouched"
[ "$CRH" = "$(hashf "$T13/company/change-requests/CR-theirs.md")" ] && pass "user CR untouched" || fail "user CR untouched"
# the package's own records (present in $REPO/company/{specs,briefs}) must NOT appear
nott "no package brief imported" bash -c "ls '$T13/company/briefs/shipped'/brief-*.md >/dev/null 2>&1"
nott "no package spec imported"  bash -c "ls '$T13/company/specs/shipped'/spec-*.md >/dev/null 2>&1"
# only the user's single record exists in each tree
[ "$(find "$T13/company/briefs" -name 'brief-*.md' | wc -l | tr -d ' ')" = "1" ] \
  && pass "briefs tree holds only the user record" || fail "briefs tree holds only the user record"

# 11b. a missing record dir is restored EMPTY by update - never repopulated with
# our records.
T14="$WORK/t14"; fresh_install "$T14"
rm -rf "$T14/company/briefs" "$T14/company/specs/shipped"
OUT="$(bash "$REPO/update.sh" "$T14" 2>&1)"; RC=$?
[ "$RC" -eq 0 ] && pass "update restoring dirs exits 0" || fail "update restoring dirs exits 0 (rc=$RC)"
check "missing briefs dir recreated"        test -d "$T14/company/briefs"
check "missing briefs/shipped recreated"    test -d "$T14/company/briefs/shipped"
check "missing specs/shipped recreated"     test -d "$T14/company/specs/shipped"
nott  "recreated briefs dir is empty of records" bash -c "find '$T14/company/briefs' -name 'brief-*.md' | grep -q ."
nott  "recreated specs/shipped empty of records" bash -c "find '$T14/company/specs/shipped' -name 'spec-*.md' | grep -q ."

# --- 12. models.json builtins injection (FR-MRA-14) -----------------------
# Traceability: FR-MRA-09 (install.sh merge) and FR-MRA-10 (update.sh merge
# via the FR-UPD-08 finalize_merge infrastructure); BR-MRA-05 write-only-when-
# injecting; BR-MRA-06 value preservation of roles/pricing/version/user keys.
# update injects the packaged template's `builtins` into a manifest that
# predates the section, preserving every other value, and is idempotent.
echo "== models.json builtins injection (FR-MRA-14) =="
mj_has_builtins() { # <file> -> 0 if a builtins object is present
  python3 -c 'import json,sys; sys.exit(0 if isinstance(json.load(open(sys.argv[1])).get("builtins"),dict) else 1)' "$1"
}
mj_get() { # <file> <key...> -> canonical JSON of the nested value
  python3 -c 'import json,sys
v=json.load(open(sys.argv[1]))
for k in sys.argv[2:]: v=v[k]
print(json.dumps(v,sort_keys=True))' "$@"
}

# 12a. builtins STRIPPED + a custom top-level key -> injected, all else kept,
# prior file backed up.
TM1="$WORK/tm1"; fresh_install "$TM1"
MJ="$TM1/company/models.json"
python3 - "$MJ" <<'PY'
import json, sys
p = sys.argv[1]; d = json.load(open(p))
d.pop("builtins", None)            # strip the section update must re-inject
d["myTeamKey"] = {"keep": "me"}    # a custom top-level key update must preserve
json.dump(d, open(p, "w"), indent=2, sort_keys=False); open(p, "a").write("\n")
PY
ROLES_BEFORE="$(mj_get "$MJ" roles)"
PRICING_BEFORE="$(mj_get "$MJ" pricing)"
VERSION_BEFORE="$(mj_get "$MJ" version)"
CUSTOM_BEFORE="$(mj_get "$MJ" myTeamKey)"
nott "precondition: builtins stripped" mj_has_builtins "$MJ"
OUT="$(bash "$REPO/update.sh" "$TM1" 2>&1)"; RC=$?
[ "$RC" -eq 0 ] && pass "inject flow exits 0" || fail "inject flow exits 0 (rc=$RC)"
check "builtins injected"           mj_has_builtins "$MJ"
[ "$(mj_get "$MJ" roles)"   = "$ROLES_BEFORE" ]   && pass "roles preserved"   || fail "roles preserved"
[ "$(mj_get "$MJ" pricing)" = "$PRICING_BEFORE" ] && pass "pricing preserved" || fail "pricing preserved"
[ "$(mj_get "$MJ" version)" = "$VERSION_BEFORE" ] && pass "version preserved" || fail "version preserved"
[ "$(mj_get "$MJ" myTeamKey)" = "$CUSTOM_BEFORE" ] && pass "custom key value preserved" || fail "custom key value preserved"
# injected builtins equal the packaged template's builtins (read, never hardcoded)
[ "$(mj_get "$MJ" builtins)" = "$(mj_get "$REPO/company/models.json" builtins)" ] \
  && pass "injected builtins match packaged template" || fail "injected builtins match packaged template"
check "backup dir created"          test -d "$TM1/company/state/.update-backups"
BKM="$(find "$TM1/company/state/.update-backups" -name 'models.json' | head -1)"
[ -n "$BKM" ] && pass "backup holds the prior models.json" || fail "backup holds the prior models.json"
nott "backup copy has no builtins (it is the pre-inject file)" mj_has_builtins "$BKM"
nott "no .new for models.json"      test -e "$MJ.new"

# 12b. a SECOND update leaves models.json byte-unchanged and writes no new backup.
H_AFTER1="$(hashf "$MJ")"
N_BK_BEFORE="$(find "$TM1/company/state/.update-backups" -name 'models.json' | wc -l | tr -d ' ')"
bash "$REPO/update.sh" "$TM1" >/dev/null 2>&1; RC=$?
[ "$RC" -eq 0 ] && pass "second update exits 0" || fail "second update exits 0 (rc=$RC)"
[ "$H_AFTER1" = "$(hashf "$MJ")" ] && pass "second update leaves models.json byte-unchanged" || fail "second update leaves models.json byte-unchanged"
N_BK_AFTER="$(find "$TM1/company/state/.update-backups" -name 'models.json' | wc -l | tr -d ' ')"
[ "$N_BK_BEFORE" = "$N_BK_AFTER" ] && pass "second update writes no new models.json backup" || fail "second update writes no new models.json backup"

# 12c. models.json DELETED -> restored via config-if-absent (template already
# carries builtins) and the merge no-ops.
TM3="$WORK/tm3"; fresh_install "$TM3"
MJ3="$TM3/company/models.json"
rm -f "$MJ3"
bash "$REPO/update.sh" "$TM3" >/dev/null 2>&1; RC=$?
[ "$RC" -eq 0 ] && pass "restore flow exits 0" || fail "restore flow exits 0 (rc=$RC)"
check "models.json restored"                test -f "$MJ3"
check "restored models.json valid JSON"     python3 -m json.tool "$MJ3"
check "restored models.json has builtins"   mj_has_builtins "$MJ3"
check "restored equals packaged template"   cmp -s "$MJ3" "$REPO/company/models.json"
nott  "no .new for a restored models.json"  test -e "$MJ3.new"

# --- 13. legacy field install survives an update (FR-MST-29, BR-MST-11) ----
# The field rollout proof. An install made before multi-session tasks carries a
# LEGACY SINGLE-OBJECT active-task.json and a V1 provenance ledger. After an
# update: the new normalizer reads both old shapes and blocks nothing, and the
# customer's task state is never rewritten, created or deleted.
#
# Every hook here is driven from the TARGET's installed copy, not from $REPO -
# what the update actually delivered into the customer install is the thing
# under test.
echo "== legacy shapes survive an update (FR-MST-29 / BR-MST-11) =="
seal_ledger() { # <ledger-file> - seal it the way the hooks seal it. The salt and
                # the canonical form come from the real _common.stamp_checksum,
                # never a copy, so this fixture cannot drift from the hooks.
  python3 - "$REPO/.claude/hooks" "$1" <<'PY'
import json, sys
sys.path.insert(0, sys.argv[1])
import _common as c
p = sys.argv[2]
d = json.load(open(p))
d.pop("checksum", None)
d["checksum"] = c.stamp_checksum(d)
json.dump(d, open(p, "w"))
PY
}
mtime_ns() { python3 -c 'import os,sys; print(os.stat(sys.argv[1]).st_mtime_ns)' "$1"; }
run_hook() { # <target> <hook.py> <abs-file-path> -> returns the hook's exit code
  local t="$1" hook="$2" fp="$3"
  printf '{"hook_event_name":"PreToolUse","tool_name":"Write","cwd":"%s","tool_input":{"file_path":"%s"}}' "$t" "$fp" \
    | CLAUDE_PROJECT_DIR="$t" python3 "$t/.claude/hooks/$hook" >/dev/null 2>&1
}

T19="$WORK/t19"; fresh_install "$T19"
AT="$T19/company/state/active-task.json"
# the pre-multi-session shape: ONE task object, not a list.
cat > "$AT" <<'JSON'
{"task": "legacy-x", "type": "feature", "brief": "company/briefs/brief-legacy-x.md", "test_scope": false, "execution": "delegated", "execution_why": "tech-lead owns the build"}
JSON
printf '# brief for legacy-x\n' > "$T19/company/briefs/brief-legacy-x.md"
# a v1 ledger for that slug carrying the dispatch that satisfies its delegated
# decision. The checksum is stamped the way the hooks stamp it - an unsealed
# ledger would be read as tampered and reset, which would make this case
# vacuous. The tamper control below proves the sealed one is really read.
cat > "$T19/company/state/provenance-ledger.json" <<'JSON'
{"version": 1, "task": "legacy-x", "self_authored": [], "audits": [], "dispatches": [{"role": "tech-lead", "at": "2026-01-01T00:00:00Z"}], "nudge_state": null}
JSON
seal_ledger "$T19/company/state/provenance-ledger.json"
cp "$AT" "$WORK/legacy-active-task.before"
AT_MTIME_BEFORE="$(mtime_ns "$AT")"
LEDGER_BEFORE="$(hashf "$T19/company/state/provenance-ledger.json")"

OUT="$(bash "$REPO/update.sh" "$T19" 2>&1)"; RC=$?
[ "$RC" -eq 0 ] && pass "update over a legacy install exits 0" || fail "update over a legacy install exits 0 (rc=$RC)"
# 13a. update never rewrites, creates or deletes the task state: same bytes,
# same mtime, no .new, no backup copy.
check "legacy active-task.json still present"        test -f "$AT"
check "legacy active-task.json byte-identical"       cmp -s "$WORK/legacy-active-task.before" "$AT"
[ "$AT_MTIME_BEFORE" = "$(mtime_ns "$AT")" ] \
  && pass "legacy active-task.json mtime unchanged" || fail "legacy active-task.json mtime unchanged"
nott "no active-task.json.new"        test -e "$AT.new"
nott "no active-task.json backed up"  bash -c "find '$T19/company/state/.update-backups' -name 'active-task.json' 2>/dev/null | grep -q ."
[ "$LEDGER_BEFORE" = "$(hashf "$T19/company/state/provenance-ledger.json")" ] \
  && pass "v1 provenance ledger byte-unchanged by update" || fail "v1 provenance ledger byte-unchanged by update"

# 13b. guard_spec does not spuriously block a source edit on the legacy
# shapes: it allows only because it read the single object as one entry AND
# resolved that entry's brief; the empty case blocks (see the control below).
LEGACY_EDIT="$T19/src/app.py"
run_hook "$T19" guard_spec.py "$LEGACY_EDIT"; RC=$?
[ "$RC" -eq 0 ] && pass "guard_spec allows a source edit on a legacy install" || fail "guard_spec allows a source edit on a legacy install (rc=$RC)"
# The guard_provenance leg here used to drive Mode E, the PreToolUse Edit
# execution gate. That gate was deleted unfired (issue #120), so a Write
# payload can no longer return anything but 0 and an rc assertion on it would
# pass vacuously forever. The SUBJECT it was really testing survives and is
# worth keeping: that this INSTALLED tree, after update.sh ran over it, still
# reads its own sealed v1 ledger through migrate_v1. That is an install
# integration fact the hooks suite cannot reach - the hooks suite proves
# migrate_v1 in isolation, this proves the updated install did not break it.
# So the observable moves from an exit code to the migrated ledger itself.
legacy_dispatches() { # <target> -> dispatches migrate_v1 credits to legacy-x
  python3 - "$1" <<'PY'
import os, sys
t = sys.argv[1]
sys.path.insert(0, os.path.join(t, ".claude", "hooks"))
os.environ["CLAUDE_PROJECT_DIR"] = t
import dispatch_feed as gp
print(len(gp.dispatches_for(gp.read_ledger(t), "legacy-x")))
PY
}
[ "$(legacy_dispatches "$T19")" = "1" ] \
  && pass "migrate_v1 credits the sealed v1 ledger's dispatch after update" \
  || fail "migrate_v1 credits the sealed v1 ledger's dispatch after update (got $(legacy_dispatches "$T19"))"

# 13c. controls - both allows above are real decisions, not silent fail-opens.
mv "$AT" "$WORK/legacy-active-task.hidden"
run_hook "$T19" guard_spec.py "$LEGACY_EDIT"; RC=$?
[ "$RC" -eq 2 ] && pass "control: guard_spec blocks that same edit with no task file" || fail "control: guard_spec blocks that same edit with no task file (rc=$RC)"
mv "$WORK/legacy-active-task.hidden" "$AT"
python3 - "$T19/company/state/provenance-ledger.json" <<'PY'
import json, sys
p = sys.argv[1]; d = json.load(open(p)); d["checksum"] = "0" * 64
json.dump(d, open(p, "w"))
PY
[ "$(legacy_dispatches "$T19")" = "0" ] \
  && pass "control: an unsealed v1 ledger credits nothing, so the sealed one was read" \
  || fail "control: an unsealed v1 ledger credits nothing, so the sealed one was read (got $(legacy_dispatches "$T19"))"

# 13d. BR-MST-11: active-task.json is untracked and unscaffolded. Neither
# install nor update ever brings one into existence.
T20="$WORK/t20"; fresh_install "$T20"
nott "fresh install creates no active-task.json"   test -e "$T20/company/state/active-task.json"
nott "active-task.json absent from the manifest"   grep -q "active-task.json" "$T20/company/state/install-manifest.json"
bash "$REPO/update.sh" "$T20" >/dev/null 2>&1; RC=$?
[ "$RC" -eq 0 ] && pass "update with no active-task.json exits 0" || fail "update with no active-task.json exits 0 (rc=$RC)"
nott "update creates no active-task.json"          test -e "$T20/company/state/active-task.json"
nott "update creates no active-task.json.new"      test -e "$T20/company/state/active-task.json.new"

echo
echo "================ SUMMARY ================"
printf 'PASS: %d   FAIL: %d\n' "$PASS" "$FAIL"
[ "$FAIL" -eq 0 ] && { echo "ALL GREEN"; exit 0; } || { echo "TESTS FAILED"; exit 1; }
