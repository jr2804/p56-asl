# AGENTS.md — HISTORY

Recorded decisions with git references. Read when relevant to current task.
Acts as simple long-term memory for the project.

## Format

| Date       | Decision   | Rationale   | Git ref          |
| ---------- | ---------- | ----------- | ---------------- |
| YYYY-MM-DD | [describe] | [why]       | [commit hash/tag] |
| 2026-09-01 | Release pipeline: maturin-action wheel matrix (win/linux/mac-arm64 × py3.13/3.14 × GIL/free-threaded) + sdist; release version stamped into Cargo.toml via sed before build; stamp-back job commits released version to main | Wheels were 0.0.0 single-platform; maturin takes the version from Cargo.toml so the git tag must be injected at build time; stamp-back makes `uv add git+...` report real versions | (2026.9.7 era) |
| 2026-10-27 | PyPI publishing via trusted publishing (OIDC, id-token: write, no API-token secret); version stamp made version-agnostic with hard grep assert | Literal `0.0.0` sed pattern silently no-ops once stamp-back keeps a real version in Cargo.toml — shipped mislabeled wheels (release 2026.9.14 → wheels named 2026.9.13; first PyPI upload mislabeled 2026.9.14); assert turns silent no-op into job failure | 0452989 + fae1eae |

## Guidance

- Record decisions that would be costly to rediscover.
- Note false turns and why they were rejected.
- Link to relevant commits.
- Keep entries brief — enough to reconstruct reasoning.
- When this file grows too large, archive older entries to
  `.agents/history/` and leave a pointer here.
