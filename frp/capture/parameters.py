"""Parameter capture.

Parameters are captured deterministically from, in order of precedence:

1. ``--param key=value`` flags passed on the CLI (source: ``cli``).
2. A ``params.json`` file in the project root (source: ``params.json``).

Values are stored as strings with a recorded ``type`` so they can be rendered
and diffed faithfully.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass
class ParameterInfo:
    key: str
    value: str
    type: str
    source: str


def _typename(value: Any) -> str:
    if isinstance(value, bool):
        return "bool"
    if isinstance(value, int):
        return "int"
    if isinstance(value, float):
        return "float"
    if isinstance(value, (list, dict)):
        return "json"
    return "str"


def _stringify(value: Any) -> str:
    if isinstance(value, (list, dict)):
        return json.dumps(value, sort_keys=True, separators=(",", ":"))
    return str(value)


def _coerce_cli_value(raw: str) -> Any:
    """Best-effort coercion of ``key=value`` CLI strings to typed values."""
    lowered = raw.lower()
    if lowered in {"true", "false"}:
        return lowered == "true"
    try:
        return int(raw)
    except ValueError:
        pass
    try:
        return float(raw)
    except ValueError:
        pass
    return raw


def capture_parameters(
    project_root: Path, cli_params: list[str] | None = None
) -> list[ParameterInfo]:
    """Capture parameters from ``params.json`` and CLI overrides."""
    merged: dict[str, tuple[Any, str]] = {}

    params_file = project_root / "params.json"
    if params_file.is_file():
        try:
            data = json.loads(params_file.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise ValueError(f"params.json is not valid JSON: {exc}") from exc
        if not isinstance(data, dict):
            raise ValueError("params.json must contain a JSON object at the top level.")
        for key, value in data.items():
            merged[str(key)] = (value, "params.json")

    for item in cli_params or []:
        if "=" not in item:
            raise ValueError(f"Invalid --param '{item}'. Expected key=value.")
        key, _, raw = item.partition("=")
        merged[key.strip()] = (_coerce_cli_value(raw), "cli")

    result = [
        ParameterInfo(
            key=key,
            value=_stringify(value),
            type=_typename(value),
            source=source,
        )
        for key, (value, source) in sorted(merged.items())
    ]
    return result