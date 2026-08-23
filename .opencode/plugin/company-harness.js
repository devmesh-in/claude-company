/**
 * claude-company enforcement adapter for opencode.
 *
 * Claude Code runs the guards in .claude/hooks/ through the hook bindings in
 * .claude/settings.json. opencode has no equivalent, so this plugin is a
 * translator and nothing more: it maps opencode's tool and event hooks onto
 * the SAME stdin payload the guards already read, and runs the SAME scripts
 * in the SAME order. The guards are never modified and never reimplemented -
 * a rule that changes, changes in the Python.
 *
 * The chain order is not written down here. It is DERIVED from
 * .claude/settings.json at startup (FR-HA-04), so there is no second copy of
 * the wiring to drift from the first, and guard_models.EXPECTED_WIRING stays
 * the one assertion that pins it.
 *
 * THIS FILE EXPORTS EXACTLY ONE FUNCTION, DELIBERATELY. opencode calls every
 * export in a plugin module as a plugin factory; one non-function export
 * fails the whole file with "Plugin export is not a function", visible only
 * under --print-logs. The plugin then silently does not load, and a harness
 * that silently does not load is indistinguishable from one that is working.
 * All pure logic therefore lives in ../lib/harness-core.js, outside the
 * directory opencode scans.
 *
 * Dependency-free ESM (FR-HA-06): no TypeScript, no build step, no
 * node_modules in the payload. The JavaScript counterpart of the
 * Python-3.8-stdlib rule the hooks follow.
 *
 * ## Failure posture
 *
 * The guards fail OPEN on an internal error: jamming a session is worse than
 * missing one check. THIS ADAPTER FAILS CLOSED. It is not a guard, it is the
 * thing that decides whether guards run at all:
 *
 *   - a guard that cannot be spawned BLOCKS (FR-HA-10)
 *   - an unclassified tool BLOCKS (FR-HA-11)
 *   - an unreadable settings.json BLOCKS every wired tool
 *
 * ## Five deliberate departures from the DevMesh prototype
 *
 * That shim (569 lines, preserved unmerged on DevMesh task/opencode-shim) is
 * where the translation shape came from. Each of these is a defect it shipped:
 *
 *   1. It returned early for every subagent session, disabling the whole
 *      guard chain in exactly the delegated lanes where code gets written.
 *      Hooks DO fire there - verified 2026-08-23: tool.execute.before fires
 *      for a delegated bash call with parentID set. Guards run in EVERY
 *      session here (FR-HA-08).
 *   2. Its spawn-error handler resolved code 0, so a missing python3 read as
 *      "allowed" (FR-HA-10).
 *   3. Its tool map covered four tools and returned silently for anything
 *      else, so any tool it did not know about wrote unguarded (FR-HA-11).
 *      Here an unclassified tool blocks, and `apply_patch` - which writes
 *      files without naming them in its arguments - is refused outright
 *      rather than handed to guards that would inspect an empty path.
 *   4. It read an `args.workdir` field that does not exist in the plugin SDK.
 *      FR-HA-12 says this fixes worktree resolution; be precise about what it
 *      actually buys. `worktree` is fixed at plugin load, and no per-call cwd
 *      exists, so every payload carries the same cwd - the guards resolve the
 *      acting tree from the FILE PATH, not from cwd, which is what makes them
 *      correct here. The practical consequence is that
 *      `in_worktree_or_out_of_tree(cwd, root)` never fires under this adapter,
 *      so guard_provenance's worktree exemptions do not apply: opencode work
 *      is held to the stricter main-checkout rule. That is a deliberate
 *      tightening, not parity.
 *   5. Its pending-context buffer was one plugin-global array, so concurrent
 *      sessions cross-injected each other's state digests (FR-HA-13).
 */

import { spawn } from "node:child_process"
import * as fs from "node:fs"
import * as path from "node:path"

import {
  CLASSIFY_READ_ONLY,
  CLASSIFY_UNKNOWN,
  CLASSIFY_UNSUPPORTED,
  SPAWN_FAILED,
  WRITE_TOOLS,
  blockMessage,
  buildPayload,
  classifyTool,
  contextFrom,
  denied,
  deniedMessage,
  loadDenyRules,
  loadWiring,
  modelPinMessage,
  noWiringMessage,
  scriptsFor,
  targetPath,
  toRelative,
  toolInputFor,
  unknownToolMessage,
  unsupportedToolMessage,
} from "../lib/harness-core.js"

// Set COMPANY_HARNESS_DEBUG to a file path to trace load and every decision.
// A translator that silently does nothing looks exactly like one that works,
// so there has to be a way to tell them apart from outside. This is how the
// "Plugin export is not a function" failure above was found.
const DEBUG_LOG = process.env.COMPANY_HARNESS_DEBUG || ""
function trace(event) {
  if (!DEBUG_LOG) return
  try {
    fs.appendFileSync(DEBUG_LOG, JSON.stringify(event) + "\n")
  } catch {
    // Tracing must never be able to break enforcement.
  }
}

