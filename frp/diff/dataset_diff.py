"""Dataset-to-dataset diff.

Compares two dataset fingerprints and reports structural/statistical changes:
row-count delta, added/removed columns, dtype changes, and date-range shifts.
Deliberately bounded — this operates on fingerprint metadata, not full row-by-row
scans, so it stays fast on large datasets.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from frp.datasets.fingerprint import DatasetFingerprint


@dataclass
class DatasetDiff:
    name_a: str
    name_b: str
    identical: bool
    row_count_a: int | None = None
    row_count_b: int | None = None
    added_columns: list[str] = field(default_factory=list)
    removed_columns: list[str] = field(default_factory=list)
    dtype_changes: list[tuple[str, str, str]] = field(default_factory=list)  # (col, a, b)
    date_range_a: dict[str, str] | None = None
    date_range_b: dict[str, str] | None = None

    @property
    def row_count_delta(self) -> int | None:
        if self.row_count_a is None or self.row_count_b is None:
            return None
        return self.row_count_b - self.row_count_a

    @property
    def schema_changed(self) -> bool:
        return bool(self.added_columns or self.removed_columns or self.dtype_changes)


def diff_datasets(a: DatasetFingerprint, b: DatasetFingerprint) -> DatasetDiff:
    identical = a.sha256 == b.sha256

    cols_a = set(a.column_names)
    cols_b = set(b.column_names)
    added = sorted(cols_b - cols_a)
    removed = sorted(cols_a - cols_b)

    dtype_changes: list[tuple[str, str, str]] = []
    for col in sorted(cols_a & cols_b):
        ta = a.dtypes.get(col, "")
        tb = b.dtypes.get(col, "")
        if ta != tb:
            dtype_changes.append((col, ta, tb))

    return DatasetDiff(
        name_a=a.name,
        name_b=b.name,
        identical=identical,
        row_count_a=a.row_count,
        row_count_b=b.row_count,
        added_columns=added,
        removed_columns=removed,
        dtype_changes=dtype_changes,
        date_range_a=a.date_range,
        date_range_b=b.date_range,
    )


def dataset_diff_to_dict(diff: DatasetDiff) -> dict:
    return {
        "name_a": diff.name_a,
        "name_b": diff.name_b,
        "identical": diff.identical,
        "row_count_a": diff.row_count_a,
        "row_count_b": diff.row_count_b,
        "row_count_delta": diff.row_count_delta,
        "added_columns": diff.added_columns,
        "removed_columns": diff.removed_columns,
        "dtype_changes": [
            {"column": c, "a": ta, "b": tb} for c, ta, tb in diff.dtype_changes
        ],
        "date_range_a": diff.date_range_a,
        "date_range_b": diff.date_range_b,
        "schema_changed": diff.schema_changed,
    }