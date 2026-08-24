---
description: Prepare a release for the owner to ship - verify the readiness list mechanically, then assemble the changelog, semver proposal, and release notes into the filled RELEASE-TEMPLATE, ending at a proposal entry on DECISIONS.md. Owner/CEO invoked only. Use when the user says /release, "prepare a release", "cut a release", or "are we ready to ship". It never runs `git tag`, `npm publish`, or deploy. `gh release create` runs only when the owner instructed that ship in-session; release.yml then publishes to npm via OIDC.
---

<!-- GENERATED from .claude/skills/release/SKILL.md by `claude-company render`. Do not edit: edit the source and re-render. -->

Use the skill tool to load the `release` skill, then follow it exactly as written.

$ARGUMENTS
