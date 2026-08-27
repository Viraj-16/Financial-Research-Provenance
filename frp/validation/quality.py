"""Data-quality checks for datasets.

Deterministic checks over a Polars frame. Generic checks (missing values,
duplicate rows, non-finite numerics) always run. Financial checks
(price > 0, volume >= 0, ticker/date not null) run only when the relevant
columns are present. Each check yields a :class:`CheckResult`.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path

import polars as pl

_PRICE_COLUMNS = {"open", "high", "low", "close", "price", "adj_close", "adjclose"}
_VOLUME_COLUMNS = {"volume", "vol"}
_TICKER_COLUMNS = {"ticker", "symbol"}
_DATE_COLUMNS = {"date", "datetime", "timestamp"}


@dataclass
class CheckResult:
    check_name: str
    severity: str  # info | warning | error
    passed: bool
    detail: str


def _match(columns: list[str], candidates: set[str]) -> list[str]:
    lower = {c.lower(): c for c in columns}
    return [lower[c] for c in candidates if c in lower]


def check_missing_values(frame: pl.DataFrame) -> list[CheckResult]:
    results: list[CheckResult] = []
    for col in frame.columns:
        nulls = int(frame.get_column(col).null_count())
        if nulls > 0:
            results.append(
                CheckResult(
                    f"missing_values[{col}]",
                    "warning",
                    False,
                    f"{nulls} null value(s) in column '{col}'",
                )
            )
    if not results:
        results.append(CheckResult("missing_values", "info", True, "no missing values"))
    return results


def check_duplicate_rows(frame: pl.DataFrame) -> CheckResult:
    dupes = frame.height - frame.unique().height
    if dupes > 0:
        return CheckResult("duplicate_rows", "warning", False, f"{dupes} duplicate row(s)")
    return CheckResult("duplicate_rows", "info", True, "no duplicate rows")


_NUMERIC_DTYPES = frozenset(
    {
        pl.Int8, pl.Int16, pl.Int32, pl.Int64,
        pl.UInt8, pl.UInt16, pl.UInt32, pl.UInt64,
        pl.Float32, pl.Float64,
    }
)


def check_finite_numerics(frame: pl.DataFrame) -> list[CheckResult]:
    results: list[CheckResult] = []
    for col, dtype in zip(frame.columns, frame.dtypes, strict=False):
        if dtype not in _NUMERIC_DTYPES:
            continue
        series = frame.get_column(col)
        bad = 0
        for v in series.to_list():
            if v is not None and isinstance(v, float) and (math.isnan(v) or math.isinf(v)):
                bad += 1
        if bad > 0:
            results.append(
                CheckResult(
                    f"invalid_numeric[{col}]",
                    "error",
                    False,
                    f"{bad} NaN/inf value(s) in numeric column '{col}'",
                )
            )
    if not results:
        results.append(CheckResult("invalid_numeric", "info", True, "no NaN/inf values"))
    return results


def check_financial(frame: pl.DataFrame) -> list[CheckResult]:
    results: list[CheckResult] = []
    cols = frame.columns

    for pc in _match(cols, _PRICE_COLUMNS):
        series = frame.get_column(pc).drop_nulls()
        non_positive = int((series <= 0).sum()) if series.len() else 0
        results.append(
            CheckResult(
                f"price_positive[{pc}]",
                "error" if non_positive else "info",
                non_positive == 0,
                f"{non_positive} non-positive price(s) in '{pc}'"
                if non_positive
                else f"all prices in '{pc}' are positive",
            )
        )

    for vc in _match(cols, _VOLUME_COLUMNS):
        series = frame.get_column(vc).drop_nulls()
        negative = int((series < 0).sum()) if series.len() else 0
        results.append(
            CheckResult(
                f"volume_non_negative[{vc}]",
                "error" if negative else "info",
                negative == 0,
                f"{negative} negative volume(s) in '{vc}'"
                if negative
                else f"all volumes in '{vc}' are non-negative",
            )
        )

    for tc in _match(cols, _TICKER_COLUMNS):
        nulls = int(frame.get_column(tc).null_count())
        results.append(
            CheckResult(
                f"ticker_not_null[{tc}]",
                "error" if nulls else "info",
                nulls == 0,
                f"{nulls} null ticker(s) in '{tc}'" if nulls else f"'{tc}' has no nulls",
            )
        )

    for dc in _match(cols, _DATE_COLUMNS):
        nulls = int(frame.get_column(dc).null_count())
        results.append(
            CheckResult(
                f"date_not_null[{dc}]",
                "error" if nulls else "info",
                nulls == 0,
                f"{nulls} null date(s) in '{dc}'" if nulls else f"'{dc}' has no nulls",
            )
        )

    return results


def validate_dataframe(frame: pl.DataFrame) -> list[CheckResult]:
    results: list[CheckResult] = []
    results.extend(check_missing_values(frame))
    results.append(check_duplicate_rows(frame))
    results.extend(check_finite_numerics(frame))
    results.extend(check_financial(frame))
    return results


def validate_file(path: Path) -> list[CheckResult]:
    """Validate a tabular file. Raises if the file cannot be read as tabular."""
    suffix = path.suffix.lower()
    if suffix == ".parquet":
        frame = pl.read_parquet(path)
    elif suffix == ".csv":
        frame = pl.read_csv(path)
    elif suffix in {".arrow", ".ipc", ".feather"}:
        frame = pl.read_ipc(path)
    else:
        raise ValueError(f"Unsupported file type for validation: {suffix or '(none)'}")
    return validate_dataframe(frame)