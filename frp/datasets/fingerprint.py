"""Dataset fingerprinting.

Computes DATA IDENTITY: a SHA-256 over the raw bytes plus tabular metadata
(schema, row count, column names, dtypes, and a detected date range) for
supported formats. This is deliberately separate from DATA STORAGE — we never
require copying the bytes to compute identity.

Supported tabular formats for metadata extraction: ``.parquet``, ``.csv``,
``.arrow``/``.ipc``. Any other file is fingerprinted by hash + size only.

A sidecar ``<file>.frpmeta.json`` may declare point-in-time fields; these are
read verbatim and never fabricated:

    {"source": "vendor", "publication_date": "2023-05-04", ...}
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

import polars as pl

from frp.hashing import hash_file

_TABULAR_SUFFIXES = {".parquet", ".csv", ".arrow", ".ipc", ".feather"}
_PIT_FIELDS = ("source", "publication_date", "effective_date", "revision_ts")


@dataclass
class DatasetFingerprint:
    name: str
    path: str
    sha256: str
    size_bytes: int
    row_count: int | None = None
    column_names: list[str] = field(default_factory=list)
    dtypes: dict[str, str] = field(default_factory=dict)
    date_range: dict[str, str] | None = None
    # Point-in-time metadata (only when a sidecar provides it):
    source: str | None = None
    publication_date: str | None = None
    effective_date: str | None = None
    revision_ts: str | None = None

    def schema_json(self) -> str:
        return json.dumps(self.dtypes, sort_keys=True, separators=(",", ":"))


def _read_frame(path: Path) -> pl.DataFrame | None:
    """Read a supported tabular file into a Polars frame, or None if unsupported."""
    suffix = path.suffix.lower()
    try:
        if suffix == ".parquet":
            return pl.read_parquet(path)
        if suffix == ".csv":
            return pl.read_csv(path)
        if suffix in {".arrow", ".ipc", ".feather"}:
            return pl.read_ipc(path)
    except Exception:  # noqa: BLE001 - unreadable/corrupt tabular file: metadata skipped
        return None
    return None


def _detect_date_range(frame: pl.DataFrame) -> dict[str, str] | None:
    """Return {column, min, max} for the first temporal column, if any."""
    for name, dtype in zip(frame.columns, frame.dtypes, strict=False):
        if dtype in (pl.Date, pl.Datetime):
            col = frame.get_column(name).drop_nulls()
            if col.len() == 0:
                continue
            return {
                "column": name,
                "min": str(col.min()),
                "max": str(col.max()),
            }
    return None


def _read_sidecar(path: Path) -> dict[str, Any]:
    sidecar = path.with_name(path.name + ".frpmeta.json")
    if not sidecar.is_file():
        return {}
    try:
        data = json.loads(sidecar.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"{sidecar.name} is not valid JSON: {exc}") from exc
    if not isinstance(data, dict):
        raise ValueError(f"{sidecar.name} must contain a JSON object.")
    return data


def fingerprint_dataset(path: Path, name: str | None = None) -> DatasetFingerprint:
    """Fingerprint a dataset file (identity + metadata; never copies bytes)."""
    if not path.is_file():
        raise FileNotFoundError(f"Dataset not found: {path}")

    fp = DatasetFingerprint(
        name=name or path.name,
        path=str(path),
        sha256=hash_file(path),
        size_bytes=path.stat().st_size,
    )

    if path.suffix.lower() in _TABULAR_SUFFIXES:
        frame = _read_frame(path)
        if frame is not None:
            fp.row_count = frame.height
            fp.column_names = list(frame.columns)
            fp.dtypes = {c: str(t) for c, t in zip(frame.columns, frame.dtypes, strict=False)}
            fp.date_range = _detect_date_range(frame)

    sidecar = _read_sidecar(path)
    for key in _PIT_FIELDS:
        if key in sidecar and sidecar[key] is not None:
            setattr(fp, key, str(sidecar[key]))

    return fp


def _parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.strptime(value, fmt)
        except ValueError:
            continue
    return None