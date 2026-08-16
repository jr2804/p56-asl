# AGENTS.md — FILES

Single source of truth for paths, config keys, and naming conventions.
Kept compact — agents hallucinate less when they know where definitions live.

## Pattern

- One file owns each class of definition (paths, config defaults, enums).
- Import from that file. Never hard-code values in other modules.
- Variables that address files get `_file` suffix; directories get `_dir`.

## Project-specific sources of truth

| What                   | Where                                                           | Key names                                       |
| ---------------------- | --------------------------------------------------------------- | ----------------------------------------------- |
| Package source root    | `src/p56_asl/`  | `__init__.py`, `__about__.py` (version)         |
| Rust core              | `src/*.rs`                                                      | `lib.rs` (PyO3), `prefilter.rs`, `resample.rs`, `actlevel.rs`, `filter.rs`, `histogram.rs`, `params.rs`; compiled to `p56_asl._native` (stubs: `src/p56_asl/_native.pyi`) |
| CLI entry points       | `src/p56_asl/cli/`            | `app.py` (Typer app), `args.py`, `commands.py`  |
| Test suite             | `tests/`                                                        | `test_*.py`, `conftest.py`                      |
| Project metadata       | `pyproject.toml`                                                | `[project]`, `[tool.pytest.ini_options]`        |
| Linter/formatter       | `ruff.toml`                                                     | Ruff rule selection, line length                |
| Type checker           | `ty.toml`                                                       | ty strictness                                   |
| Markdown linter        | `.config/rumdl.toml`                                            | `line-length`, `flavor`, disabled rules         |
| mise tasks             | `.config/mise/config.toml` + `.config/mise/conf.d/*.toml`       | `[tasks.dev]`, `[tasks.test]`, ...              |
| Copier answers         | `.copier-answers.yml`                                           | Template version + answers (regenerated)        |
| Pre-commit config      | `.pre-commit-config.yaml`                                       | Hook list                                       |
| MCP server config      | `.config/mise/conf.d/mcp.toml`                                  | `[tasks.add-mcp-servers]`, tool list            |
| Skills install task    | `.config/mise/conf.d/skills.toml`                               | `[tasks.add-skills]`, skill list                |

## Naming conventions

- **Repository name** (`project_slug`): kebab-case (`my-project`)
- **Python package** (`package_slug`): snake_case (`my_project`)
- **Layout**: `src/p56_asl/`
- **Test files**: `test_<module>.py`
- **Test data** (`tests/data/`): `speech_*.wav` inputs and `*.log.ref` sv56demo
  baseline logs are committed; sv56demo raw outputs (`*.ref`, `*.nrm`, `*.ltl`,
  `voice_24.src`, `voice_32.src`) are gitignored — regenerable via `ref/sv56demo`
- **Template files** (in source template): `filename.ext.jinja` — the `.jinja`
  suffix is stripped on generation
