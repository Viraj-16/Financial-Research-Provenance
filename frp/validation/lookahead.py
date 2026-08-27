"""Look-ahead bias warning system.

This is a WARNING system, not a mathematical proof. It can only reason about
information FRP actually has: a declared ``backtest_date`` parameter and a
dataset's ``publication_date`` (from a ``.frpmeta.json`` sidecar). When a
dataset's publication date is AFTER the simulated decision date, we flag a
potential look-ahead: the data may not have been available at that time.

We never claim to detect all look-ahead bias.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from frp.datasets.fingerprint import DatasetFingerprint, _parse_dt


@dataclass
class LookAheadWarning:
    dataset: str
    backtest_date: str
    publication_date: str
    message: str


def parse_backtest_date(params: dict[str, str]) -> datetime | None:
    """Extract a backtest/decision date from parameters, if present."""
    for key in ("backtest_date", "decision_date", "as_of", "as_of_date"):
        if key in params:
            return _parse_dt(params[key])
    return None


def check_lookahead(
    backtest_date: datetime | None, datasets: list[DatasetFingerprint]
) -> list[LookAheadWarning]:
    """Flag datasets whose publication_date is after the backtest date."""
    if backtest_date is None:
        return []

    warnings: list[LookAheadWarning] = []
    for ds in datasets:
        pub = _parse_dt(ds.publication_date)
        if pub is None:
            continue
        if pub > backtest_date:
            warnings.append(
                LookAheadWarning(
                    dataset=ds.name,
                    backtest_date=backtest_date.date().isoformat(),
                    publication_date=pub.date().isoformat(),
                    message=(
                        "POTENTIAL LOOK-AHEAD BIAS — this information may not have "
                        "been available at the time of the simulated decision."
                    ),
                )
            )
    return warnings