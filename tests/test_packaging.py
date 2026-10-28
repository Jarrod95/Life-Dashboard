"""Verify Python packaging configuration without importing build-only setuptools."""
from pathlib import Path
import tomllib

ROOT = Path(__file__).resolve().parents[1]


def test_only_app_package_is_discoverable():
    config = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    discovery = config["tool"]["setuptools"]["packages"]["find"]
    assert discovery["where"] == ["."]
    assert discovery["namespaces"] is False
    assert discovery["include"] == ["app", "app.*"]
    for excluded in ("tests", "data", "config", "migrations"):
        assert excluded in discovery["exclude"]
        assert excluded + ".*" in discovery["exclude"]

    # Check filesystem layout, independent of setuptools' isolated build environment.
    for name in ("app", "app/integrations", "app/services"):
        assert (ROOT / name / "__init__.py").is_file()


def test_graph_dependencies_are_installable_project_requirements():
    config = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    dependencies = config["project"]["dependencies"]
    for name in ("msal", "requests", "filelock"):
        assert any(spec.startswith(name + ">=") for spec in dependencies)
    assert config["build-system"]["build-backend"] == "setuptools.build_meta"
