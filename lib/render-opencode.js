#!/usr/bin/env node
/**
 * lib/render-opencode.js - generate .opencode/ from .claude/.
 *
 * `.claude/` is the SOLE source of truth and is never written by this script
 * (FR-HA-01). `.opencode/` is a view of it, generated and committed, and a
 * drift gate re-renders and diffs (FR-HA-05). That is what makes the Claude
 * side impossible to regress by accident: nothing here can reach it.
 *
 * What is generated:
 *
 *   .claude/agents/<role>.md      -> .opencode/agent/<role>.md    (FR-HA-02)
 *   .claude/skills/<n>/SKILL.md   -> .opencode/command/<n>.md      (FR-HA-03)
 *                                 -> .opencode/opencode.json
 *
 * What is NOT generated, deliberately:
 *
 *   - the skills themselves. opencode discovers .claude/skills/**\/SKILL.md
 *     natively (verified 2026-08-23 with `opencode debug skill`), so copying
 *     them would register every skill twice. The generated commands exist only
 *     to give each skill a `/slash` affordance, which skills alone do not get.
 *   - .opencode/plugin/company-harness.js. It is hand-written and shipped
 *     as-is; it derives the guard chains from .claude/settings.json at
 *     runtime, so there is nothing about the wiring to generate.
 *
 * Usage:
 *   node lib/render-opencode.js            write .opencode/
 *   node lib/render-opencode.js --check    exit 1 on any difference
 *   node lib/render-opencode.js --root DIR operate on another checkout
 *
 * Node built-ins only - no dependencies, matching the adapter and the hooks.
 */

"use strict";

const fs = require("fs");
const path = require("path");

// Named in every generated file. Deliberately the CLI form, not the repo path:
// a user who installed the company has no lib/ directory, and telling them to
// run a file they do not have is how a customized role silently stays
// customized on one harness and stock on the other.
const GENERATED_BY = "`claude-company render`";

// --------------------------------------------------------------------------
// Frontmatter
// --------------------------------------------------------------------------

/**
 * Split a markdown file into its frontmatter lines and its body.
 *
 * Deliberately NOT a YAML parser. Every value here is passed through verbatim,
 * so a description carrying colons, quotes and escaped newlines survives
 * byte-for-byte instead of being re-serialized into something almost the same.
 */
function splitFrontmatter(text) {
  const lines = text.split("\n");
  if (lines[0] !== "---") return { keys: {}, body: text };
  const end = lines.indexOf("---", 1);
  if (end === -1) return { keys: {}, body: text };
  const keys = {};
  for (const line of lines.slice(1, end)) {
    const m = line.match(/^([A-Za-z][A-Za-z0-9_-]*):\s*(.*)$/);
    if (m) keys[m[1]] = m[2].trim();
  }
  return { keys, body: lines.slice(end + 1).join("\n").replace(/^\n+/, "") };
}

// --------------------------------------------------------------------------
// Tool and permission mapping
// --------------------------------------------------------------------------

// Claude tool name -> opencode permission key. Tools with no opencode
// counterpart map to null and are dropped: TaskCreate and friends are Claude's
// own todo surface, and NotebookEdit has no opencode tool at all.
const PERMISSION_KEY = {
  Agent: "task",
  Task: "task",
  Bash: "bash",
  Read: "read",
  Edit: "edit",
  Write: "write",
  MultiEdit: "edit",
  NotebookEdit: null,
  Grep: "grep",
  Glob: "glob",
  WebFetch: "webfetch",
  WebSearch: "websearch",
  TaskCreate: null,
  TaskUpdate: null,
  TaskList: null,
  TaskGet: null,
};

/** `Agent(developer, qa-engineer), Bash, Read` -> ["Agent(developer, qa-engineer)", "Bash", "Read"] */
function splitToolList(value) {
  const out = [];
  let depth = 0;
  let cur = "";
  for (const ch of value || "") {
    if (ch === "(") depth++;
    if (ch === ")") depth--;
    if (ch === "," && depth === 0) {
      if (cur.trim()) out.push(cur.trim());
      cur = "";
      continue;
    }
    cur += ch;
  }
  if (cur.trim()) out.push(cur.trim());
  return out;
}

/**
 * The opencode `permission` block for one role.
 *
 * Claude expresses this two ways and they mean opposite things:
 *   disallowedTools: a denylist - everything else is allowed
 *   tools:           an allowlist - everything else is denied
 * Only `task` is expressible per-target in opencode, so an allowlist collapses
 * to "deny every spawn except these", which is the part that carries the
 * hierarchy rule. The rest of an allowlist is not enforceable here and is
 * reported by --check rather than silently dropped.
 */
