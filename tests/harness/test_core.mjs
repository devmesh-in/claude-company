#!/usr/bin/env node
/**
 * tests/harness/test_core.mjs - the adapter's pure decisions.
 *
 * These prove the DECISIONS, not the plumbing: which guards a tool routes to,
 * what blocks, what passes, and what the payload looks like when it reaches a
 * guard's stdin. Every case here fails if a specific behavior regresses, and
 * the comment on each says which break it catches.
 *
 * The plumbing (does opencode actually call us, does the block reach the
 * model) is proved by tests/harness/test_opencode.sh against the real binary.
 * Neither suite substitutes for the other.
 */

import * as fs from "node:fs"
import * as os from "node:os"
import * as path from "node:path"
import { fileURLToPath } from "node:url"

const HERE = path.dirname(fileURLToPath(import.meta.url))
const REPO = path.resolve(HERE, "..", "..")

const core = await import(path.join(REPO, ".opencode", "lib", "harness-core.js"))

let pass = 0
let fail = 0
const ok = (desc) => { pass++; process.stdout.write("  \x1b[32mPASS\x1b[0m " + desc + "\n") }
const no = (desc, detail) => {
  fail++
  process.stdout.write("  \x1b[31mFAIL\x1b[0m " + desc + "\n")
  if (detail) process.stdout.write("       " + detail + "\n")
}
const eq = (desc, actual, expected) => {
  const a = JSON.stringify(actual)
  const e = JSON.stringify(expected)
  a === e ? ok(desc) : no(desc, "expected " + e + "\n       actual   " + a)
}
const is = (desc, cond, detail) => (cond ? ok(desc) : no(desc, detail))

// --------------------------------------------------------------------------
// A throwaway project whose settings.json is the SHIPPED one, so the wiring
// under test is the wiring that ships.
// --------------------------------------------------------------------------
const WORK = fs.mkdtempSync(path.join(os.tmpdir(), "cc-harness-"))
process.on("exit", () => fs.rmSync(WORK, { recursive: true, force: true }))
fs.mkdirSync(path.join(WORK, ".claude"), { recursive: true })
fs.copyFileSync(
  path.join(REPO, ".claude", "settings.json"),
  path.join(WORK, ".claude", "settings.json"))

// --------------------------------------------------------------------------
// Tool classification - FR-HA-11
// --------------------------------------------------------------------------
process.stdout.write("\ntool classification (FR-HA-11)\n")

eq("write tools route to their Claude name",
   ["edit", "write", "bash", "task"].map((t) => core.WRITE_TOOLS[t]),
   ["Edit", "Write", "Bash", "Task"])

// apply_patch writes files but names none of them in its arguments - its only
// argument is patchText. Classifying it as a write would hand guard_frozen and
// no_slop an empty file_path and an empty new_string: they would inspect
// nothing and pass, which is a bypass that LOOKS like enforcement. Refusing is
// the only honest answer, and this test exists to stop a future reader
// "fixing" it into WRITE_TOOLS.
is("apply_patch is refused, not routed to the Edit chain",
   core.classifyTool("apply_patch") === core.CLASSIFY_UNSUPPORTED)
is("and its refusal explains why, rather than inviting a reclassification",
   core.unsupportedToolMessage("apply_patch").includes("patchText"))

// There is no `patch` tool in opencode. An earlier version of this adapter
// mapped one, and two tests asserted on it - both passed forever, because the
// behavior they named had no subject.
is("`patch` is not treated as a real tool",
   core.classifyTool("patch") === core.CLASSIFY_UNKNOWN)

is("read is read-only", core.classifyTool("read") === core.CLASSIFY_READ_ONLY)

// MCP tools block, which is correct - an MCP server defines its own argument
// shape, so there is no file path or content for a guard to judge. The message
// must say that, or a reader follows the generic advice and adds an
// unguardable tool to WRITE_TOOLS.
is("an MCP tool blocks", core.classifyTool("mcp__x__y") === core.CLASSIFY_UNKNOWN)
is("and its message explains MCP rather than inviting a reclassification",
   core.unknownToolMessage("mcp__x__y").includes("MCP server defines its own"))

// The whole point of failing closed. If this flips to read-only or write, a
// tool opencode adds in a future release stops being a loud error.
is("an unrecognised tool is UNKNOWN, not silently allowed",
   core.classifyTool("teleport") === core.CLASSIFY_UNKNOWN)

