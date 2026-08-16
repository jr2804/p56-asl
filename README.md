# Extended ITU-T Rec. P.56 - Active Speech Level (ASL)

> An extended version of the ITU-T Rec. P.56 Active Speech Level (ASL). Complies with reference C-implementation but re-implemented in Rust and MIT-licensed.

<!-- markdownlint-disable MD033 -->
<p align="center">
  <a href="#"><img alt="Python 3.13+" src="https://img.shields.io/badge/python-3.13%2B-3776ab?logo=python"></a>
  <a href="LICENSE"><img alt="License" src="https://img.shields.io/badge/license-MIT-green.svg"></a>
  <a href="https://github.com/jr2804/p56-asl/actions"><img alt="CI" src="https://github.com/jr2804/p56-asl/actions/workflows/ci.yml/badge.svg"></a>
</p>
<!-- markdownlint-enable MD033 -->

---

## Quick Start

```bash
# Clone and set up
git clone https://github.com/jr2804/p56-asl.git
cd p56-asl
mise dev
```

## Usage

### Running Tests

```bash
mise test
# or
uv run pytest
```

### Code Quality

```bash
mise lint       # ruff + ty + codespell
mise format     # ruff format + isort
mise all        # test + lint + format in one pass
```

### CLI Commands

```bash
uv run p56-asl --help         # app/script entry
uv run -m p56_asl --help      # module entry
uv run p56-asl --version      # show version

# Measure the active speech level (aliases: calc, calculate)
uv run p56-asl measure input.wav
uv run p56-asl measure input.wav --pre-filter nb --format json
uv run p56-asl measure input.wav --fs 16000 --channels "1, 2" --time-start 0.5

# Calibrate by a dB gain (alias: scale); no sign means +
uv run p56-asl calibrate input.wav 3.01 output.wav   # +3.01 dB
uv run p56-asl calibrate input.wav -3.01             # in place, -3.01 dB
```

See `docs/reference/cli.md` for all options.

## Development

### Pre-commit Hooks

```bash
pre-commit install
pre-commit run --all-files
```

### Documentation

```bash
mise docs-serve          # live preview at http://localhost:8000
mise docs-build          # build static site to site/
```

## CI/CD

GitHub Actions runs on every push and PR:

| Workflow | Triggers | Jobs |
|----------|----------|------|
| **CI** (`ci.yml`) | push, PR to main | test matrix (3.13, 3.14) + lint + type-check |
| **Release** (`release.yml`) | tag `v*` | build + publish to PyPI |

## AI Dev-Features

This project includes optional AI-agent tooling. After `mise dev`, install with:

```bash
mise run add-mcp-servers <agent>   # register MCP servers (claude, codex, gemini, ...)
mise run add-skills                # install agent skills
```

Enabled dev-features are listed in `.config/mise/conf.d/mcp.toml` and
`.config/mise/conf.d/skills.toml`.

## Project Structure

```text
p56-asl/
├── .config/mise/               # mise task definitions
├── .github/workflows/          # CI + release workflows
├── docs/                       # MkDocs documentation
├── src/p56_asl/     # Source package
│   ├── __init__.py
│   ├── __about__.py
│   └── cli/
│       ├── __init__.py
│       ├── app.py
│       ├── args.py
│       └── commands.py
├── tests/                      # Test suite
├── .copier-answers.yml         # Template version tracking
├── pyproject.toml              # uv + hatch + pytest config
├── ruff.toml                   # Linter + formatter config
├── ty.toml                     # Type checker config
└── README.md
```

## Tech Stack

| Layer | Tool | Purpose |
|-------|------|---------|
| Package manager | [uv](https://docs.astral.sh/uv/) | Fast installs, deterministic lockfile |
| Task runner | [mise](https://mise.jdx.dev/) | DAG-based tasks, tool version management |
| Linter + formatter | [ruff](https://docs.astral.sh/ruff/) | Single-binary code quality |
| Type checker | [ty](https://github.com/google/ty) | Strict type checking |
| Testing | [pytest](https://pytest.org/) | Test framework with 100% coverage gate |
| Spell check | [codespell](https://github.com/codespell-project/codespell) | Code and doc spell checking |
| Documentation | [Zensical](https://github.com/zensical/zensical) | MkDocs Material with executable examples |
| Versioning | [uv-dynamic-versioning](https://github.com/ninoseki/uv-dynamic-versioning) | Git tag-based versioning |
| Hooks | [pre-commit](https://pre-commit.com/) | Automated quality gate |
| CI/CD | GitHub Actions | Test matrix + PyPI release |

## License

MIT — see [LICENSE](LICENSE) for details.

---

Generated from [copier-uv-plus](https://codeberg.org/jr2804/copier-uv-plus).
