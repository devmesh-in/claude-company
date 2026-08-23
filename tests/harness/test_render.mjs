#!/usr/bin/env node
/**
 * tests/harness/test_render.mjs - the .claude -> .opencode renderer.
 *
 * The load-bearing property is FR-HA-01: `.claude/` is the source of truth and
 * nothing here may write to it. That is what makes "the Claude side cannot
 * regress" a fact about the design rather than a promise, so it is asserted
 * directly rather than assumed.
 */

import * as fs from "node:fs"
import * as os from "node:os"
import * as path from "node:path"
import { execFileSync } from "node:child_process"
import { createRequire } from "node:module"
import { fileURLToPath } from "node:url"

const HERE = path.dirname(fileURLToPath(import.meta.url))
const REPO = path.resolve(HERE, "..", "..")
const require = createRequire(import.meta.url)
const renderer = require(path.join(REPO, "lib", "render-opencode.js"))

let pass = 0
let fail = 0
const ok = (d) => { pass++; process.stdout.write("  \x1b[32mPASS\x1b[0m " + d + "\n") }
const no = (d, x) => {
  fail++
  process.stdout.write("  \x1b[31mFAIL\x1b[0m " + d + "\n")
  if (x) process.stdout.write("       " + x + "\n")
}
const is = (d, c, x) => (c ? ok(d) : no(d, x))
const eq = (d, a, e) => {
  const as = JSON.stringify(a)
  const es = JSON.stringify(e)
  as === es ? ok(d) : no(d, "expected " + es + "\n       actual   " + as)
}

// --------------------------------------------------------------------------
process.stdout.write("\nfrontmatter and tool mapping (FR-HA-02)\n")

{
  const { keys, body } = renderer.splitFrontmatter(
    '---\nname: x\ndescription: "a: b, with, commas"\nmodel: opus\n---\n\nBODY\n')
  // Values pass through verbatim. Re-serializing a description that carries
  // colons, quotes and escaped newlines is how a role prompt gets quietly
  // mangled.
  eq("a description with colons and commas survives whole",
     keys.description, '"a: b, with, commas"')
  is("the body is separated from the frontmatter", body.trim() === "BODY")
}

eq("Agent(...) is split as one entry, not on its inner commas",
   renderer.splitToolList("Agent(developer, qa-engineer), Bash, Read"),
   ["Agent(developer, qa-engineer)", "Bash", "Read"])

{
  // Claude's disallowedTools is a DENYLIST.
  const { perms } = renderer.permissionsFor({
    disallowedTools: "Agent, Edit, Write, MultiEdit, NotebookEdit" })
  eq("a denylist becomes per-key denies",
     perms, { task: "deny", edit: "deny", write: "deny" })
}

{
  // Claude's tools: is an ALLOWLIST, and the part that carries the hierarchy
  // rule is which agents may be spawned. Reversing this would let a tech-lead
  // spawn anything.
  const { perms } = renderer.permissionsFor({
    tools: "Agent(developer, qa-engineer), Bash, Read" })
  eq("an allowlist becomes a wildcard deny plus named allows",
     perms.task, { "*": "deny", developer: "allow", "qa-engineer": "allow" })
}

{
  const { unmapped } = renderer.permissionsFor({ disallowedTools: "Nonesuch" })
  is("a tool with no opencode counterpart is reported, not dropped silently",
     unmapped.includes("Nonesuch"))
}

// --------------------------------------------------------------------------
process.stdout.write("\ngenerated agents (FR-HA-02, FR-HA-15)\n")

{
  const src = fs.readFileSync(
    path.join(REPO, ".claude", "agents", "tech-lead.md"), "utf8")
  const { text } = renderer.renderAgent("tech-lead", src)

  // FR-HA-15. A model line here would reintroduce per-role tiering on
  // opencode, which the owner ruled out; the adapter also blocks it at spawn,
  // and these two must agree.
  is("no model is pinned", !/^model:/m.test(text))
  is("mode is subagent", /^mode: subagent$/m.test(text))
  is("the wildcard deny precedes the named allows, since last match wins",
     text.indexOf('"*": deny') < text.indexOf('"developer": allow'))

  // The role prompt is the product. A renderer that paraphrases it is worse
  // than no renderer.
  const body = renderer.splitFrontmatter(src).body.replace(/\s+$/, "")
  is("the role body is carried through byte-for-byte", text.includes(body))
  is("the file says it is generated", text.includes("GENERATED from .claude/agents/tech-lead.md"))
}

