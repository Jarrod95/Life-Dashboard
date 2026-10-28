"""Protect editable installs against accidental packaging of local data directories."""
from pathlib import Path
import tomllib

from setuptools import find_packages


ROOT = Path(__file__).resolve().parents[1]


def test_only_flask_app_is_discovered():
    config = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    discovery = config["tool"]["setuptools"]["packages"]["find"]
    packages = find_packages(
        where=str(ROOT),
        include=discovery["include"],
        exclude=discovery["exclude"],
    )
    assert "app" in packages
    assert "app.integrations" in packages
    assert "app.services" in packages
    assert all(name == "app" or name.startswith("app.") for name in packages)


def test_graph_dependencies_are_installable_project_requirements():
    config = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    dependencies = config["project"]["dependencies"]
    for name in ("msal", "requests", "filelock"):
        assert any(spec.startswith(name + ">=") for spec in dependencies)
    assert config["build-system"]["build-backend"] == "setuptools.build_meta"
