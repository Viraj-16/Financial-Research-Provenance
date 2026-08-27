"""Project path resolution for FRP.

FRP stores all metadata and artifacts inside a ``.frp/`` directory located at
the project root (the directory in which ``frpx init`` was run). This mirrors
the ``.git/`` convention and keeps provenance local-first.
"""

from __future__ import annotations

from pathlib import Path

FRP_DIR_NAME = ".frp"
DB_FILE_NAME = "frp.db"
CONFIG_FILE_NAME = "config.toml"
ARTIFACTS_DIR_NAME = "artifacts"


class ProjectNotFoundError(Exception):
    """Raised when no ``.frp/`` project can be located from the given path."""


class ProjectPaths:
    """Resolved filesystem paths for an FRP project."""

    def __init__(self, root: Path) -> None:
        self.root = root.resolve()

    @property
    def frp_dir(self) -> Path:
        return self.root / FRP_DIR_NAME

    @property
    def db_path(self) -> Path:
        return self.frp_dir / DB_FILE_NAME

    @property
    def config_path(self) -> Path:
        return self.frp_dir / CONFIG_FILE_NAME

    @property
    def artifacts_dir(self) -> Path:
        return self.frp_dir / ARTIFACTS_DIR_NAME

    def artifacts_for(self, experiment_id: str) -> Path:
        return self.artifacts_dir / experiment_id

    def exists(self) -> bool:
        return self.frp_dir.is_dir()

    def ensure_dirs(self) -> None:
        self.frp_dir.mkdir(parents=True, exist_ok=True)
        self.artifacts_dir.mkdir(parents=True, exist_ok=True)


def find_project_root(start: Path | None = None) -> Path | None:
    """Walk upward from ``start`` (default: cwd) to locate a ``.frp/`` dir."""
    current = (start or Path.cwd()).resolve()
    for candidate in [current, *current.parents]:
        if (candidate / FRP_DIR_NAME).is_dir():
            return candidate
    return None


def resolve_project(start: Path | None = None) -> ProjectPaths:
    """Resolve the current project or raise :class:`ProjectNotFoundError`."""
    root = find_project_root(start)
    if root is None:
        raise ProjectNotFoundError(
            "No FRP project found. Run 'frpx init' in your research repository first."
        )
    return ProjectPaths(root)