{
  const src = fs.readFileSync(
    path.join(REPO, ".claude", "skills", "gates", "SKILL.md"), "utf8")
  const text = renderer.renderCommand("gates", src)
  is("a command points at the skill", text.includes("`gates` skill"))
  is("a command takes arguments", text.includes("$ARGUMENTS"))
  // opencode reads .claude/skills natively, so duplicating the body here
  // would give every instruction two copies that can disagree. Compared
  // against the BODY, not against a keyword: the description legitimately
  // repeats terms the body uses, and asserting on one of those would fail for
  // the wrong reason.
  const skillBody = renderer.splitFrontmatter(src).body.trim()
  is("a command does NOT duplicate the skill body",
     skillBody.length > 0 && !text.includes(skillBody))
  is("a command is far shorter than the skill it points at",
     text.length < skillBody.length)
}

// --------------------------------------------------------------------------
process.stdout.write("\nthe Claude side is never written (FR-HA-01)\n")

{
  // Render into a COPY and compare .claude/ before and after. This is the
  // whole safety argument for the design, so it is checked mechanically.
  const work = fs.mkdtempSync(path.join(os.tmpdir(), "cc-render-"))
  process.on("exit", () => fs.rmSync(work, { recursive: true, force: true }))
  for (const sub of [["agents"], ["skills"], ["hooks"]]) {
    fs.cpSync(path.join(REPO, ".claude", ...sub), path.join(work, ".claude", ...sub),
              { recursive: true })
  }
  fs.copyFileSync(path.join(REPO, ".claude", "settings.json"),
                  path.join(work, ".claude", "settings.json"))

  const fingerprint = (dir) => {
    const out = []
    const walk = (d) => {
      for (const e of fs.readdirSync(d, { withFileTypes: true }).sort(
        (a, b) => a.name.localeCompare(b.name))) {
        const p = path.join(d, e.name)
        if (e.isDirectory()) walk(p)
        else out.push(path.relative(dir, p) + ":" + fs.statSync(p).size)
      }
    }
    walk(dir)
    return out.join("\n")
  }

  const before = fingerprint(path.join(work, ".claude"))
  execFileSync(process.execPath,
               [path.join(REPO, "lib", "render-opencode.js"), "--root", work],
               { stdio: "pipe" })
  const after = fingerprint(path.join(work, ".claude"))
  is("rendering leaves .claude/ untouched", before === after)
  is("rendering produced .opencode/agent/",
     fs.existsSync(path.join(work, ".opencode", "agent", "tech-lead.md")))

  // A role deleted at the source must not leave a generated orphan claiming
  // the company still has that role.
  fs.writeFileSync(path.join(work, ".opencode", "agent", "ghost.md"), "stale\n")
  execFileSync(process.execPath,
               [path.join(REPO, "lib", "render-opencode.js"), "--root", work],
               { stdio: "pipe" })
  is("a generated orphan is removed on re-render",
     !fs.existsSync(path.join(work, ".opencode", "agent", "ghost.md")))
}

// --------------------------------------------------------------------------
process.stdout.write("\ndrift gate (FR-HA-05)\n")

{
  // BR-HA-01: the committed tree must equal what the source renders to, or the
  // review that approved .opencode/ approved something else. This gate IS the
  // no-hand-edits rule; without it the rule is only a comment.
  let code = 0
  try {
    execFileSync(process.execPath,
                 [path.join(REPO, "lib", "render-opencode.js"), "--check"],
                 { cwd: REPO, stdio: "pipe" })
  } catch (e) {
    code = e.status
  }
  is("the committed .opencode/ matches .claude/", code === 0,
     "run: node lib/render-opencode.js")
}

// --------------------------------------------------------------------------
process.stdout.write("\n================ SUMMARY ================\n")
process.stdout.write("PASS: " + pass + "   FAIL: " + fail + "\n")
process.stdout.write(fail === 0 ? "ALL GREEN\n" : "RED\n")
process.exit(fail === 0 ? 0 : 1)