function permissionsFor(keys) {
  const perms = {};
  const unmapped = [];

  for (const entry of splitToolList(keys.disallowedTools)) {
    const key = PERMISSION_KEY[entry];
    if (key === undefined) unmapped.push(entry);
    if (!key) continue;
    perms[key] = "deny";
  }

  for (const entry of splitToolList(keys.tools)) {
    const m = entry.match(/^Agent\((.*)\)$/);
    if (m) {
      const allowed = m[1].split(",").map((s) => s.trim()).filter(Boolean);
      const task = { "*": "deny" };
      for (const name of allowed) task[name] = "allow";
      perms.task = task;
      continue;
    }
  }

  // An allowlist means "these tools and NO others". opencode can express that
  // per-target only for `task`, so any tool the allowlist leaves out is still
  // available on opencode while Claude Code denies it. Report the OMISSIONS,
  // which are the actual divergence - not the entries, which are the part that
  // works. Listing the entries would fire eleven warnings on a routine render
  // and teach the reader to ignore all of them.
  if (splitToolList(keys.tools).length) {
    const named = new Set();
    for (const entry of splitToolList(keys.tools)) {
      const key = PERMISSION_KEY[entry.replace(/\(.*\)$/, "")];
      if (key) named.add(key);
    }
    const enforceable = new Set(Object.values(PERMISSION_KEY).filter(Boolean));
    const omitted = [...enforceable].filter((k) => !named.has(k)).sort();
    if (omitted.length) {
      unmapped.push(
        "allowlist omits " + omitted.join(", ") +
        " - Claude Code denies those, opencode will still allow them");
    }
  }

  return { perms, unmapped };
}

function yamlPermissions(perms, indent) {
  const pad = " ".repeat(indent);
  const out = [];
  for (const key of Object.keys(perms).sort()) {
    const value = perms[key];
    if (typeof value === "string") {
      out.push(pad + key + ": " + value);
      continue;
    }
    out.push(pad + key + ":");
    // "*" first, then the named allows in a stable order: last match wins in
    // opencode, so the wildcard deny has to come before the exceptions.
    const names = Object.keys(value).filter((k) => k !== "*").sort();
    if (value["*"] !== undefined) {
      out.push(pad + '  "*": ' + value["*"]);
    }
    for (const name of names) out.push(pad + '  "' + name + '": ' + value[name]);
  }
  return out;
}

// --------------------------------------------------------------------------
// Renderers
// --------------------------------------------------------------------------

function renderAgent(name, source) {
  const { keys, body } = splitFrontmatter(source);
  const { perms, unmapped } = permissionsFor(keys);

  const lines = ["---"];
  if (keys.description) lines.push("description: " + keys.description);
  lines.push("mode: subagent");
  // FR-HA-15: no `model:` line, ever. On opencode every role inherits the
  // session model, and the adapter blocks any role that pins one.
  if (Object.keys(perms).length) {
    lines.push("permission:");
    lines.push(...yamlPermissions(perms, 2));
  }
  lines.push("---");
  lines.push("");
  lines.push(
    "<!-- GENERATED from .claude/agents/" + name + ".md by " + GENERATED_BY +
    ". Do not edit: edit the source and re-render. -->");
  lines.push("");
  lines.push(body.replace(/\s+$/, ""));
  lines.push("");
  return { text: lines.join("\n"), unmapped };
}

function renderCommand(name, skillSource) {
  const { keys } = splitFrontmatter(skillSource);
  const lines = ["---"];
  if (keys.description) lines.push("description: " + keys.description);
  lines.push("---");
  lines.push("");
  lines.push(
    "<!-- GENERATED from .claude/skills/" + name + "/SKILL.md by " +
    GENERATED_BY + ". Do not edit: edit the source and re-render. -->");
  lines.push("");
  // The body is NOT duplicated here. opencode reads .claude/skills natively,
  // so the one copy of the instructions stays the skill; this command exists
  // to give it a slash affordance.
  lines.push(
    "Use the skill tool to load the `" + name + "` skill, then follow it " +
    "exactly as written.");
  lines.push("");
  lines.push("$ARGUMENTS");
  lines.push("");
  return lines.join("\n");
}

function renderConfig() {
  return JSON.stringify({
    $schema: "https://opencode.ai/config.json",
    instructions: ["CLAUDE.md"],
    // The company hierarchy needs exactly ONE nested level: CEO (depth 0)
    // spawns a tech-lead (depth 1), who must be able to spawn their own
    // developer and qa-engineer crew (depth 2). opencode defaults this to 1,
    // which silently strips the task tool from every lead session - a lead
    // could describe its team but never dispatch it. Developers stay
    // terminal regardless: they carry no explicit task permission, so
    // opencode removes the task tool from THEIR sessions entirely, and at
    // depth 2 this config would refuse a further spawn even if one appeared.
    subagent_depth: 2,
  }, null, 2) + "\n";
}

