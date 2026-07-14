"use strict";

// update.js - the `claude-company update` driver. A plain, non-interactive
// Node front end over update.sh (the engine). Where install-tui.js is a rich
// TUI over install.sh, update has no TUI by design (OQ-UPD-05): a refresh is a
// mechanical file-disposition pass, so it always runs plain and lets the engine
// decide every file's fate (keep, replace with backup, or land beside as .new).
//
// This driver only does the parts install already knows how to do - preflight
// the machine and validate the target - then hands the resolved target to
// update.sh and returns its exit code verbatim. It reuses install-tui's shared
// preflight/target surfaces rather than forking them.
//
// Node >= 16, stdlib only. ASCII punctuation in strings.

const path = require("path");
const { spawnSync } = require("child_process");

const S = require("./install-tui.js")._shared;

const ROOT = path.join(__dirname, "..");
const UPDATE_SH = path.join(ROOT, "update.sh");

// Engine exit code returned when we cannot even spawn bash to run update.sh.
// The engine itself uses 3 for a hard write failure; a spawn failure is the
// closest local equivalent (nothing was written).
const EXIT_ENGINE_SPAWN = 3;

// --------------------------------------------------------------------------
// Help
// --------------------------------------------------------------------------

function helpText() {
  return [
    "Update an installed claude-company project - refresh the shipped files.",
    "",
    "Usage:",
    "  claude-company update [TARGET] [options]",
    "",
    "Refreshes claude-company's own files (agents, hooks, skills, canon docs)",
    "in a project that already ran install. It NEVER overwrites a file you",
    "customized: your edit stays and the new upstream version lands beside it",
    "as <file>.new for you to reconcile. The run still exits 0 when that",
    "happens. Anything it does replace is backed up first to",
    "company/state/.update-backups/<timestamp>/.",
    "",
    "Options:",
    "  --target DIR         Target project directory (must already exist).",
    "  --check              Print the plan and write nothing.",
    "  --force              Override a downgrade (installed version is newer).",
    "  -y, --yes            Accepted for parity; update is always plain (no-op).",
    "  --plain              Accepted for parity; update is always plain (no-op).",
    "  --no-color           Monochrome output (NO_COLOR is honored too).",
    "  -h, --help           Show this help.",
    "",
    "Examples:",
    "  claude-company update /path/to/your/project",
    "  npx claude-company update . --check",
    "",
    "Exit codes: 0 ok (even when a conflict became <file>.new), 1 usage,",
    "2 preflight/target hard-fail, 3 write failure, 4 downgrade refused.",
  ].join("\n");
}

// --------------------------------------------------------------------------
// Argument parsing
// --------------------------------------------------------------------------

// Mirrors install-tui.parseArgs in shape and `--` handling. update-specific
// flags: --check and --force are real; -y/--yes and --plain are accepted no-ops
// so the flag surface matches install for muscle memory.
function parseArgs(argv) {
  const args = {
    positional: null,
    target: null,
    yes: false,
    plain: false,
    noColor: false,
    check: false,
    force: false,
    help: false,
  };
  for (let i = 0; i < argv.length; i++) {
    const a = argv[i];
    if (a === "-h" || a === "--help") {
      args.help = true;
    } else if (a === "-y" || a === "--yes") {
      args.yes = true;
    } else if (a === "--plain") {
      args.plain = true;
    } else if (a === "--no-color") {
      args.noColor = true;
    } else if (a === "--check") {
      args.check = true;
    } else if (a === "--force") {
      args.force = true;
    } else if (a === "--target") {
      args.target = argv[++i];
      if (args.target === undefined) {
        return { error: "update: --target requires a directory argument" };
      }
    } else if (a.startsWith("--target=")) {
      args.target = a.slice("--target=".length);
    } else if (a === "--") {
      // remaining are positional
      if (i + 1 < argv.length && args.positional === null) args.positional = argv[i + 1];
      break;
    } else if (a.startsWith("-") && a !== "-") {
      return { error: "update: unrecognized option '" + a + "'" };
    } else if (args.positional === null) {
      args.positional = a;
    } else {
      return { error: "update: unexpected extra argument '" + a + "'" };
    }
  }
  return { args };
}

// --------------------------------------------------------------------------
// Entry
// --------------------------------------------------------------------------

// Public entry: runs the updater. `argv` is the args after the `update`
// subcommand. Returns a Promise resolving to the process exit code. Always
// non-interactive.
function run(argv) {
  const parsed = parseArgs(argv || []);
  if (parsed.error) {
    process.stderr.write(parsed.error + "\n\n");
    process.stderr.write(helpText() + "\n");
    return Promise.resolve(S.EXIT_USAGE);
  }
  const args = parsed.args;
  if (args.help) {
    process.stdout.write(helpText() + "\n");
    return Promise.resolve(S.EXIT_OK);
  }

  // -- preflight (same probe table install uses) --
  process.stdout.write("claude-company update - preflight\n");
  const results = S.PROBES.map((p) => {
    const [status, detail] = p.fn();
    return [p, status, detail];
  });
  for (const [probe, status, detail] of results) {
    process.stdout.write("  [" + status + "] " + S.padRight(probe.name, 18) + " " + detail + "\n");
  }
  const hardFail = results.filter((r) => r[0].hard && r[1] === S.FAIL);
  if (hardFail.length) {
    const names = hardFail.map((r) => r[0].name).join(", ");
    process.stderr.write("update: missing required tool(s): " + names + "\n");
    process.stderr.write("update: these are required by the enforcement hooks.\n");
    return Promise.resolve(S.EXIT_PREFLIGHT);
  }

  // -- resolve and validate target --
  const targetArg = args.target || args.positional;
  if (!targetArg) {
    process.stderr.write(
      "update: a target is required in non-interactive mode.\n" +
      "Usage: claude-company update --target /path/to/your/project [--check]\n");
    return Promise.resolve(S.EXIT_USAGE);
  }
  const [ok, p, msg] = S.validateTarget(targetArg);
  if (!ok) {
    process.stderr.write("update: target " + targetArg + ": " + msg + "\n");
    return Promise.resolve(S.EXIT_PREFLIGHT);
  }
  process.stdout.write("\ntarget: " + p + " (" + msg + ")\n");

  // -- run update.sh, streaming raw; return its exit code verbatim --
  const engineArgs = [UPDATE_SH, p];
  if (args.check) engineArgs.push("--check");
  if (args.force) engineArgs.push("--force");
  process.stdout.write("\n" + (args.check ? "planning update...\n" : "updating...\n"));
  const env = Object.assign({}, process.env, { PYTHONDONTWRITEBYTECODE: "1" });
  const res = spawnSync("bash", engineArgs, { env, stdio: "inherit" });
  if (res.error) {
    process.stderr.write("update: could not run update.sh: " + res.error.message + "\n");
    return Promise.resolve(EXIT_ENGINE_SPAWN);
  }
  // The engine owns the disposition semantics; pass its code up unchanged.
  // 0 ok (even with .new), 2 usage/target, 3 write failure, 4 downgrade refused.
  return Promise.resolve(res.status === null ? EXIT_ENGINE_SPAWN : res.status);
}

module.exports = { run, helpText };
