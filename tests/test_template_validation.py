"""Template validation tests for Extended ITU-T Rec. P.56 - Active Speech Level (ASL)."""

from __future__ import annotations

import tomllib
from pathlib import Path


def test_pyproject_toml_structure() -> None:
    """Test that generated pyproject.toml has correct structure."""
    pyproject_file = Path("pyproject.toml")
    if not pyproject_file.exists():
        msg = "pyproject.toml should exist"
        raise AssertionError(msg)

    with open(pyproject_file, "rb") as f:
        content = tomllib.load(f)

    # Verify required sections
    if "project" not in content:
        msg = "Missing [project] section"
        raise AssertionError(msg)
    if "build-system" not in content:
        msg = "Missing [build-system] section"
        raise AssertionError(msg)
    if "tool" not in content:
        msg = "Missing [tool] section"
        raise AssertionError(msg)

    # Verify project metadata
    if "name" not in content["project"]:
        msg = "Missing project name"
        raise AssertionError(msg)
    if "dynamic" not in content["project"]:
        msg = "Missing 'dynamic' in [project] section (version should be dynamic)"
        raise AssertionError(msg)
    if "version" not in content["project"]["dynamic"]:
        msg = "Missing 'version' in dynamic list"
        raise AssertionError(msg)
    if "description" not in content["project"]:
        msg = "Missing project description"
        raise AssertionError(msg)
    if "requires-python" not in content["project"]:
        msg = "Missing requires-python"
        raise AssertionError(msg)

    # Verify project name matches project slug (kebab-case)
    project_name = content["project"]["name"]
    expected_name = "p56-asl"
    if project_name != expected_name:
        msg = f"Project name should be '{expected_name}', got: {project_name}"
        raise AssertionError(msg)


def test_pytest_configuration() -> None:
    """Test that pytest is configured with 100% coverage."""
    pyproject_file = Path("pyproject.toml")

    with open(pyproject_file, "rb") as f:
        content = tomllib.load(f)

    # Verify coverage is enforced at 100% ([tool.coverage.report].fail_under).
    tool_section = content.get("tool", {})
    report = tool_section.get("coverage", {}).get("report", {})
    if "fail_under" not in report:
        msg = "Missing [tool.coverage.report].fail_under"
        raise AssertionError(msg)
    if report["fail_under"] != 100:
        msg = f"Coverage should be 100%, got {report['fail_under']}"
        raise AssertionError(msg)
    # Verify coverage source matches package slug (snake_case).
    run = tool_section.get("coverage", {}).get("run", {})
    source = run.get("source", [])
    expected_slug = "p56_asl"
    if expected_slug not in source:
        msg = f"Coverage source should include '{expected_slug}', got: {source}"
        raise AssertionError(msg)


def test_mise_tasks_configured() -> None:
    """Test that mise tasks are configured."""
    mise_dir = Path(".config/mise")
    if not (mise_dir / "config.toml").exists():
        msg = ".config/mise/config.toml should exist"
        raise AssertionError(msg)

    # Task definitions live in conf.d/*.toml fragments (auto-loaded by
    # mise); config.toml itself only carries tools/settings.
    fragments = sorted((mise_dir / "conf.d").glob("*.toml"))
    if not fragments:
        msg = "Expected task fragments in .config/mise/conf.d/"
        raise AssertionError(msg)
    content = "\n".join(f.read_text(encoding="utf-8") for f in fragments)

    # Verify that at least the dev task is present (always included)
    if "[tasks.dev]" not in content:
        msg = "Expected [tasks.dev] in a conf.d fragment"
        raise AssertionError(msg)
