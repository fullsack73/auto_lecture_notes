from __future__ import annotations

import tomllib
from pathlib import Path


def read_project_version(root: Path | None = None) -> str:
    project_root = root or Path(__file__).resolve().parents[1]
    with (project_root / "pyproject.toml").open("rb") as handle:
        version = tomllib.load(handle)["project"]["version"]
    if not isinstance(version, str) or not version.strip():
        raise ValueError("pyproject.toml project.version must be a non-empty string")
    return version.strip()


if __name__ == "__main__":
    print(read_project_version())
