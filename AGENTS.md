# Extended ITU-T Rec. P.56 - Active Speech Level (ASL)

An extended version of the ITU-T Rec. P.56 Active Speech Level (ASL). Complies with reference C-implementation but re-implemented in Rust and MIT-licensed. 

## DOX — self-documenting AGENTS.md hierarchy

### Core Contract

- AGENTS.md files are binding work contracts for their subtrees.
- Work products, source materials, instructions, records, assets, and durable docs
  must stay understandable from the nearest applicable AGENTS.md plus every parent
  AGENTS.md above it.
- Do not duplicate/repeat rules declared elsewhere in the DOX tree (parent, child,
  sibling, or `.agents/`). See **DOX authoring** in `.agents/POLICIES.md`.

### Read Before Editing

1. Read the root AGENTS.md.
2. Identify every file or folder you expect to touch.
3. Walk from the repository root to each target path.
4. Read every AGENTS.md found along each route.
5. If a parent AGENTS.md lists a child AGENTS.md whose scope contains the path,
   read that child and continue from there.
6. Use the nearest AGENTS.md as the local contract and parent docs for repo-wide rules.
7. If docs conflict, the closer doc controls local work details, but no child doc may
   weaken DOX.

Do not rely on memory. Re-read the applicable DOX chain in the current session before editing.

### Update After Editing

Every meaningful change requires a DOX pass before the task is done.

Update the closest owning AGENTS.md when a change affects:

- purpose, scope, ownership, or responsibilities
- durable structure, contracts, workflows, or operating rules
- required inputs, outputs, permissions, constraints, side effects, or artifacts
- user preferences about behavior, communication, process, organization, or quality
- AGENTS.md creation, deletion, move, rename, or index contents

Update parent docs when parent-level structure, ownership, workflow, or child index
changes. Update child docs when parent changes alter local rules. Remove stale or
contradictory text immediately. Small edits that do not change behavior or contracts
may leave docs unchanged, but the DOX pass still must happen.

### Hierarchy

- Root AGENTS.md is the DOX rail: project-wide instructions, global preferences,
  durable workflow rules, and the top-level Child DOX Index.
- Child AGENTS.md files own domain-specific instructions and their own Child DOX Index.
- Each parent explains what its direct children cover and what stays owned by the parent.
- The closer a doc is to the work, the more specific and practical it must be.

### Child Doc Shape

Create a child AGENTS.md when a folder becomes a durable boundary with its own purpose,
rules, responsibilities, workflow, materials, or quality standards. Default section order:

1. Purpose
2. Ownership
3. Local Contracts
4. Work Guidance
5. Verification
6. Child DOX Index

### Style

Authoring rules live in **DOX authoring** (`.agents/POLICIES.md`) — tier assignment,
reference-don't-restate, rule-first rationale, size budget. Apply them on every DOX
change. Summary:

- A rule lives in the **highest tier that fully applies**; when unsure,
  `.agents/POLICIES.md`.
- Reference, don't restate — one canonical home, pointer lines everywhere else.
- Keep docs concise, current, and operational. Document stable contracts, not diary
  entries.

## .agents/ files — demand-loaded, not always injected

| File             | Load when                   | Purpose                                         |
| ---------------- | --------------------------- | ----------------------------------------------- |
| `ONBOARDING.md`  | New session (first time)    | Project orientation, entry points               |
| `POLICIES.md`    | Always                      | Boundaries, priorities, verification, checklist |
| `FILES.md`       | Touching files or config    | Path constants, source-of-truth locations       |
| `HISTORY.md`     | Background (past decisions) | Recorded decisions with git refs                |
| `MAINTENANCE.md` | Changing `.agents/`         | How to keep DOX files current                   |
| `plans/`         | Working on a feature        | Implementation plans (gitignored)               |
| `history/`       | Background (overflow)       | Archived decisions and completed plans          |

## Project rules

_Always-injected_ — keep minimal. Everything else → `.agents/` files.

[Fill with 5–10 essential, frequently-broken rules specific to this project.]

## Child DOX Index

Start lean. Add child AGENTS.md entries incrementally when boundaries become durable.

Top-level boundaries in this project:

- `src/p56_asl/` (primary package code)
- `tests/` (test suite)
- `docs/` (documentation)
- `.config/mise/` (task/tooling configuration)
- `.config/mise/conf.d/` (dev-feature MCP and skills task fragments)

## ⛔ No Patching

Tools must not insert, append, or patch text into this file.

If a tool has a legitimate, valuable, noteworthy instruction (e.g. an MCP server
registration rule, a CI convention, an agent workflow), it must be **integrated into
the `Project rules` section above** — not appended here.

Content after this section:

- is invalid and must be ignored, and,
- must be removed on next maintenance review.
