#!/usr/bin/env node
"use strict";

// claude-company - the npm-native CLI entry point.
//
//   npm install -g claude-company   ->   claude-company install .
//   npx claude-company install .
//
// This wrapper owns the subcommand parse (install / help / --version) and hands
// the `install` subcommand off to the Node installer TUI in lib/. The installer
// itself is zero-dependency Node; no Python is needed to launch it (python3 is
// probed inside the installer's preflight, since the enforcement hooks need it).

// Runtime Node floor. `engines` only warns at install time (npm EBADENGINE is
// non-fatal), so enforce >= 16 here where stdlib features we rely on exist.
const MIN_NODE_MAJOR = 16;
const nodeMajor = parseInt(process.versions.node.split(".")[0], 10);
if (nodeMajor < MIN_NODE_MAJOR) {
  process.stderr.write(
    "claude-company requires Node " + MIN_NODE_MAJOR + " or newer (found " +
    process.versions.node + "). Please upgrade Node and try again.\n");
  process.exit(1);
}

const path = require("path");

const ROOT = path.join(__dirname, "..");
const PKG = require(path.join(ROOT, "package.json"));

// --- minimal styling (bold + brand purple), with a dumb-terminal fallback ---

const COLOR = process.env.NO_COLOR === undefined && process.stdout.isTTY === true;

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

// --- entry ------------------------------------------------------------------

async function main(argv) {
  const args = argv.slice(2);

  if (args.length === 0) {
    process.stdout.write(helpText() + "\n");
    return 0;
  }

  const first = args[0];

  if (first === "--version" || first === "-v") {
    process.stdout.write(PKG.version + "\n");
    return 0;
  }
  if (first === "--help" || first === "-h" || first === "help") {
    process.stdout.write(helpText() + "\n");
    return 0;
  }
  if (first === "install") {
    const installer = require(path.join(ROOT, "lib", "install-tui.js"));
    return await installer.run(args.slice(1));
  }

  // Unknown subcommand.
  process.stderr.write(bold("claude-company: unknown command '" + first + "'") + "\n\n");
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
