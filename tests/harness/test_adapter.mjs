#!/usr/bin/env node
/**
 * tests/harness/test_adapter.mjs - the adapter's HANDLERS, driven directly.
 *
 * test_core.mjs proves the pure decisions and test_opencode.sh proves opencode
 * still calls us. Neither could see the defect that mattered most: the
 * PostToolUse handler hardcoded `tool_response: ""`, so guard_provenance
 * recorded every audit as "unknown" - and `fresh_audit` passes anything that
 * is not "do-not-ship", so an auditor HALT read as an audit that passed and
 * the commit gate opened. Pure logic was correct; the wiring threw the verdict
 * away.
 *
 * So this suite instantiates the real plugin against a throwaway project whose
 * "guards" are scripts that record the payload they were handed. What reaches
 * a guard's stdin is the actual contract, and it is checked here rather than
 * inferred.
 */

import * as fs from "node:fs"
import * as os from "node:os"
import * as path from "node:path"
import { fileURLToPath } from "node:url"

const HERE = path.dirname(fileURLToPath(import.meta.url))
const REPO = path.resolve(HERE, "..", "..")
const { CompanyHarness } = await import(
  path.join(REPO, ".opencode", "plugin", "company-harness.js"))

let pass = 0
let fail = 0
const ok = (d) => { pass++; process.stdout.write("  \x1b[32mPASS\x1b[0m " + d + "\n") }
const no = (d, x) => {
  fail++
  process.stdout.write("  \x1b[31mFAIL\x1b[0m " + d + "\n")
  if (x) process.stdout.write("       " + x + "\n")
}
const is = (d, c, x) => (c ? ok(d) : no(d, x))

// --------------------------------------------------------------------------
// A project whose guards only record what they were given.
// --------------------------------------------------------------------------
function makeProject({ exitCode = 0, wiring } = {}) {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), "cc-adapter-"))
  const hooks = path.join(root, ".claude", "hooks")
  fs.mkdirSync(hooks, { recursive: true })
  const capture = path.join(root, "captured.jsonl")
  fs.writeFileSync(path.join(hooks, "recorder.py"),
    "#!/usr/bin/env python3\n" +
    "import sys, json\n" +
    "raw = sys.stdin.read()\n" +
    "open(" + JSON.stringify(capture) + ", 'a').write(raw + '\\n')\n" +
    "sys.exit(" + exitCode + ")\n")
  const hookCmd = { type: "command", command: 'python3 "$CLAUDE_PROJECT_DIR/.claude/hooks/recorder.py"' }
  fs.writeFileSync(path.join(root, ".claude", "settings.json"), JSON.stringify(
    wiring || {
      permissions: { deny: ["Read(./secrets/**)"] },
      hooks: {
        PreToolUse: [
          { matcher: "Edit|Write|MultiEdit", hooks: [hookCmd] },
          { matcher: "Task|Agent", hooks: [hookCmd] },
        ],
        PostToolUse: [{ matcher: "Task|Agent", hooks: [hookCmd] }],
      },
    }, null, 2))
  return {
    root,
    captured: () => (fs.existsSync(capture)
      ? fs.readFileSync(capture, "utf8").trim().split("\n").filter(Boolean).map(JSON.parse)
      : []),
    cleanup: () => fs.rmSync(root, { recursive: true, force: true }),
  }
}

const fakeClient = { config: { get: async () => ({ data: { agent: {} } }) } }
const load = (root) => CompanyHarness({ client: fakeClient, directory: root, worktree: root })

// --------------------------------------------------------------------------
process.stdout.write("\nthe audit verdict reaches guard_provenance (F1)\n")

{
  const p = makeProject()
  const h = await load(p.root)
  const HALT = "Verdict: HALT. Do not ship - the deny list is bypassable."
  await h["tool.execute.after"](
    { tool: "task", sessionID: "s1", args: { subagent_type: "auditor", prompt: "audit" } },
    { title: "audit", output: HALT, metadata: {} })

  const posts = p.captured().filter((c) => c.hook_event_name === "PostToolUse")
  is("a PostToolUse payload reached the guard", posts.length === 1,
     "got " + posts.length)
  // THE regression this file exists for. An empty tool_response is recorded as
  // verdict "unknown", and fresh_audit treats anything that is not
  // "do-not-ship" as a pass - so a HALT would silently open the commit gate.
  is("tool_response carries the auditor's actual verdict text",
     posts[0] && posts[0].tool_response === HALT,
     "got " + JSON.stringify(posts[0] && posts[0].tool_response))
  is("and it is not the empty string that shipped once",
     posts[0] && posts[0].tool_response !== "")
  p.cleanup()
}