// Claude Code applies a 60s default per hook. Without a timeout here a guard
// that blocks - the usual cause is a slow `git status` under load, and
// guard_provenance's own docstring records a 217-second hooks run under
// contention - wedges the tool call with no recovery and no log line.
const GUARD_TIMEOUT_MS = 60000

function runScript(scriptPath, payload, cwd) {
  return new Promise((resolve) => {
    let child
    try {
      child = spawn("python3", [scriptPath], {
        cwd,
        env: { ...process.env, CLAUDE_PROJECT_DIR: cwd },
        stdio: ["pipe", "pipe", "pipe"],
      })
    } catch (e) {
      resolve({ code: SPAWN_FAILED, stdout: "", stderr: String(e && e.message) })
      return
    }
    let stdout = ""
    let stderr = ""
    let settled = false
    const done = (r) => {
      if (settled) return
      settled = true
      clearTimeout(timer)
      resolve(r)
    }
    // A guard that never answers is treated as a guard that could not run,
    // which BLOCKS. "I could not look" must never read as "nothing to see" -
    // the same rule guard_secrets learned the hard way about git silence.
    const timer = setTimeout(() => {
      try { child.kill("SIGKILL") } catch { /* already gone */ }
      done({
        code: SPAWN_FAILED,
        stdout: "",
        stderr: "timed out after " + GUARD_TIMEOUT_MS + "ms",
      })
    }, GUARD_TIMEOUT_MS)
    child.stdout.on("data", (d) => (stdout += d))
    child.stderr.on("data", (d) => (stderr += d))
    child.on("error", (e) =>
      done({ code: SPAWN_FAILED, stdout: "", stderr: String(e && e.message) }))
    child.on("close", (code) => done({ code, stdout, stderr }))
    child.stdin.on("error", () => {})
    child.stdin.end(JSON.stringify(payload))
  })
}

