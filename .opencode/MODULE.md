# MODULE: .opencode

The opencode harness. Everything here except `plugin/` and `lib/` is
GENERATED from `.claude/` by `lib/render-opencode.js`.

## Do not hand-edit the generated files

`agent/`, `command/` and `opencode.json` are rendered output. Edit the source
in `.claude/` and re-render:

```bash
node lib/render-opencode.js          # write, from a repo checkout
node lib/render-opencode.js --check  # drift gate, used by the suite
```

In an INSTALLED project there is no `lib/`, so the same thing is a subcommand:

```bash
npx claude-company render            # write
npx claude-company render --check    # drift gate
```

That subcommand exists because the docs once told users to run the repo path.
A user who customized a role got the customized prompt on Claude Code and the
shipped prompt on opencode, permanently, with nothing to tell them.

`tests/harness/test_render.mjs` fails if the committed tree and the source
disagree, so a hand edit here is caught rather than silently carried.

## What is here

| Path | What it is | Generated? |
|---|---|---|
| `plugin/company-harness.js` | The enforcement adapter. Translates opencode's tool and event hooks into the payload the Python guards read, and runs those same guards. | no |
| `lib/harness-core.js` | The adapter's pure decisions: tool classification, wiring derivation, deny matching, payload shape, verdicts. | no |
| `agent/*.md` | The company roles, frontmatter rewritten for opencode. Bodies are byte-identical to `.claude/agents/`. | yes |
| `command/*.md` | One slash command per skill, pointing at it. | yes |
| `opencode.json` | Wires `CLAUDE.md` as an instruction file. | yes |

## Two things that will bite you

**Every export in `plugin/` must be a function.** opencode calls each export
as a plugin factory. One non-function export fails the whole file with
`Plugin export is not a function`, logged ONLY under `--print-logs`, so the
plugin silently does not load and enforcement silently does not happen. That
is why the pure logic lives in `lib/` - a directory opencode does not scan -
and `plugin/company-harness.js` exports exactly one function.

**Skills are NOT here.** opencode reads `.claude/skills/**/SKILL.md`
natively. A copy under `.opencode/skill/` would register every skill twice,
and the two copies would drift the moment one is edited. The generated
commands exist only to give each skill a `/slash` affordance, which skills
alone do not get.

## Debugging

Set `COMPANY_HARNESS_DEBUG` to a file path to trace plugin load, every tool
decision, and every guard chain:

```bash
COMPANY_HARNESS_DEBUG=/tmp/harness.log opencode run --agent build "..."
```

A harness that silently does nothing looks exactly like one that is working.
This is how you tell them apart.

## Changelog

- 2026-08-23: created (#133, FR-HA-01..20).
