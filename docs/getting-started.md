# Getting started

This guide takes you from install to your first delivered feature. It works for a brand-new project or a codebase you already have. Allow ten minutes, most of it watching the company work.

## Before you start

You need three things installed:

- Claude Code v2.1.172 or later
- Python 3.8+ and git (the hooks use them)
- Node.js with `npx` if you want browser testing with screenshots

## Step 1: install

Clone claude-company anywhere, then point its installer at your project:

```bash
git clone https://github.com/you/claude-company
bash claude-company/install.sh /path/to/your/project
```

The installer copies the team, the rules, and the process files into your project. It merges with what you already have: your existing Claude settings, MCP servers, and `CLAUDE.md` are extended, never replaced. Run it again after an update and it refreshes claude-company's own files while leaving your state alone.

After it finishes you will see three new things in your project:

- `.claude/`: the agent team, the commands, and the enforcement hooks
- `company/`: the process documents, templates, and state files
- `ORCHESTRATOR.md`: the CEO's private runbook

## Step 2: start the company

Open your project in Claude Code and give the orchestrator your first request:

```text
/orchestrator build me a REST API for tracking workouts, with user accounts
```

You do not need to initialize anything first. The company notices it is new here and onboards itself: it studies your code (or founds a new project from your request), finds your real test and lint commands, and registers them as gates. You can watch this happen; it reports what it found and what it wired.

## Step 3: watch the pipeline

For a feature-sized request, expect this sequence:

1. The CEO sizes the request and dispatches the product manager.
2. The product manager explores 8 to 15 directions, then writes a spec with numbered, testable requirements. The spec records which options it considered and why the winner won.
3. The CEO turns the spec into sealed work orders and spawns a tech lead.
4. The tech lead runs its own team: developers building in parallel, then a QA engineer that clicks through the running app and captures screenshots of the loaded, empty, error, and after-action states.
5. The CEO reruns the gates itself, checks the diffs stayed inside their assignments, reads the screenshots, merges, and reports to you.

Small requests skip most of this. A typo fix gets one developer and the gates, nothing more.

## Step 4: read the delivery report

The company interrupts you for two things only. The delivery report tells you what shipped, shows the evidence (green gates, screenshots), and lists anything that needs your answer. Decisions that belong to you, like anything involving money or a production deploy, wait in `company/state/DECISIONS.md` until you answer them.

To check on things at any time:

```text
/standup
```

You get one screen: done, in flight, blocked, decisions you owe, and current gate status.

## When something gets blocked

Sooner or later you will see a message like `BLOCKED: git commit requires green, fresh gates`. This is the system working. The block message contains the fix: run the gates, and if they are red, repair the failure rather than route around it. Agents get the same messages and follow the same recipes, so most blocks resolve without you.

For a production emergency, tell the orchestrator it is a hotfix. Hooks then log instead of block, and the process catches up afterward.

## Where to go next

- [How it works](how-it-works.md) explains the method: why briefs are sealed, why producers never grade their own work, and what the gates actually check.
- [Customizing](customizing.md) covers adding gates, protecting files, and tuning process depth.
