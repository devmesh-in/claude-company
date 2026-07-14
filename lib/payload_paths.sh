# lib/payload_paths.sh - the single source of truth for the install overwrite
# set. Sourced (never executed) by install.sh and by the future update
# command so both agree, byte for byte, on which files the installer copies in
# place via copy_overwrite / copy_tree_overwrite.
#
# Works on macOS bash 3.2: no associative arrays, no readarray, no mapfile.
#
# cc_overwrite_relpaths SRC_ROOT
#   Prints, newline-delimited and LC_ALL=C sorted, the SRC_ROOT-relative paths
#   (no leading "./") of exactly the files install.sh overwrites in place.
#   Only paths that actually exist under SRC_ROOT are emitted.

cc_overwrite_relpaths() {
  local src_root d f p
  src_root="$1"
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
