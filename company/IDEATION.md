# IDEATION.md - How this company thinks before it builds

Great builds die in the first five minutes, when the first workable idea gets
mistaken for the best one. This playbook is how the company generates and
selects ideas - for products, features, and architectures - at a
production-grade bar.

Two standing doctrines:

1. **Diverge before you converge.** Never spec, design, or build the first
   idea that works. Generate a real option space (the patterns below), then
   converge with explicit criteria. The road not taken is recorded in the
   options memo so the client can see it and veto the choice.
2. **Autonomous posture.** Ideation never interviews the client. The company
   runs the patterns itself, converges to a recommendation, and delivers an
   options memo (`company/templates/OPTIONS-TEMPLATE.md`) with veto rights.
   The only exceptions are the standing owner-escalation topics (money,
   business policy), which land as decisions in the memo, not questions
   mid-flow.

## The patterns (pick by goal, use at least three categories per divergence)

**Goal: quantity - fill the option space fast (8-15 directions)**

1. **Perspective multiplication.** Generate ideas as N distinct stakeholders
   would see the problem: the daily power user, the first-time user, the
   admin, the attacker, the support engineer, the CFO, the competitor. Each
   perspective must produce at least one idea the others would not.
2. **Feature decomposition (SCAMPER).** Take the current or obvious solution
   and systematically Substitute, Combine, Adapt, Modify/Magnify, Put to
   other uses, Eliminate, Reverse each major attribute. Eliminate is the
   most underused: what if this feature simply did not exist - what would
   users do, and is THAT the product?

**Goal: depth - refine promising directions**

3. **Constraint variation.** Re-solve the same problem under artificial
   constraints, one at a time: 10x less budget, zero new dependencies, must
   ship in a day, must work offline, one-tenth the UI. Constraints expose
   which parts of a design are load-bearing and which are habit.
4. **Chain refinement.** Take the strongest idea and run three explicit
   passes: strip it to its irreducible core; find the weakest assumption and
   redesign without it; then add back only what earns its place.

**Goal: breakthrough - escape the local maximum**

5. **Inversion.** State the goal, then design for the opposite: "how would we
   guarantee users churn / data corrupts / the team ships slowly" - then read
   the anti-design as a checklist of what the real design must prevent. The
   negative space usually contains at least one requirement nobody listed.
6. **Extreme scaling.** Redesign as if usage were 100x, then as if it were
   1/100th (a single user who pays 100x). The 100x version surfaces the
   architecture; the 1/100th version surfaces the actual value.
7. **Analogical transfer.** Name three domains that solved a structurally
   similar problem (logistics, gaming, banking, biology) and port their
   mechanism, not their surface. Say the mapping out loud: "X is to us what
   the dispatch board is to trucking."

**Goal: differentiation - win against alternatives**

8. **Competitive positioning matrix.** List the real alternatives (including
   "do nothing" and spreadsheets), score them on the two axes clients
   actually feel, and design for the empty quadrant. An idea that lands in
   an occupied quadrant needs a 10x edge or a different quadrant.

**Goal: customer-centric - features that matter**

9. **Journey friction walk.** Walk the primary persona's end-to-end journey
   step by step; at each step ask what they feel, what they wait for, what
   they re-enter, what they screenshot to send someone. Every friction point
   is a feature candidate ranked by frequency x pain.
10. **Assumption challenge.** List the premises the request smuggles in
    ("users want a dashboard", "this needs accounts"), then generate one
    idea per premise that drops it. Half of production-grade simplicity is
    a premise someone refused.

## Output discipline (applies to every divergence)

- Ideas are NUMBERED, in a table: `# | Idea | Reasoning | Production risks |
  Trade-offs`. Reasoning is mandatory - an idea without a why is a slogan.
- Convergence uses explicit, written criteria (client value, production
  risk, cost to build, cost to operate, reversibility) - never vibes.
- Production-grade filter before any idea reaches the memo: how does it
  fail, how is it observed, what does it cost at 10x, can it be rolled back,
  what does it force on future modules?
- The memo records winners AND the strongest rejected option with the reason
  it lost. If the strongest rejected option keeps winning arguments later,
  the convergence was wrong - reopen it.

## Who runs what

- **product-manager**: divergence is mandatory before any spec (8-15
  directions, at least 3 pattern categories); the spec carries an "options
  considered" section.
- **architect**: the solutioning gate - 2-3 scored architecture options
  before any program build; the memo shows the scoring.
- **ideation-strategist**: deep divergence on demand. For big engagements
  the CEO spawns 2-3 strategists in parallel with different assigned lenses
  and synthesizes their outputs into one memo.
- **CEO**: classifies fuzzy or new-idea requests as `ideation` engagements,
  synthesizes memos, owns the recommendation, and proceeds on it unless the
  client vetoes.
