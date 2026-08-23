/**
 * Pure logic for the claude-company opencode adapter.
 *
 * WHY THIS FILE IS NOT IN .opencode/plugin/: opencode loads every module in
 * the plugin directory and calls EVERY export as a plugin factory. A single
 * non-function export fails the whole file with "Plugin export is not a
 * function", and the error is only visible under --print-logs, so the plugin
 * silently does not load and enforcement silently does not happen. Verified
 * 2026-08-23. Everything here is therefore kept out of that directory, and
 * .opencode/plugin/company-harness.js exports exactly one function.
 *
 * Keeping the pure decisions here also makes them testable without opencode:
 * tests/harness drives these directly over a payload corpus (FR-HA-20).
 *
 * Node built-ins only (FR-HA-06).
 */

import * as fs from "node:fs"
import * as path from "node:path"

// --------------------------------------------------------------------------
// Tool classification - FR-HA-11
// --------------------------------------------------------------------------

/** opencode tool name -> the Claude tool name the guards match on. */
export const WRITE_TOOLS = {
  edit: "Edit",
  write: "Write",
  bash: "Bash",
  task: "Task",
}

/**
 * Write-capable tools the adapter refuses rather than guards, with the reason.
 *
 * OQ-HA-03 REVISED 2026-08-23. The fallback said "classify patch as a write
 * tool and run the Edit chain". Both halves were wrong. There is no `patch`
 * tool: opencode registers `apply_patch`, whose only argument is `patchText`.
 * It carries no file path, so `toolInputFor("Edit", ...)` would hand
 * guard_frozen and no_slop an empty `file_path` and an empty `new_string` -
 * they would inspect nothing and pass, which is a silent write bypass dressed
 * up as enforcement.
 *
 * Refusing is the honest option: the guards judge a file path and a content
 * string, and this tool supplies neither. edit and write are fully guarded and
 * do the same job.
 */
export const UNSUPPORTED_TOOLS = {
  apply_patch:
    "it writes files without naming them in its arguments (its only argument " +
    "is `patchText`), so the guards have no file path or content to judge. " +
    "Use the edit or write tool instead - both are fully guarded.",
}

/**
 * Tools that cannot modify the repository.
 *
 * A tool in NEITHER set blocks, so a tool added by a future opencode release
 * is a loud failure on first use rather than an unguarded write.
 * tests/harness pins this against known-tools.json so the block lands in CI
 * before it lands on a user.
 */
export const READ_ONLY_TOOLS = new Set([
  "read", "glob", "grep", "list", "webfetch", "websearch",
  "todowrite", "todoread", "skill", "question", "lsp", "invalid",
])

export const CLASSIFY_WRITE = "write"
export const CLASSIFY_READ_ONLY = "read-only"
export const CLASSIFY_UNSUPPORTED = "unsupported"
export const CLASSIFY_UNKNOWN = "unknown"

export function classifyTool(tool) {
  if (WRITE_TOOLS[tool]) return CLASSIFY_WRITE
  if (READ_ONLY_TOOLS.has(tool)) return CLASSIFY_READ_ONLY
  if (UNSUPPORTED_TOOLS[tool]) return CLASSIFY_UNSUPPORTED
  return CLASSIFY_UNKNOWN
}

// --------------------------------------------------------------------------
// Wiring, derived from .claude/settings.json - FR-HA-04
// --------------------------------------------------------------------------

function readJson(file) {
  try {
    return JSON.parse(fs.readFileSync(file, "utf8"))
  } catch {
    return null
  }
}

/**
 * Ordered hook groups per event, exactly as Claude Code reads them.
 *
 * Returns null when no settings file could be read at all. Callers treat that
 * as BLOCK rather than "no hooks configured" - the two are indistinguishable
 * from here, and only one of them is safe.
 */
export function loadWiring(root) {
  const files = [
    path.join(root, ".claude", "settings.json"),
    path.join(root, ".claude", "settings.local.json"),
  ]
  let found = false
  const events = {}
  for (const file of files) {
    if (!fs.existsSync(file)) continue
    const cfg = readJson(file)
    if (cfg === null) return null // present but unparseable: fail closed
    found = true
    const hooks = (cfg && cfg.hooks) || {}
    for (const [event, groups] of Object.entries(hooks)) {
      if (!Array.isArray(groups)) continue
      events[event] = (events[event] || []).concat(groups)
    }
  }
  return found ? events : null
}