{
  // OQ-HA-01: the snapshot is the oracle, since opencode cannot enumerate
  // tools headlessly. An opencode upgrade that adds a tool must fail HERE,
  // during CI, not at a user's first use of it.
  const snap = JSON.parse(
    fs.readFileSync(path.join(HERE, "known-tools.json"), "utf8"))
  const unclassified = snap.tools.filter(
    (t) => core.classifyTool(t) === core.CLASSIFY_UNKNOWN)
  is("every tool in known-tools.json is classified",
     unclassified.length === 0,
     "unclassified: " + unclassified.join(", "))
}

// --------------------------------------------------------------------------
// Wiring derivation - FR-HA-04
// --------------------------------------------------------------------------
process.stdout.write("\nwiring derived from .claude/settings.json (FR-HA-04)\n")

const wiring = core.loadWiring(WORK)
is("the shipped settings.json parses into events", wiring !== null)

// This is the anti-drift property: the chain is not written down twice. If
// someone adds a guard to settings.json, it appears here with no other edit.
eq("a Write routes to the full edit chain, in wiring order",
   core.scriptsFor(wiring, "PreToolUse", "Write"),
   ["guard_frozen.py", "guard_spec.py", "guard_tests.py", "no_slop.py",
    "guard_models.py"])

eq("Bash routes to the bash chain",
   core.scriptsFor(wiring, "PreToolUse", "Bash"),
   ["guard_commit.py", "guard_secrets.py", "guard_tests.py"])

eq("Task matches the Task|Agent matcher",
   core.scriptsFor(wiring, "PreToolUse", "Task"),
   ["guard_models.py"])

// A matcher of "Edit|Write|MultiEdit" must not be satisfied by a substring.
eq("a tool not named in a matcher gets no chain",
   core.scriptsFor(wiring, "PreToolUse", "Edi"), [])

eq("matcherless events apply to every tool",
   core.scriptsFor(wiring, "SessionStart", ""), ["session_start.py"])

// The cost ledger was removed in #134; if SubagentStop ever comes back with a
// hook, the adapter picks it up without being told.
eq("an unwired event yields no chain",
   core.scriptsFor(wiring, "SubagentStop", ""), [])

{
  // Fail closed. A settings.json that exists but is corrupt must not read as
  // "this project has no hooks" - that is indistinguishable from an unguarded
  // project, and only one of the two is safe.
  const broken = fs.mkdtempSync(path.join(os.tmpdir(), "cc-broken-"))
  fs.mkdirSync(path.join(broken, ".claude"), { recursive: true })
  fs.writeFileSync(path.join(broken, ".claude", "settings.json"), "{ not json")
  is("an unparseable settings.json yields null, not an empty wiring",
     core.loadWiring(broken) === null)
  fs.rmSync(broken, { recursive: true, force: true })
}

// --------------------------------------------------------------------------
// Deny list - FR-HA-14
// --------------------------------------------------------------------------
process.stdout.write("\ndeny paths, enforced in the adapter (FR-HA-14)\n")

const rules = core.loadDenyRules(WORK)
is("the shipped deny list is loaded", rules.length === 6, "got " + rules.length)

// opencode has no path-pattern permissions, so a miss here is a real leak of
// a secret file to the model, not a cosmetic difference from Claude Code.
is("a read of .env is denied", core.denied(rules, "read", ".env") === ".env")
is("a write to .env is denied", core.denied(rules, "write", ".env") === ".env")
// Defence in depth: apply_patch is refused before the deny list is consulted,
// but the deny rules still cover it, so enabling it later cannot open a path.
is("apply_patch is covered by the Edit deny rules",
   core.denied(rules, "apply_patch", ".env") === ".env")
is("secrets/** matches a nested path",
   core.denied(rules, "read", "secrets/aws/key.pem") === "secrets/**")

// The bug this pins: denied() matches a raw string, so an unnormalized path
// walked straight past it. `./secrets/x` and `docs/../secrets/x` are ordinary
// ways for a model to write that path, Claude Code blocks all three, and for a
// READ the deny list is the only protection - read is read-only, so no guard
// chain runs behind it. Asserting one spelling is what let this ship.
for (const spelling of ["./secrets/aws/key.pem", "docs/../secrets/aws/key.pem",
                        "secrets/../secrets/aws/key.pem"]) {
  is("denied whichever way it is spelled: " + spelling,
     core.denied(rules, "read", core.toRelative("/repo", spelling)) === "secrets/**")
}
is("an absolute path inside the repo normalizes and is denied",
   core.denied(rules, "read", core.toRelative("/repo", "/repo/secrets/k.pem"))
     === "secrets/**")
