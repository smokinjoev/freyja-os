from __future__ import annotations

import re
import tomllib
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


def test_rev2_operator_console_scripts_are_declared() -> None:
    pyproject = tomllib.loads((REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    scripts = pyproject["project"]["scripts"]

    assert scripts["freyja-certify"] == "certification.cli:main"
    assert scripts["freyja-rev2-preflight-status"] == "certification.rev2_preflight_status:main"


def test_runtime_dockerfiles_copy_declared_top_level_packages() -> None:
    pyproject = tomllib.loads((REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    packages = set(pyproject["tool"]["setuptools"]["packages"])
    package_dirs = pyproject["tool"]["setuptools"].get("package-dir", {})
    top_level_packages = {package.split(".", 1)[0] for package in packages}

    for dockerfile in (
        REPO_ROOT / "deploy/docker/director.Dockerfile",
        REPO_ROOT / "deploy/docker/signal-connector.Dockerfile",
    ):
        content = dockerfile.read_text(encoding="utf-8")
        copied_paths = {
            match.group("source").split("/", 1)[0]
            for match in re.finditer(r"^COPY\s+(?P<source>\S+)\s+", content, flags=re.MULTILINE)
        }

        effective_copied_paths = set(copied_paths)
        for package, package_dir in package_dirs.items():
            package_root = package.split(".", 1)[0]
            source_root = package_dir.split("/", 1)[0]
            if source_root in copied_paths:
                effective_copied_paths.add(package_root)

        missing = top_level_packages - effective_copied_paths
        assert missing == set(), f"{dockerfile.relative_to(REPO_ROOT)} does not copy {sorted(missing)}"
