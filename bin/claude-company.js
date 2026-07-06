#!/usr/bin/env node
"use strict";

// claude-company - thin Node launcher over the Python installer TUI.
//
// This wrapper exists so the project can ship on npm:
//   npm install -g claude-company   ->   claude-company install .
//   npx claude-company install .
//
// It owns no install logic of its own. The `install` subcommand finds a
// suitable Python (3.8+), then hands off to <package-root>/install, forwarding
// every remaining argument verbatim and mirroring the child's exit / signal.

const path = require("path");
const fs = require("fs");
const { spawn, spawnSync } = require("child_process");

const ROOT = path.join(__dirname, "..");
const INSTALLER = path.join(ROOT, "install");
const PKG = require(path.join(ROOT, "package.json"));

// --- minimal styling (bold + brand purple), with a dumb-terminal fallback ---

const COLOR =
  process.env.NO_COLOR === undefined &&
  process.env.NO_COLOR !== "" &&
  process.stdout.isTTY === true;

const PURPLE = "\x1b[38;2;139;92;246m";
const BOLD = "\x1b[1m";
const RESET = "\x1b[0m";

function brand(text) {
  return COLOR ? BOLD + PURPLE + text + RESET : text;
}
function bold(text) {
  return COLOR ? BOLD + text + RESET : text;
}

// --- help / version ---------------------------------------------------------

function versionString() {
  return PKG.version;
}

function helpText() {
  return [
    brand("claude-company") + " - " + PKG.description,
    "",
    bold("Usage"),
    "  claude-company install [target] [flags...]   install into a project",
    "  claude-company --version                      print the version",
    "  claude-company --help                         show this help",
    "",
    bold("Examples"),
    "  # installed globally (npm install -g claude-company):",
    "  claude-company install .",
    "  claude-company install ~/my-project --yes --no-detect-gates",
    "",
    "  # without installing, via npx:",
    "  npx claude-company install .",
    "",
    "The install subcommand forwards all flags to the bundled installer:",
    "  --target DIR, -y/--yes, --plain, --no-color,",
    "  --detect-gates/--no-detect-gates, --orientation/--no-orientation",
    "",
    "Docs: docs/getting-started.md",
  ].join("\n");
}

// --- python discovery -------------------------------------------------------

// Return an absolute-ish command name for a Python >= 3.8, or null.
function findPython() {
  const candidates = ["python3", "python"];
  for (const bin of candidates) {
    let res;
    try {
      res = spawnSync(bin, ["--version"], { encoding: "utf8" });
    } catch (e) {
      continue;
    }
    if (!res || res.error || res.status !== 0) {
      continue;
    }
    const out = (res.stdout || "") + (res.stderr || "");
    const m = out.match(/Python\s+(\d+)\.(\d+)/i);
    if (!m) {
      continue;
    }
    const major = parseInt(m[1], 10);
    const minor = parseInt(m[2], 10);
    if (major > 3 || (major === 3 && minor >= 8)) {
      return bin;
    }
  }
  return null;
}

function noPythonError() {
  const lines = [
    bold("claude-company needs Python 3.8+ to run its installer."),
    "",
    "No usable python3 or python was found on your PATH.",
    "Install Python from https://python.org or your package manager",
    "(brew install python, apt install python3, ...), then try again.",
  ];
  process.stderr.write(lines.join("\n") + "\n");
}

// --- install subcommand -----------------------------------------------------

function runInstall(forwardArgs) {
  if (!fs.existsSync(INSTALLER)) {
    process.stderr.write(
      bold("claude-company: bundled installer not found at ") +
        INSTALLER +
        "\n"
    );
    return 2;
  }

  const python = findPython();
  if (!python) {
    noPythonError();
    return 2;
  }

  // Hand off. cwd is inherited so `.` and relative targets resolve against the
  // user's working directory (the Python installer resolves relative paths
  // against cwd itself). stdio inherited so the TUI/plain output flows through.
  const child = spawn(python, [INSTALLER].concat(forwardArgs), {
    stdio: "inherit",
  });

  const forward = (sig) => {
    try {
      child.kill(sig);
    } catch (e) {
      /* child already gone */
    }
  };
  process.on("SIGINT", () => forward("SIGINT"));
  process.on("SIGTERM", () => forward("SIGTERM"));

  return new Promise((resolve) => {
    child.on("error", (err) => {
      process.stderr.write(
        bold("claude-company: failed to launch installer: ") +
          err.message +
          "\n"
      );
      resolve(2);
    });
    child.on("exit", (code, signal) => {
      if (signal) {
        // Mirror the child's signal death for accurate shell semantics.
        process.kill(process.pid, signal);
        // If we survive (signal ignored), fall back to conventional 128+n.
        resolve(1);
        return;
      }
      resolve(code === null ? 1 : code);
    });
  });
}

// --- entry ------------------------------------------------------------------

async function main(argv) {
  const args = argv.slice(2);

  if (args.length === 0) {
    process.stdout.write(helpText() + "\n");
    return 0;
  }

  const first = args[0];

  if (first === "--version" || first === "-v") {
    process.stdout.write(versionString() + "\n");
    return 0;
  }
  if (first === "--help" || first === "-h" || first === "help") {
    process.stdout.write(helpText() + "\n");
    return 0;
  }
  if (first === "install") {
    return await runInstall(args.slice(1));
  }

  // Unknown subcommand.
  process.stderr.write(
    bold("claude-company: unknown command '" + first + "'") + "\n\n"
  );
  process.stderr.write(helpText() + "\n");
  return 1;
}

main(process.argv)
  .then((code) => {
    process.exitCode = code;
  })
  .catch((err) => {
    process.stderr.write(
      bold("claude-company: unexpected error: ") + (err && err.message) + "\n"
    );
    process.exitCode = 1;
  });