is(".env.* matches a suffixed env file",
   core.denied(rules, "read", ".env.production") === ".env.*")
is("an ordinary source file is not denied",
   core.denied(rules, "write", "lib/render-opencode.js") === null)

// A single `*` must not span a separator, or `.env.*` would match half the
// repository once a path happens to contain ".env.".
is("* does not span a path separator",
   core.globMatch("secrets/*", "secrets/a/b") === false)
is("** does span a path separator",
   core.globMatch("secrets/**", "secrets/a/b") === true)

// --------------------------------------------------------------------------
// Payload shape - FR-HA-20
// --------------------------------------------------------------------------
process.stdout.write("\nguard stdin payload (FR-HA-20)\n")

eq("Edit carries the fields the guards read",
   core.toolInputFor("Edit", { filePath: "/r/a.py", oldString: "x", newString: "y" }),
   { file_path: "/r/a.py", old_string: "x", new_string: "y" })

eq("Task carries subagent_type, which guard_models keys on",
   core.toolInputFor("Task", { subagent_type: "developer", prompt: "p", description: "d" }),
   { subagent_type: "developer", description: "d", prompt: "p" })

{
  const p = core.buildPayload("/root", "sess", "PreToolUse", "Write",
                              { file_path: "a", content: "b" })
  eq("the payload matches Claude Code's shape",
     Object.keys(p).sort(),
     ["cwd", "hook_event_name", "permission_mode", "session_id", "tool_input",
      "tool_name"])
  // FR-HA-12: this is what _common.git_cwd and acting_tree resolve against.
  // The DevMesh shim always sent the project root, so a worktree commit was
  // judged against main.
  is("cwd is the acting tree", p.cwd === "/root")
}

// --------------------------------------------------------------------------
// Verdicts - FR-HA-09, FR-HA-10
// --------------------------------------------------------------------------
process.stdout.write("\nverdicts (FR-HA-09, FR-HA-10)\n")

is("exit 0 does not block",
   core.blockMessage([{ code: 0, stdout: "", stderr: "" }], ["g.py"]) === null)

is("exit 2 blocks with the guard's own stderr",
   core.blockMessage([{ code: 2, stdout: "", stderr: "BLOCKED: nope" }], ["g.py"])
     === "BLOCKED: nope")

// Claude Code treats a non-zero, non-2 exit as a non-blocking error. Matching
// that matters: a guard erroring internally must not become a hard stop, or
// the fail-open contract the hooks are written to is broken from outside.
is("exit 1 does not block",
   core.blockMessage([{ code: 1, stdout: "", stderr: "boom" }], ["g.py"]) === null)

{
  // The DevMesh shim resolved code 0 on spawn error, so a machine without
  // python3 ran with every guard silently inert and looked completely normal.
  const msg = core.blockMessage(
    [{ code: core.SPAWN_FAILED, stdout: "", stderr: "ENOENT" }], ["guard_frozen.py"])
  is("a guard that cannot START blocks", msg !== null)
  is("and the message names the guard", (msg || "").includes("guard_frozen.py"))
}

// --------------------------------------------------------------------------
// Context extraction
// --------------------------------------------------------------------------
process.stdout.write("\ncontext extraction\n")

eq("a JSON envelope yields its additionalContext",
   core.contextFrom([{
     code: 0,
     stdout: JSON.stringify({ hookSpecificOutput: { additionalContext: "pinned" } }),
     stderr: "",
   }]),
   ["pinned"])

// session_start and context_pin print bare text, not an envelope.
eq("plain text is taken as context", core.contextFrom([
  { code: 0, stdout: "digest line", stderr: "" }]), ["digest line"])

// A guard printing a JSON-looking string that is not an envelope must not be
// swallowed - losing a digest silently is how the harness goes quiet.
eq("malformed JSON is kept as text",
   core.contextFrom([{ code: 0, stdout: "{oops", stderr: "" }]), ["{oops"])

eq("empty stdout yields nothing",
   core.contextFrom([{ code: 0, stdout: "  \n", stderr: "" }]), [])

// --------------------------------------------------------------------------
process.stdout.write("\n================ SUMMARY ================\n")
process.stdout.write("PASS: " + pass + "   FAIL: " + fail + "\n")
process.stdout.write(fail === 0 ? "ALL GREEN\n" : "RED\n")
process.exit(fail === 0 ? 0 : 1)
