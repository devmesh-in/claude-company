# lib/payload_paths.sh - the single source of truth for the install overwrite
# set. Sourced (never executed) by install.sh and by the future update
# command so both agree, byte for byte, on which files the installer copies in
# place via copy_overwrite / copy_tree_overwrite.
#
# Works on macOS bash 3.2: no associative arrays, no readarray, no mapfile.
#
# cc_overwrite_relpaths SRC_ROOT [HARNESSES]
#   Prints, newline-delimited and LC_ALL=C sorted, the SRC_ROOT-relative paths
#   (no leading "./") of exactly the files install.sh overwrites in place.
#   Only paths that actually exist under SRC_ROOT are emitted.
#
#   HARNESSES is a comma-separated selection, default "claude". The .opencode
#   tree is part of the overwrite set ONLY when opencode is selected, because
#   the manifest must describe what was actually installed: listing files a
#   claude-only install never received would put `update` into safe mode for
#   paths that were never meant to be there.
#
#   The default is deliberately "claude" and not "everything present": an
#   existing scripted `bash install.sh /path` must keep producing exactly the
#   install it produced before opencode support existed.

cc_overwrite_relpaths() {
  local src_root harnesses d f p
  src_root="$1"
  harnesses="${2:-claude}"
  {
    # Overwritten trees - mirror copy_tree_overwrite: every non-pyc file,
    # excluding __pycache__ caches (not just *.py).
    for d in \
      "$src_root/.claude/agents" \
      "$src_root/.claude/hooks" \
      "$src_root/.claude/skills" \
      "$src_root/company/templates"
    do
      if [ -d "$d" ]; then
        find "$d" -type f -not -path '*/__pycache__/*' -not -name '*.pyc' -print
      fi
    done

    # The opencode adapter, generated agents and generated commands. Present
    # in the overwrite set only when that harness was selected.
    case ",$harnesses," in
      *,opencode,*)
        for d in \
          "$src_root/.opencode/agent" \
          "$src_root/.opencode/command" \
          "$src_root/.opencode/lib" \
          "$src_root/.opencode/plugin"
        do
          if [ -d "$d" ]; then
            find "$d" -type f -not -path '*/node_modules/*' -print
          fi
        done
        for f in \
          "$src_root/.opencode/opencode.json" \
          "$src_root/.opencode/package.json"
        do
          if [ -f "$f" ]; then printf '%s\n' "$f"; fi
        done
        ;;
    esac

    # Overwritten singletons - mirror copy_overwrite, only if they exist.
    for f in \
      "$src_root/ORCHESTRATOR.md" \
      "$src_root/company/METHOD.md" \
      "$src_root/company/GATES.md" \
      "$src_root/company/EXTENDING.md" \
      "$src_root/company/IDEATION.md" \
      "$src_root/company/GIT.md" \
      "$src_root/company/LOOPS.md" \
      "$src_root/company/run-gates.sh"
    do
      if [ -f "$f" ]; then
        printf '%s\n' "$f"
      fi
    done
  } | while IFS= read -r p; do
    printf '%s\n' "${p#$src_root/}"
  done | LC_ALL=C sort
}

# wire_background_subagents_env ENABLE_RC
#
# Make OPENCODE_EXPERIMENTAL_BACKGROUND_SUBAGENTS=true visible to every way a
# user might launch opencode. The flag is read from the process environment
# BEFORE the opencode process starts - neither .opencode/opencode.json nor a
# plugin can enable it later (verified live 2026-08-24 against real opencode
# 1.18.21: the task tool schema is built without the background parameter, and
# no config-file or CLI spelling flips it).
#
# Three launch contexts, each best-effort and idempotent:
#   1. Terminal launches: export into the shell rc (ENABLE_RC=1; install's
#      --no-background-subagents-env passes 0 to skip the whole wiring).
#   2. GUI-spawned processes on macOS (desktop app, editor extensions launched
#       from Dock/Spotlight) never read an rc file: launchctl setenv covers the
#      current GUI login. NOTE: it does not survive a reboot; re-running the
#      installer refreshes it.
#   3. WSL checkouts driven by an opencode installed on the Windows side: the
#      Windows user environment is set through PowerShell interop when it is
#      reachable from PATH (interop is often disabled; then this is a no-op).
#
# Every failure warns and moves on - this is a convenience and must never fail
# an install or update. Shared here so install and update can never drift;
# same reasoning as cc_overwrite_relpaths above.
wire_background_subagents_env() {
  local enable_rc="$1" var rc
  # ENABLE_RC=0 is a full opt-out (--no-background-subagents-env): none of the
  # three branches may touch the machine, not just the rc write.
  [ "$enable_rc" = "1" ] || return 0
  var="OPENCODE_EXPERIMENTAL_BACKGROUND_SUBAGENTS"
  case "${SHELL##*/}" in
    zsh)  rc="$HOME/.zshrc"  ;;
    bash) rc="$HOME/.bashrc" ;;
    *)    rc="$HOME/.profile" ;;
  esac
  # Guard on the exact active line, not the bare variable name: a comment
  # mentioning it must not read as "already wired" - that failure mode is
  # invisible capability loss.
  if grep -qs "^export $var=true" "$rc"; then
    skip "background-subagents env already present in ${rc#$HOME/}"
  else
    {
      printf '\n'
      printf '# claude-company: background subagent tasks for opencode\n'
      printf 'export %s=true\n' "$var"
    } >> "$rc" 2>/dev/null && \
      ok "export $var=true added to ${rc#$HOME/}" ||
      warn "could not write to $rc - add 'export $var=true' yourself before running opencode"
  fi
  if [ "$(uname -s)" = "Darwin" ] && command -v launchctl >/dev/null 2>&1; then
    if launchctl setenv "$var" true >/dev/null 2>&1; then
      ok "GUI-launched opencode covered for this login (launchctl setenv)"
    else
      warn "launchctl setenv failed - GUI-launched opencode will not see background subagents until a terminal exports them"
    fi
  fi
  if command -v powershell.exe >/dev/null 2>&1; then
    # Under WSL: reach the Windows-side user environment so an opencode run
    # from Windows against this checkout inherits the flag too. New Windows
    # processes only pick it up after they are restarted.
    if powershell.exe -NoProfile -Command "[Environment]::SetEnvironmentVariable('$var','true','User')" >/dev/null 2>&1; then
      ok "Windows user environment updated (restart Windows shells to inherit)"
    else
      warn "could not update the Windows user environment - set $var=true in Windows yourself if you run opencode there"
    fi
  fi
}