// A matcher is "Edit|Write|MultiEdit", "Bash", "Task|Agent", or absent for the
// events that carry no tool. Absent matches everything on that event.
function matcherCovers(matcher, tool) {
  if (matcher === undefined || matcher === null || matcher === "") return true
  return String(matcher).split("|").some((t) => t.trim() === tool)
}

/**
 * The hook FILENAMES for one event and tool, in wiring order.
 * Commands look like: python3 "$CLAUDE_PROJECT_DIR/.claude/hooks/guard_frozen.py"
 */
export function scriptsFor(wiring, event, tool) {
  const out = []
  for (const group of (wiring && wiring[event]) || []) {
    if (!matcherCovers(group.matcher, tool)) continue
    for (const hook of group.hooks || []) {
      const m = String(hook.command || "").match(/([A-Za-z0-9_]+\.py)/)
      if (m && !out.includes(m[1])) out.push(m[1])
    }
  }
  return out
}

// --------------------------------------------------------------------------
// Deny list - FR-HA-14
// --------------------------------------------------------------------------

// opencode has no Read(...)/Edit(...) permission syntax, so settings.json's
// permissions.deny is enforced by the adapter instead. Claude tool name -> the
// opencode tools that can reach the same path.
const DENY_TOOL_MAP = {
  Read: ["read"],
  Edit: ["edit", "write", "apply_patch"],
  Write: ["edit", "write", "apply_patch"],
  MultiEdit: ["edit", "write", "apply_patch"],
}