{
  // The verdict has to survive the real parser, not just arrive intact.
  const { execFileSync } = await import("node:child_process")
  const read = (text) => execFileSync("python3", ["-c",
    "import sys; sys.path.insert(0, sys.argv[1]); import guard_provenance as g; " +
    "print(g.audit_verdict(g.response_text(sys.argv[2])))",
    path.join(REPO, ".claude", "hooks"), text], { encoding: "utf8" }).trim()
  is("guard_provenance reads HALT text as do-not-ship",
     read("Verdict: HALT. Do not ship.") === "do-not-ship")
  is("and reads an empty response as unknown, which is why '' was dangerous",
     read("") === "unknown")
}

// --------------------------------------------------------------------------
process.stdout.write("\nfail-closed wiring (FR-HA-10, FR-HA-11, F4)\n")

{
  const p = makeProject({ exitCode: 2 })
  const h = await load(p.root)
  let blocked = null
  try {
    await h["tool.execute.before"]({ tool: "write", sessionID: "s1" },
                                   { args: { filePath: "a.txt", content: "x" } })
  } catch (e) { blocked = e.message }
  is("a guard exiting 2 blocks the tool call", blocked !== null)
  p.cleanup()
}

{
  const p = makeProject()
  const h = await load(p.root)
  let blocked = null
  try {
    await h["tool.execute.before"]({ tool: "teleport", sessionID: "s1" }, { args: {} })
  } catch (e) { blocked = e.message }
  is("an unclassified tool blocks", blocked !== null && blocked.includes("teleport"))

  // F3: refusing must not invite the reader to make it a write tool.
  let ap = null
  try {
    await h["tool.execute.before"]({ tool: "apply_patch", sessionID: "s1" },
                                   { args: { patchText: "@@" } })
  } catch (e) { ap = e.message }
  is("apply_patch is refused with its own reason",
     ap !== null && ap.includes("patchText"))
  p.cleanup()
}

{
  // F2, end to end through the handler rather than through denied() alone.
  const p = makeProject()
  const h = await load(p.root)
  for (const spelling of ["secrets/k.pem", "./secrets/k.pem", "docs/../secrets/k.pem"]) {
    let msg = null
    try {
      await h["tool.execute.before"]({ tool: "read", sessionID: "s1" },
                                     { args: { filePath: spelling } })
    } catch (e) { msg = e.message }
    is("a read of " + spelling + " is denied", msg !== null && msg.includes("secrets/**"))
  }
  p.cleanup()
}

{
  // F4: a company project whose hooks are gone must BLOCK, because that is
  // what Claude Code does - a missing hook script exits 2.
  const root = fs.mkdtempSync(path.join(os.tmpdir(), "cc-nohooks-"))
  fs.mkdirSync(path.join(root, "company"), { recursive: true })
  const h = await load(root)
  let msg = null
  try {
    await h["tool.execute.before"]({ tool: "write", sessionID: "s1" },
                                   { args: { filePath: "a.txt", content: "x" } })
  } catch (e) { msg = e.message }
  is("a company project with no .claude/hooks blocks, rather than going quiet",
     msg !== null && msg.includes(".claude/hooks is missing"))

  // A project that never installed the company is a different state.
  const bare = fs.mkdtempSync(path.join(os.tmpdir(), "cc-bare-"))
  const h2 = await load(bare)
  is("a project that never installed the company is left alone",
     Object.keys(h2).length === 0)
  fs.rmSync(root, { recursive: true, force: true })
  fs.rmSync(bare, { recursive: true, force: true })
}

// --------------------------------------------------------------------------
process.stdout.write("\nguards run in delegated sessions (FR-HA-08)\n")

{
  const p = makeProject()
  const h = await load(p.root)
  // A subagent session is just another sessionID here. The DevMesh shim
  // resolved the parent and returned early; nothing may reintroduce that.
  await h["tool.execute.before"]({ tool: "write", sessionID: "child-session" },
                                 { args: { filePath: "a.txt", content: "x" } })
  const pre = p.captured().filter((c) => c.hook_event_name === "PreToolUse")
  is("a write from any session runs the chain", pre.length === 1)
  is("and the payload names that session", pre[0] && pre[0].session_id === "child-session")
  p.cleanup()
}

// --------------------------------------------------------------------------
process.stdout.write("\ncontext is session-scoped (FR-HA-13)\n")

{
  const p = makeProject()
  const h = await load(p.root)
  // Two sessions, one plugin instance. The prototype used a single global
  // array and cross-injected state digests between concurrent sessions.
  const out1 = { system: [] }
  await h["experimental.chat.system.transform"]({ sessionID: "A" }, out1)
  is("a session with nothing queued gets nothing", out1.system.length === 0)
  p.cleanup()
}

// --------------------------------------------------------------------------
process.stdout.write("\n================ SUMMARY ================\n")
process.stdout.write("PASS: " + pass + "   FAIL: " + fail + "\n")
process.stdout.write(fail === 0 ? "ALL GREEN\n" : "RED\n")
process.exit(fail === 0 ? 0 : 1)
