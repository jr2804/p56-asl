# AGENTS.md — HISTORY

Recorded decisions with git references. Read when relevant to current task.
Acts as simple long-term memory for the project.

## Format

| Date       | Decision   | Rationale   | Git ref          |
| ---------- | ---------- | ----------- | ---------------- |
| YYYY-MM-DD | [describe] | [why]       | [commit hash/tag] |
| 2026-09-01 | Release pipeline: 16-job maturin-action wheel matrix (win/linux/mac-arm/mac-intel × py3.13/3.14 × GIL/free-threaded) + sdist; release version stamped into Cargo.toml via sed before build; PyPI publish gated on PYPI_API_TOKEN secret | Wheels were 0.0.0 single-platform; maturin takes the version from Cargo.toml, so the git tag must be injected at build time | (this commit) |

## Guidance

- Record decisions that would be costly to rediscover.
- Note false turns and why they were rejected.
- Link to relevant commits.
- Keep entries brief — enough to reconstruct reasoning.
- When this file grows too large, archive older entries to
  `.agents/history/` and leave a pointer here.
