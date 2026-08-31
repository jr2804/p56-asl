# AGENTS.md — ONBOARDING

Read this when starting a new session. After first read, only revisit when
project structure or tooling changes significantly.

## Project

An extended version of the ITU-T Rec. P.56 Active Speech Level (ASL).
Complies with reference C-implementation but re-implemented in Rust and
MIT-licensed. Full docs at `README.md` or `docs/`.

## Quick start

```bash
mise dev        # install dependencies (uv sync --dev)
mise test       # run pytest with coverage
mise lint       # ruff + ty + codespell
mise format     # ruff format + isort + undersort
mise all        # test + lint + format in one pass
```

## Entry points (read these first)

| File / Section | Why |
| -------------- | --- |
| `AGENTS.md` | Root rail — rules + `.agents/` index |
| `.agents/POLICIES.md` | Boundaries, priorities, verification |
| `.agents/FILES.md` | Source-of-truth locations for this package |
| `pyproject.toml` | Dependencies, pytest config, build backend |
| `.copier-answers.yml` | Template answers (regenerated on `copier update`) |

## Layout

- **`src/p56_asl/`** — primary package source (src layout)
- **`tests/`** — pytest suite (100% coverage gate)
- **`src/p56_asl/cli/`** — Typer CLI
- **`docs/`** — MkDocs Material documentation (mkdocs.yml)
- **`.config/mise/`** — task runner config (`config.toml` + `conf.d/` fragments)

## Where to dig deeper

- `docs/` — user-facing documentation
- `.agents/HISTORY.md` — past decisions and rationale
- Source-tree AGENTS.md files — local contracts for each area

## Available tools

If MCP dev-features are enabled (`include_mcp_tasks`), the following may be
available after running `mise run add-mcp-servers <agent>` and `mise run
add-skills`:

- **repowise** — architecture overview, risk, health scores, change-risk
- **codegraph** — symbol search, call graphs, dependency maps
- **grepai** — semantic code search by meaning, not text
- **bd / beads** — distributed issue tracker (if `tracking` skill category enabled)
- Various slop/dead-code detectors (see `.config/mise/conf.d/skills.toml`)