export const CompanyHarness = async ({ client, directory, worktree }) => {
  // FR-HA-12: the acting tree, so _common.git_cwd and acting_tree can resolve
  // a worktree instead of always seeing the project root.
  const root = worktree || directory
  const hooksDir = path.join(root, ".claude", "hooks")

  // A project with no .claude/hooks is NOT a project to leave unguarded. On
  // Claude Code the same state blocks: the hook command still runs and
  // `python3 .claude/hooks/guard_frozen.py` exits 2 on a missing file, which
  // is the block code. Returning {} here made a half-installed or wrong-root
  // project fully guarded on one harness and fully open on the other, with a
  // single trace line as the only evidence. BR-HA-03: a harness may differ in
  // mechanism, never in verdict.
  //
  // The one exception is a project that never installed the company at all -
  // no company/ directory - where this plugin has no business blocking
  // anything. That is a different state from a broken install.
  if (!fs.existsSync(hooksDir)) {
    const installed = fs.existsSync(path.join(root, "company"))
    trace({ ev: "inactive", reason: "no .claude/hooks", installed, root })
    if (!installed) return {}
    const message =
      "BLOCKED: .claude/hooks is missing, so the company harness cannot run " +
      "any guard, but this project has a company/ directory and is meant to " +
      "be guarded. Run `claude-company update` to restore the hooks."
    const refuse = async () => { throw new Error(message) }
    return { "tool.execute.before": refuse }
  }

  const wiring = loadWiring(root)
  const denyRules = loadDenyRules(root)
  trace({
    ev: "load",
    root,
    wiredEvents: wiring ? Object.keys(wiring) : null,
    denyRules: denyRules.length,
  })

  // FR-HA-13: keyed by session, never one shared buffer.
  const pending = new Map()
  const digested = new Set()

  const queue = (sessionID, text) => {
    if (!sessionID || !text) return
    if (!pending.has(sessionID)) pending.set(sessionID, [])
    pending.get(sessionID).push(text)
  }

  const drain = (sessionID) => {
    const queued = pending.get(sessionID)
    if (!queued || !queued.length) return []
    pending.set(sessionID, [])
    return queued
  }

  /** Run one chain in order. Stops at the first blocker. */
  const runChain = async (scripts, payload) => {
    const results = []
    for (const script of scripts) {
      const r = await runScript(path.join(hooksDir, script), payload, root)
      results.push(r)
      if (r.code === 2 || r.code === SPAWN_FAILED) break
    }
    return results
  }

  const runEvent = async (sessionID, event, claudeTool, toolInput, extra) => {
    if (wiring === null) return
    const scripts = scriptsFor(wiring, event, claudeTool)
    if (!scripts.length) return
    const results = await runChain(
      scripts, buildPayload(root, sessionID, event, claudeTool, toolInput, extra))
    const msg = blockMessage(results, scripts)
    trace({ ev: "chain", event, tool: claudeTool, scripts, blocked: Boolean(msg) })
    if (msg) throw new Error(msg)
    for (const ctx of contextFrom(results)) queue(sessionID, ctx)
  }

  const sessionDigest = async (sessionID) => {
    if (digested.has(sessionID)) return
    digested.add(sessionID)
    await runEvent(sessionID, "SessionStart", "", {})
  }

  // FR-HA-15. Owner decision 2026-08-23: opencode roles INHERIT the session
  // model. There is no per-harness manifest to compare against, so the rule is
  // the ABSENCE of a pin and the guard is that any pin blocks. That preserves
  // the property company/models.json gives the Claude side: no role reasons at
  // a different level than any other.
  const companyAgents = () => {
    const out = new Set()
    for (const dir of ["agent", "agents"]) {
      const d = path.join(root, ".opencode", dir)
      if (!fs.existsSync(d)) continue
      for (const f of fs.readdirSync(d)) {
        if (f.endsWith(".md")) out.add(f.slice(0, -3))
      }
    }
    return out
  }

  const enforceInherit = async (subagentType) => {
    if (!subagentType) return
    if (!companyAgents().has(subagentType)) return // builtin or unknown: not ours
    let model
    try {
      const res = await client.config.get({ query: { directory } })
      const agent = res && res.data && res.data.agent && res.data.agent[subagentType]
      model = agent ? agent.model : undefined
    } catch {
      return // config unreadable: the spawn chain still runs; invent no verdict
    }
    if (typeof model === "string" && model.trim() && model.trim() !== "inherit") {
      throw new Error(modelPinMessage(subagentType, model))
    }
  }

  return {
    "tool.execute.before": async (input, output) => {
      const tool = input.tool
      const args = output.args || {}
      const rel = toRelative(root, targetPath(args))
      trace({ ev: "before", tool, rel, session: input.sessionID })

      // FR-HA-14: deny paths, in every session, reads included.
      const hit = denied(denyRules, tool, rel)
      if (hit) throw new Error(deniedMessage(rel, hit))

      const kind = classifyTool(tool)
      if (kind === CLASSIFY_READ_ONLY) return
      if (kind === CLASSIFY_UNSUPPORTED) throw new Error(unsupportedToolMessage(tool))
      // FR-HA-11. Unknown means unclassified, and an unclassified tool may
      // write. Blocking is loud and immediate; the alternative is a silent
      // hole nobody finds until it matters.
      if (kind === CLASSIFY_UNKNOWN) throw new Error(unknownToolMessage(tool))

      if (wiring === null) throw new Error(noWiringMessage())

      const claudeTool = WRITE_TOOLS[tool]
      if (claudeTool === "Task") await enforceInherit(args.subagent_type)

      // FR-HA-08: no subagent exemption. Delegated lanes are where code gets
      // written, so they are exactly where the guards must run.
      await runEvent(input.sessionID, "PreToolUse", claudeTool,
                     toolInputFor(claudeTool, args))
    },

    "tool.execute.after": async (input, output) => {
      const claudeTool = WRITE_TOOLS[input.tool]
      // Claude wires PostToolUse for the edit tools and the spawn tools only.
      if (!claudeTool || claudeTool === "Bash") return
      // tool_response CARRIES THE AUDIT VERDICT. guard_provenance mode_b_post
      // parses it, and fresh_audit treats anything that is not "do-not-ship"
      // as an audit that passed - so an empty response records an auditor HALT
      // as "unknown" and the commit gate lets the merge through. Sending "" is
      // strictly worse than sending nothing: recording nothing leaves the gate
      // armed, while recording "unknown" disarms it. This shipped empty once;
      // it turned the commit gate from "an audit passed" into "an auditor was
      // spawned".
      await runEvent(input.sessionID, "PostToolUse", claudeTool,
                     toolInputFor(claudeTool, input.args || {}),
                     { tool_response: (output && output.output) || "" })
    },

    "chat.message": async (input) => {
      await sessionDigest(input.sessionID)
      await runEvent(input.sessionID, "UserPromptSubmit", "", {})
    },

    event: async ({ event }) => {
      if (event.type === "session.created") {
        const info = event.properties && event.properties.info
        if (info && info.id) await sessionDigest(info.id)
      } else if (event.type === "session.idle") {
        const id = event.properties && event.properties.sessionID
        if (!id) return
        // A Stop chain cannot un-finish a turn, so a block here surfaces as
        // injected context on the next turn rather than as a hard stop.
        try {
          await runEvent(id, "Stop", "", {}, { stop_hook_active: false })
        } catch (e) {
          queue(id, String(e && e.message))
        }
      }
    },

    "experimental.chat.system.transform": async (input, output) => {
      if (!input.sessionID) return
      const queued = drain(input.sessionID)
      if (queued.length) output.system = (output.system || []).concat(queued)
    },

    "experimental.session.compacting": async (input, output) => {
      const queued = drain(input.sessionID)
      if (queued.length) output.context.push(...queued)
    },
  }
}