// --------------------------------------------------------------------------
// Rendering the whole tree
// --------------------------------------------------------------------------

function listAgents(root) {
  const dir = path.join(root, ".claude", "agents");
  if (!fs.existsSync(dir)) return [];
  return fs.readdirSync(dir).filter((f) => f.endsWith(".md")).sort();
}

function listSkills(root) {
  const dir = path.join(root, ".claude", "skills");
  if (!fs.existsSync(dir)) return [];
  return fs.readdirSync(dir)
    .filter((n) => fs.existsSync(path.join(dir, n, "SKILL.md")))
    .sort();
}

/** { relativePath: contents } for every generated file, plus any warnings. */
function render(root) {
  const files = {};
  const warnings = [];

  for (const file of listAgents(root)) {
    const name = file.slice(0, -3);
    const src = fs.readFileSync(path.join(root, ".claude", "agents", file), "utf8");
    const { text, unmapped } = renderAgent(name, src);
    files[path.join(".opencode", "agent", file)] = text;
    for (const entry of unmapped) {
      warnings.push(name + ": tool '" + entry + "' has no opencode mapping");
    }
  }

  for (const name of listSkills(root)) {
    const src = fs.readFileSync(
      path.join(root, ".claude", "skills", name, "SKILL.md"), "utf8");
    files[path.join(".opencode", "command", name + ".md")] = renderCommand(name, src);
  }

  files[path.join(".opencode", "opencode.json")] = renderConfig();
  return { files, warnings };
}

// --------------------------------------------------------------------------
// CLI
// --------------------------------------------------------------------------

/** Generated files currently on disk, so a stale leftover counts as drift. */
function onDisk(root) {
  const found = {};
  for (const sub of [["agent"], ["command"]]) {
    const dir = path.join(root, ".opencode", ...sub);
    if (!fs.existsSync(dir)) continue;
    for (const f of fs.readdirSync(dir)) {
      if (!f.endsWith(".md")) continue;
      const rel = path.join(".opencode", ...sub, f);
      found[rel] = fs.readFileSync(path.join(root, rel), "utf8");
    }
  }
  const cfg = path.join(root, ".opencode", "opencode.json");
  if (fs.existsSync(cfg)) {
    found[path.join(".opencode", "opencode.json")] = fs.readFileSync(cfg, "utf8");
  }
  return found;
}

function main(argv) {
  let root = process.cwd();
  let check = false;
  for (let i = 0; i < argv.length; i++) {
    if (argv[i] === "--check") check = true;
    else if (argv[i] === "--root") root = argv[++i];
    else {
      process.stderr.write("unknown argument: " + argv[i] + "\n");
      return 2;
    }
  }

  const { files, warnings } = render(root);
  for (const w of warnings) process.stderr.write("warning: " + w + "\n");

  if (check) {
    // BR-HA-01: no generated file is ever hand-edited, and this is the
    // enforcement rather than a convention - a hand edit shows up here as a
    // difference and fails the gate.
    const disk = onDisk(root);
    const drift = [];
    for (const rel of Object.keys(files).sort()) {
      if (disk[rel] === undefined) drift.push("missing:   " + rel);
      else if (disk[rel] !== files[rel]) drift.push("differs:   " + rel);
    }
    for (const rel of Object.keys(disk).sort()) {
      if (files[rel] === undefined) drift.push("orphaned:  " + rel);
    }
    if (drift.length) {
      process.stderr.write(
        "generated .opencode/ does not match .claude/:\n" +
        drift.map((d) => "  " + d).join("\n") +
        "\n\nRe-render with: node lib/render-opencode.js\n");
      return 1;
    }
    process.stdout.write(
      "generated tree matches source (" + Object.keys(files).length + " files)\n");
    return 0;
  }

  for (const rel of Object.keys(files).sort()) {
    const abs = path.join(root, rel);
    fs.mkdirSync(path.dirname(abs), { recursive: true });
    fs.writeFileSync(abs, files[rel]);
  }
  // A role or skill deleted at the source must not leave a generated orphan.
  for (const rel of Object.keys(onDisk(root))) {
    if (files[rel] === undefined) fs.unlinkSync(path.join(root, rel));
  }
  process.stdout.write("wrote " + Object.keys(files).length + " files\n");
  return 0;
}

if (require.main === module) process.exit(main(process.argv.slice(2)));

module.exports = {
  main,
  splitFrontmatter,
  splitToolList,
  permissionsFor,
  renderAgent,
  renderCommand,
  render,
};
