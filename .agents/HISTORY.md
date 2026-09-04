# AGENTS.md — HISTORY

Recorded decisions with git references. Read when relevant to current task.
Acts as simple long-term memory for the project.

## Format

| Date       | Decision   | Rationale   | Git ref          |
| ---------- | ---------- | ----------- | ---------------- |
| YYYY-MM-DD | [describe] | [why]       | [commit hash/tag] |
| 2026-09-01 | Release pipeline: maturin-action wheel matrix (win/linux/mac-arm64 × py3.13/3.14 × GIL/free-threaded) + separate x86_64 macOS cross-compile job + sdist; release version stamped into Cargo.toml via sed before build; PyPI publish gated on PYPI_API_TOKEN secret | Wheels were 0.0.0 single-platform; maturin takes the version from Cargo.toml so the git tag must be injected at build time; GitHub has no Intel macOS runners (macos-15 is arm64) so x86_64 wheels are cross-compiled on the arm64 runner | (this commit) |

## Guidance

- Record decisions that would be costly to rediscover.
- Note false turns and why they were rejected.
- Link to relevant commits.
- Keep entries brief — enough to reconstruct reasoning.
- When this file grows too large, archive older entries to
  `.agents/history/` and leave a pointer here.
