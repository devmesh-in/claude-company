# claude-company

An AI software company you drop into your repo.

You describe what you want built. A CEO agent plans the work, staffs a team of AI product managers, architects, tech leads, developers, and QA engineers, builds it, tests it in a real browser with screenshots, and reports back with proof. The quality rules are enforced by scripts that block bad actions, not by instructions the AI is asked to follow.

Works with [Claude Code](https://claude.com/claude-code). One install command, one command to run.

```text
you>  /orchestrator build me a waitlist page with an admin view

CEO   sized the request: feature
CEO   product-manager wrote the spec (3 options considered, picked #2)
CEO   tech-lead "waitlist" spawned 2 developers + 1 QA engineer
QA    captured: loaded / empty / error / after-signup screenshots
CEO   gates: lint PASS  typecheck PASS  tests PASS (stamped)
CEO   merged. Here is what shipped, the evidence, and one decision I need from you.
```

## Why this exists

Most multi-agent coding frameworks write their process as prompts and hope the model follows them. Under pressure, models skip steps: they commit failing code, edit tests until they pass, and mark their own work as done. claude-company replaces hope with enforcement: hooks (small scripts that run before every action) block the bad action itself, and every block is logged so you can see the system working.

## How it works

1. You install claude-company into your project and ask for something.
2. The CEO (your main Claude session) sizes the request: an idea to explore, a small fix, a feature, or a whole product. Ceremony scales to match, so a typo fix never gets a committee.
3. For features and products, staff agents plan first. The product manager generates 8 to 15 candidate directions, then writes a spec from the strongest one. The architect proposes 2 to 3 designs, scores them, and picks one with written reasons.
4. Tech leads build. Each lead runs its own team: developers working in parallel on separate directories, plus a QA engineer that clicks through the running app in a real browser and captures screenshots.
5. The CEO verifies with evidence: reruns the test gates, checks that nobody edited files outside their assignment, and reads the screenshots. Then it merges and reports to you.

You hear from the company for two reasons only: decisions that belong to you (money, deploys, scope) and delivery reports with evidence. Everything else runs itself, including the paperwork.

```text
You            decide business policy and deploys. Nothing ships to production without you.
 CEO           your main Claude session. Plans, staffs, verifies, reports.
   ideation-strategist   explores the option space so the first idea is never the only idea
   product-manager       writes specs with testable requirements
   architect             picks the design from scored alternatives
   tech-lead             runs its own team, one per workstream
     developer           builds exactly what its work order says
     qa-engineer         drives the real app, captures screenshots
   auditor               independent review before big merges
   security-reviewer, devops-engineer, docs-librarian   on call
```

## Get started

1. Clone this repo and run the installer against your project:

```bash
git clone https://github.com/you/claude-company
bash claude-company/install.sh /path/to/your/project
```

2. Open your project in Claude Code and start the company:

```text
/orchestrator build me <what you want>
```

There is no setup step. On first contact the company onboards itself: it studies your codebase (or treats your request as the founding brief of a new one), finds your real test and lint commands, and wires them in as gates. The installer never overwrites your existing settings, and running it twice changes nothing.

Read the [getting started guide](docs/getting-started.md) for a full walkthrough.

## The rules it enforces

Each rule is a hook: a script that runs before the action and blocks it when the rule is broken. When a hook blocks an agent, the message tells the agent how to fix its own compliance, so the process self-heals instead of stalling.

| Rule | What gets blocked |
|---|---|
| Protected files stay protected | Edits to `.env`, lockfiles, shipped migrations, and any file your project marks as frozen |
| No commit while tests fail | `git commit` when the gate suite is red, stale, or was never run |
| No code without a plan | Source-code changes when no approved work order exists |
| Tests are the referee | Editing or deleting tests that the current work order does not cover |
| No AI filler in writing | Em dashes, smart quotes, and stock AI phrases in anything written |
| No quitting early | Ending a work session while the active task's gates are red |

Every block is one line in `company/state/adherence.log`, so enforcement is visible, not claimed. All hooks fail open: an internal error lets the action through rather than jamming your session.

## Commands

| Command | What it does |
|---|---|
| `/orchestrator` | Start or resume the company. The only command you need day to day |
| `/brainstorm` | Explore ideas in parallel and get an options memo with a recommendation |
| `/standup` | One-screen status: done, in flight, blocked, decisions you owe |
| `/feature` | Run one feature through the full pipeline |
| `/gates` | Run the test gates and stamp the result |
| `/company-init`, `/onboard` | Found the company explicitly (new project or existing codebase) |
| `/cr` | File or decide a change request against a protected file |

## What stays yours

No agent, including the CEO, ever decides: production deploys, database migrations in production, anything involving money, weakening a protection rule, or business policy. The company merges to your main branch; shipping to users is a button only you press.

## Customizing

Gates, protected files, team roles, and process documents are plain files you can read and edit. The [customizing guide](docs/customizing.md) covers the common changes: adding gates, freezing files, and tuning how much process each request gets.

## FAQ

**How much does it cost to run?** More than a single Claude session: parallel agents multiply token use. The company counters this by scaling ceremony to the task, so small fixes get one developer and no meetings.

**Does it work on an existing codebase?** Yes. It reads your code, adopts your conventions, and wires your existing test commands in as gates. It adapts to your project, not the other way around.

**What if a gate is wrong or blocks me unfairly?** Gates are your own commands in `company/gates.config`; edit them anytime. For real emergencies there is a hotfix mode that logs instead of blocks.

**Can I see what it decided and why?** Yes. Specs record the options considered, memos record the roads not taken, decisions wait for you in `company/state/DECISIONS.md`, and the adherence log records every block.

## Requirements

- Claude Code v2.1.172 or later (nested agents)
- Python 3.8+, bash, git
- Node.js with `npx` for browser testing (Playwright)

## Learn more

- [Getting started](docs/getting-started.md): install to first delivery, step by step
- [How it works](docs/how-it-works.md): the method behind the company
- [Customizing](docs/customizing.md): gates, frozen files, roles, and process depth
- `company/METHOD.md`: the canon the agents themselves follow