export function loadDenyRules(root) {
  const rules = []
  for (const name of ["settings.json", "settings.local.json"]) {
    const cfg = readJson(path.join(root, ".claude", name))
    const deny = (cfg && cfg.permissions && cfg.permissions.deny) || []
    for (const entry of deny) {
      const m = String(entry).match(/^([A-Za-z]+)\((.*)\)$/)
      if (!m) continue
      const tools = DENY_TOOL_MAP[m[1]]
      if (!tools) continue
      rules.push({ tools, pattern: m[2].replace(/^\.\//, "") })
    }
  }
  return rules
}

/**
 * Minimal glob: ** spans separators, * does not.
 * Enough for the shipped patterns (.env, .env.*, secrets/**) and anything a
 * project adds in the same shape.
 */
export function globMatch(pattern, target) {
  let rx = ""
  for (let i = 0; i < pattern.length; i++) {
    const ch = pattern[i]
    if (ch === "*") {
      if (pattern[i + 1] === "*") {
        rx += ".*"
        i++
        if (pattern[i + 1] === "/") i++ // `secrets/**` also matches `secrets/`
      } else {
        rx += "[^/]*"
      }
      continue
    }
    rx += /[.+^${}()|[\]\\?]/.test(ch) ? "\\" + ch : ch
  }
  return new RegExp("^" + rx + "$").test(target)
}

/** The matching deny pattern, or null. */
export function denied(rules, tool, rel) {
  if (!rel) return null
  const base = path.basename(rel)
  for (const rule of rules) {
    if (!rule.tools.includes(tool)) continue
    if (globMatch(rule.pattern, rel) || globMatch(rule.pattern, base)) {
      return rule.pattern
    }
  }
  return null
}

// --------------------------------------------------------------------------
// Payload translation
// --------------------------------------------------------------------------

/**
 * The project-relative path a tool argument refers to, NORMALIZED.
 *
 * Normalization is load-bearing, not tidiness. `denied()` matches globs against
 * this string, and for a read it is the ONLY protection: read is classified
 * read-only, so no guard chain runs behind it. Before this normalized,
 * "secrets/key.pem" was denied while "./secrets/key.pem" and
 * "docs/../secrets/key.pem" read straight through - both are ordinary ways for
 * a model to write that path, and Claude Code blocks all three.
 *
 * `.env` happened to survive on the basename fallback. A directory pattern like
 * `secrets/**` has no basename to fall back to, which is why that one failed.
 */
export function toRelative(root, p) {
  if (!p) return ""
  const raw = path.isAbsolute(p) ? path.relative(root, p) : p
  return path.normalize(raw).replace(/\\/g, "/").replace(/^\.\//, "")
}

export function targetPath(args) {
  return (args && (args.filePath || args.path)) || ""
}

/** The tool_input shape each guard reads, keyed by the CLAUDE tool name. */
export function toolInputFor(tool, args) {
  const a = args || {}
  switch (tool) {
    case "Edit":
      return {
        file_path: a.filePath || a.path || "",
        old_string: a.oldString || "",
        new_string: a.newString !== undefined ? a.newString : (a.patch || ""),
      }
    case "Write":
      return { file_path: a.filePath || a.path || "", content: a.content || "" }
    case "Bash":
      return { command: a.command || "" }
    case "Task":
      return {
        subagent_type: a.subagent_type || "",
        description: a.description || "",
        prompt: a.prompt || "",
      }
    default:
      return { ...a }
  }
}

/** The stdin payload a guard receives. Mirrors Claude Code's shape exactly. */
export function buildPayload(root, sessionID, event, toolName, toolInput, extra) {
  return {
    ...(extra || {}),
    session_id: sessionID,
    cwd: root,
    permission_mode: "default",
    hook_event_name: event,
    tool_name: toolName,
    tool_input: toolInput,
  }
}

// --------------------------------------------------------------------------
// Guard results
// --------------------------------------------------------------------------

export const SPAWN_FAILED = -1

/**
 * The block message for a chain result, or null if nothing blocked.
 *
 * A guard that could not START is a block, not an allow (FR-HA-10). The
 * DevMesh shim resolved code 0 on spawn error, which reads a missing python3
 * as permission to proceed.
 */
export function blockMessage(results, scripts) {
  for (let i = 0; i < results.length; i++) {
    const r = results[i]
    if (r.code === SPAWN_FAILED) {
      return (
        "BLOCKED: the company harness could not run " + scripts[i] + " - " +
        (r.stderr || "python3 could not be started") +
        "\nEnforcement is not skipped because a guard failed to start. " +
        "Install python3, or remove the hook binding in .claude/settings.json."
      )
    }
    if (r.code === 2) {
      return (r.stderr || "").trim() || "Blocked by the company harness."
    }
  }
  return null
}

/** Context strings a chain produced, from JSON envelopes or plain text. */
export function contextFrom(results) {
  const out = []
  for (const r of results) {
    const text = (r.stdout || "").trim()
    if (!text) continue
    if (text.startsWith("{")) {
      try {
        const parsed = JSON.parse(text)
        const ctx =
          (parsed.hookSpecificOutput && parsed.hookSpecificOutput.additionalContext) ||
          parsed.additionalContext
        if (typeof ctx === "string" && ctx.trim()) out.push(ctx.trim())
        continue
      } catch {
        // Not an envelope after all - fall through and treat it as text.
      }
    }
    out.push(text)
  }
  return out
}

export function unknownToolMessage(tool) {
  // MCP tools are external code that can write anywhere, and their argument
  // shapes are defined by the server, not by opencode - so there is no file
  // path or content for the guards to judge. They block, which is the right
  // answer, but the generic "classify it" message would send the reader off to
  // add an unguardable tool to WRITE_TOOLS.
  if (tool.startsWith("mcp__")) {
    return (
      "BLOCKED: MCP tool '" + tool + "' cannot be guarded on this harness. An " +
      "MCP server defines its own argument shape, so the guards have no file " +
      "path or content to judge, and claude-company will not pretend to check " +
      "what it cannot see. Use the built-in edit, write and bash tools for " +
      "anything that touches this repository."
    )
  }
  return (
    "BLOCKED: tool '" + tool + "' is not classified by the company harness, " +
    "so it cannot be checked. If it CANNOT write to the repository, add it to " +
    "READ_ONLY_TOOLS in .opencode/lib/harness-core.js. If it can write, it may " +
    "only go in WRITE_TOOLS when its arguments carry a file path and the new " +
    "content - the guards judge those two things and nothing else. A write " +
    "tool without them belongs in UNSUPPORTED_TOOLS. Either way, add it to " +
    "tests/harness/known-tools.json."
  )
}

export function unsupportedToolMessage(tool) {
  return (
    "BLOCKED: tool '" + tool + "' cannot be guarded on this harness, because " +
    UNSUPPORTED_TOOLS[tool]
  )
}

export function deniedMessage(rel, pattern) {
  return (
    "BLOCKED: '" + rel + "' matches the protected path '" + pattern +
    "' in .claude/settings.json permissions.deny."
  )
}

export function noWiringMessage() {
  return (
    "BLOCKED: .claude/settings.json could not be read, so the company " +
    "harness cannot know which guards to run. Fix the file, or run " +
    "`claude-company update` to restore it."
  )
}

export function modelPinMessage(agent, model) {
  return (
    "BLOCKED: agent '" + agent + "' pins model '" + model + "'. On opencode " +
    "every company role inherits the session model, so no role runs weaker " +
    "than another. Remove the model line from .opencode/agent/" + agent + ".md."
  )
}
