"""Metric detection.

Two deterministic sources are supported (no AI/heuristic extraction):

1. An explicit ``metrics.json`` file written by the research script. This is
   the authoritative source. Example::

       {"sharpe": 1.42, "cagr": 0.183, "max_drawdown": -0.121}

2. Optional structured stdout lines of the form ``FRP_METRIC key=value`` for
   scripts that prefer to print metrics. Only lines with this exact prefix are
   parsed, avoiding false positives.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path

_STDOUT_PATTERN = re.compile(r"^FRP_METRIC\s+([A-Za-z0-9_.:-]+)\s*=\s*(-?[0-9.eE+]+)\s*$")


@dataclass
class MetricInfo:
    key: str
    value: float
    source: str
    unit: str | None = None


def _coerce_float(value: object) -> float | None:
    try:
        return float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None


def read_metrics_file(path: Path) -> list[MetricInfo]:
    """Read metrics from a ``metrics.json`` file, if present."""
    if not path.is_file():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"metrics.json is not valid JSON: {exc}") from exc
    if not isinstance(data, dict):
        raise ValueError("metrics.json must contain a JSON object at the top level.")

    metrics: list[MetricInfo] = []
    for key, raw in data.items():
        num = _coerce_float(raw)
        if num is None:
            continue  # skip non-numeric metric entries deterministically
        metrics.append(MetricInfo(key=str(key), value=num, source="metrics.json"))
    metrics.sort(key=lambda m: m.key)
    return metrics


def parse_stdout_metrics(stdout: str) -> list[MetricInfo]:
    """Parse ``FRP_METRIC key=value`` lines from captured stdout."""
    metrics: list[MetricInfo] = []
    for line in stdout.splitlines():
        match = _STDOUT_PATTERN.match(line.strip())
        if not match:
            continue
        key, raw = match.group(1), match.group(2)
        num = _coerce_float(raw)
        if num is None:
            continue
        metrics.append(MetricInfo(key=key, value=num, source="stdout"))
    metrics.sort(key=lambda m: m.key)
    return metrics


def detect_metrics(project_root: Path, stdout: str) -> list[MetricInfo]:
    """Detect metrics, preferring ``metrics.json`` over stdout parsing.

    If a key appears in both sources, the ``metrics.json`` value wins.
    """
    file_metrics = read_metrics_file(project_root / "metrics.json")
    known = {m.key for m in file_metrics}
    stdout_metrics = [m for m in parse_stdout_metrics(stdout) if m.key not in known]
    combined = file_metrics + stdout_metrics
    combined.sort(key=lambda m: m.key)
    return combined