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

const fs = require("fs");
const path = require("path");
const https = require("https");
const { spawnSync } = require("child_process");

const S = require("./install-tui.js")._shared;

const ROOT = path.join(__dirname, "..");
const UPDATE_SH = path.join(ROOT, "update.sh");
const PKG = require(path.join(ROOT, "package.json"));

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
    "Before it touches the project, update makes ONE optional HTTPS request to",
    "the npm registry to see if a newer claude-company shipped; if so it hands",
    "off to that version once. The check fails open - offline, a timeout, or a",
    "bad answer prints one WARN line and proceeds with the current version.",
    "",
    "Options:",
    "  --target DIR         Target project directory (must already exist).",
    "  --check              Print the plan and write nothing.",
    "  --force              Override a downgrade (installed version is newer).",
    "  --no-self-update     Skip the newer-version check (makes no network call).",
    "  -y, --yes            Accepted for parity; update is always plain (no-op).",
    "  --plain              Accepted for parity; update is always plain (no-op).",
    "  --no-color           Monochrome output (NO_COLOR is honored too).",
    "  -h, --help           Show this help.",
    "",
    "Examples:",
    "  claude-company update /path/to/your/project",
    "  npx claude-company update . --check",
    "  claude-company update . --no-self-update",
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
    noSelfUpdate: false,
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
    } else if (a === "--no-self-update") {
      args.noSelfUpdate = true;
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
// Self-update currency check (FR-SU-01..12)
// --------------------------------------------------------------------------
//
// Before update touches the project, get the CLI itself current: if a newer
// claude-company is published, hand off to it exactly once (covering stale npx
// caches and stale global installs) and let the NEWER CLI do the refresh. The
// hard rule is FAIL OPEN - any resolution or spawn failure prints one WARN line
// and proceeds with the current version. The check must never introduce a new
// nonzero exit of its own.

// OQ-SU-01 assumption: JS mirror of manifest.py _vercmp. Split on '.', compare
// field by field; numeric only when BOTH fields parse as ints, else lexical; a
// missing field counts as "0". Returns -1, 0, or 1.
function versionCompare(a, b) {
  const fa = String(a).split(".");
  const fb = String(b).split(".");
  const n = Math.max(fa.length, fb.length);
  for (let i = 0; i < n; i++) {
    const sa = i < fa.length ? fa[i] : "0";
    const sb = i < fb.length ? fb[i] : "0";
    let va, vb;
    if (isIntStr(sa) && isIntStr(sb)) {
      va = parseInt(sa, 10);
      vb = parseInt(sb, 10);
    } else {
      va = sa;
      vb = sb;
    }
    if (va < vb) return -1;
    if (va > vb) return 1;
  }
  return 0;
}

// Mirror of Python int() acceptance for version fields: an optional sign then
// digits, nothing else.
function isIntStr(s) {
  return /^[+-]?\d+$/.test(s);
}

// OQ-SU-04 assumption: 2000ms default, env-overridable. A non-numeric or
// non-positive override falls back to the default.
function parseTimeout(raw, dflt) {
  const n = parseInt(raw, 10);
  return Number.isFinite(n) && n > 0 ? n : dflt;
}

// Resolve the latest published version. Returns a Promise of { version } on
// success or { error } on any failure - the caller decides what to do with it.
function resolveLatest() {
  // FR-SU-12: CC_LATEST_VERSION, when set, bypasses the network entirely and is
  // the resolved answer - the seam that keeps tests off the live registry.
  const injected = process.env.CC_LATEST_VERSION;
  if (injected !== undefined && injected !== "") {
    return Promise.resolve({ version: injected });
  }
  const base = process.env.CC_REGISTRY_URL || "https://registry.npmjs.org";
  const url = base.replace(/\/+$/, "") + "/claude-company/latest";
  const timeoutMs = parseTimeout(process.env.CC_REGISTRY_TIMEOUT_MS, 2000);
  return httpsGetVersion(url, timeoutMs);
}

// GET the given URL and pull `.version` out of the JSON body. Never rejects -
// every failure mode resolves to { error } so the caller can fail open.
function httpsGetVersion(url, timeoutMs) {
  return new Promise((resolve) => {
    let settled = false;
    const done = (result) => {
      if (!settled) {
        settled = true;
        resolve(result);
      }
    };
    let req;
    try {
      req = https.get(url, (res) => {
        if (res.statusCode !== 200) {
          res.resume();
          done({ error: "HTTP " + res.statusCode });
          return;
        }
        let body = "";
        res.setEncoding("utf8");
        res.on("data", (chunk) => {
          body += chunk;
          if (body.length > 1e6) {
            req.destroy();
            done({ error: "response too large" });
          }
        });
        res.on("end", () => {
          try {
            const obj = JSON.parse(body);
            const v = obj && obj.version;
            if (typeof v === "string" && v) done({ version: v });
            else done({ error: "no version field in registry answer" });
          } catch (e) {
            done({ error: "bad JSON from registry" });
          }
        });
      });
    } catch (e) {
      done({ error: e && e.message ? e.message : "request failed" });
      return;
    }
    req.on("error", (e) => done({ error: e && e.message ? e.message : "request failed" }));
    // OQ-SU-04 assumption: hard timeout - destroy the socket and fail open.
    req.setTimeout(timeoutMs, () => {
      req.destroy();
      done({ error: "timeout after " + timeoutMs + "ms" });
    });
  });
}

// Is an `npx` executable resolvable on PATH? Scanned rather than spawned. The
// brief scopes native Windows out, so only the POSIX name is probed.
function npxAvailable() {
  const dirs = (process.env.PATH || "").split(path.delimiter);
  for (const dir of dirs) {
    if (!dir) continue;
    try {
      fs.accessSync(path.join(dir, "npx"), fs.constants.X_OK);
      return true;
    } catch (e) {
      // keep scanning
    }
  }
  return false;
}

// The self-update step. Runs after arg parse, before preflight. Returns a
// Promise of null to continue with the current CLI, or of an integer exit code
// when it handed off (the caller returns that code verbatim, FR-SU-03).
async function maybeSelfUpdate(argv, args) {
  // OQ-SU-06 assumption: --no-self-update skips the WHOLE step, network included.
  if (args.noSelfUpdate) return null;
  // FR-SU-08: we ARE the newer CLI the driver handed off to - proceed, do not
  // re-check (this is also what keeps the handoff to exactly once).
  if (process.env.CC_SELFUPDATE_DONE) return null;

  let resolved;
  try {
    resolved = await resolveLatest();
  } catch (e) {
    resolved = { error: e && e.message ? e.message : "unexpected error" };
  }
  if (resolved.error) {
    // Fail OPEN: the registry is unresolved. One WARN line, then continue.
    process.stderr.write(
      "self-update: WARN could not check for updates (" + resolved.error +
      "); continuing with claude-company@" + PKG.version + "\n");
    return null;
  }

  const latest = resolved.version;
  // Strictly-newer is the only re-exec trigger; equal or older is silent and
  // proceeds with today's behavior (FR-SU-06/07).
  if (versionCompare(latest, PKG.version) <= 0) {
    return null;
  }

  if (args.check) {
    // FR-SU-07: --check resolves and reports staleness in the plan but never
    // re-execs and writes nothing.
    process.stdout.write(
      "self-update: a newer claude-company is available (" + latest + " > " +
      PKG.version + "); run update without --check to pick it up\n");
    return null;
  }

  // OQ-SU-02 assumption: re-exec via npx for everyone. FR-SU-10: when npx is
  // absent, print one guidance line only - the driver NEVER runs npm install -g.
  if (!npxAvailable()) {
    process.stdout.write(
      "self-update: a newer claude-company is available (" + latest + "), but npx " +
      "was not found; run 'npm install -g claude-company@latest' then re-run update\n");
    return null;
  }

  // OQ-SU-05 assumption: hand off exactly once via npx, marking the child with
  // CC_SELFUPDATE_DONE=1 so it never re-checks. Pass the original args verbatim.
  process.stdout.write("self-update: handing off to claude-company@" + latest + " ...\n");
  const childEnv = Object.assign({}, process.env, { CC_SELFUPDATE_DONE: "1" });
  const childArgs = ["-y", "claude-company@" + latest, "update"].concat(argv);
  let res;
  try {
    res = spawnSync("npx", childArgs, { env: childEnv, stdio: "inherit" });
  } catch (e) {
    res = { error: e };
  }
  if (res.error) {
    // Spawn failure -> WARN -> fall through open to the current CLI.
    process.stderr.write(
      "self-update: WARN handoff failed (" + (res.error.message || res.error) +
      "); continuing with claude-company@" + PKG.version + "\n");
    return null;
  }
  // FR-SU-03: return the child's exit code verbatim (a signal kill maps to the
  // spawn-failure code, matching the engine-spawn convention below).
  return res.status === null ? EXIT_ENGINE_SPAWN : res.status;
}

// --------------------------------------------------------------------------
// Entry
// --------------------------------------------------------------------------

// Public entry: runs the updater. `argv` is the args after the `update`
// subcommand. Returns a Promise resolving to the process exit code. Always
// non-interactive.
async function run(argv) {
  const parsed = parseArgs(argv || []);
  if (parsed.error) {
    process.stderr.write(parsed.error + "\n\n");
    process.stderr.write(helpText() + "\n");
    return S.EXIT_USAGE;
  }
  const args = parsed.args;
  if (args.help) {
    process.stdout.write(helpText() + "\n");
    return S.EXIT_OK;
  }

  // -- self-update currency check (FR-SU-01): after arg parse, before preflight.
  // Fails open on every path; returns the child's code only when it handed off.
  const handoffCode = await maybeSelfUpdate(argv || [], args);
  if (handoffCode !== null) return handoffCode;

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
