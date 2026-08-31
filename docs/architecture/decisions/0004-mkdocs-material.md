---
title: "0004 — MkDocs Material for documentation"
---

## 0004 — MkDocs Material for documentation

**Date**: 2026-08-17
**Status**: Accepted

### Context

The project template shipped Zensical as the documentation generator.
Zensical 0.0.55 panics on Windows in its file watcher (upstream issue

## 786) in every link mode, which makes both `docs-serve` and builds

unreliable on Windows development machines.

### Decision

Documentation is built with MkDocs Material (`mkdocs.yml`). Math renders
via `pymdownx.arithmatex` (generic) + MathJax 3 from CDN, with display
math as ` ```math ` fenced blocks; the API reference uses mkdocstrings
over `src/`; deployment to GitHub Pages runs through
`.github/workflows/docs.yml` on pushes to `main`.

### Consequences

- Stable, widely documented toolchain; no watcher panics.
- `pymdownx.snippets` and `markdown-exec` must be declared explicitly
  (Zensical enabled them implicitly).
- Zensical is banned in `docs/` verification until upstream stabilizes.
