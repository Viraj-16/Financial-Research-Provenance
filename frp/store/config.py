"""Project configuration stored in ``.frp/config.toml``.

Kept intentionally minimal for the MVP. We read TOML with the stdlib
``tomllib`` (Python 3.11+) and fall back to a tiny parser for 3.10.
Writing is done with a small serializer to avoid adding a dependency.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

try:  # Python 3.11+
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - 3.10 fallback
    tomllib = None  # type: ignore[assignment]


@dataclass
class ProjectConfig:
    """Top-level FRP project configuration."""

    name: str
    frp_version: str = "0.1.0"
    metric_tolerance: float = 1e-9
    extra: dict[str, Any] = field(default_factory=dict)

    def to_toml(self) -> str:
        lines = [
            "[project]",
            f'name = "{_escape(self.name)}"',
            f'frp_version = "{_escape(self.frp_version)}"',
            "",
            "[reproduction]",
            f"metric_tolerance = {self.metric_tolerance}",
            "",
        ]
        return "\n".join(lines)


def _escape(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"')


def write_config(path: Path, config: ProjectConfig) -> None:
    path.write_text(config.to_toml(), encoding="utf-8")


def read_config(path: Path) -> ProjectConfig:
    text = path.read_text(encoding="utf-8")
    data: dict[str, Any]
    if tomllib is not None:
        data = tomllib.loads(text)
    else:  # pragma: no cover - minimal 3.10 fallback
        data = _minimal_toml_parse(text)
    project = data.get("project", {})
    reproduction = data.get("reproduction", {})
    return ProjectConfig(
        name=project.get("name", "unnamed"),
        frp_version=project.get("frp_version", "0.1.0"),
        metric_tolerance=float(reproduction.get("metric_tolerance", 1e-9)),
    )


def _minimal_toml_parse(text: str) -> dict[str, Any]:  # pragma: no cover
    """Very small TOML subset parser used only on Python 3.10."""
    result: dict[str, Any] = {}
    section: dict[str, Any] = result
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("[") and line.endswith("]"):
            name = line[1:-1].strip()
            section = result.setdefault(name, {})
            continue
        if "=" in line:
            key, _, value = line.partition("=")
            key = key.strip()
            value = value.strip()
            if value.startswith('"') and value.endswith('"'):
                section[key] = value[1:-1]
            else:
                try:
                    section[key] = float(value) if "." in value else int(value)
                except ValueError:
                    section[key] = value
    return result