"""Tests for data-quality checks and look-ahead warnings (Phase 5)."""

from __future__ import annotations

from datetime import date, datetime
from pathlib import Path

import polars as pl

from frp.datasets.fingerprint import DatasetFingerprint
from frp.validation.lookahead import check_lookahead, parse_backtest_date
from frp.validation.quality import validate_dataframe, validate_file


def _results_by_name(results: list) -> dict:
    return {r.check_name: r for r in results}


def test_clean_financial_data_passes() -> None:
    frame = pl.DataFrame(
        {
            "ticker": ["AAA", "BBB"],
            "date": [date(2023, 1, 1), date(2023, 1, 2)],
            "close": [10.0, 20.0],
            "volume": [100, 200],
        }
    )
    results = validate_dataframe(frame)
    assert all(r.passed for r in results if r.severity in {"info"})
    assert not any(r.severity == "error" and not r.passed for r in results)


def test_negative_price_flagged() -> None:
    frame = pl.DataFrame({"close": [10.0, -5.0, 20.0]})
    results = _results_by_name(validate_dataframe(frame))
    check = results["price_positive[close]"]
    assert check.passed is False
    assert check.severity == "error"


def test_negative_volume_flagged() -> None:
    frame = pl.DataFrame({"volume": [100, -1, 50]})
    results = _results_by_name(validate_dataframe(frame))
    check = results["volume_non_negative[volume]"]
    assert check.passed is False


def test_null_ticker_flagged() -> None:
    frame = pl.DataFrame({"ticker": ["AAA", None, "CCC"]})
    results = _results_by_name(validate_dataframe(frame))
    assert results["ticker_not_null[ticker]"].passed is False


def test_missing_values_and_duplicates() -> None:
    frame = pl.DataFrame({"x": [1, 1, None]})
    results = _results_by_name(validate_dataframe(frame))
    assert results["missing_values[x]"].passed is False
    assert results["duplicate_rows"].passed is False


def test_validate_file_unsupported(tmp_path: Path) -> None:
    p = tmp_path / "note.txt"
    p.write_text("hello")
    try:
        validate_file(p)
        raise AssertionError("expected ValueError")
    except ValueError:
        pass


# --- Point-in-time / look-ahead ---------------------------------------------


def _fp(name: str, publication_date: str | None) -> DatasetFingerprint:
    return DatasetFingerprint(
        name=name,
        path=f"/tmp/{name}",
        sha256="0" * 64,
        size_bytes=1,
        publication_date=publication_date,
    )


def test_lookahead_publication_before_decision_ok() -> None:
    backtest = datetime(2023, 3, 31)
    datasets = [_fp("fundamentals", "2023-02-15")]  # published before decision
    assert check_lookahead(backtest, datasets) == []


def test_lookahead_publication_after_decision_warns() -> None:
    backtest = datetime(2023, 3, 31)
    datasets = [_fp("fundamentals", "2023-05-04")]  # published AFTER decision
    warnings = check_lookahead(backtest, datasets)
    assert len(warnings) == 1
    w = warnings[0]
    assert w.dataset == "fundamentals"
    assert w.backtest_date == "2023-03-31"
    assert w.publication_date == "2023-05-04"
    assert "LOOK-AHEAD" in w.message


def test_lookahead_no_backtest_date_no_warning() -> None:
    datasets = [_fp("fundamentals", "2023-05-04")]
    assert check_lookahead(None, datasets) == []


def test_lookahead_no_publication_date_skipped() -> None:
    backtest = datetime(2023, 3, 31)
    datasets = [_fp("prices", None)]
    assert check_lookahead(backtest, datasets) == []


def test_parse_backtest_date_from_params() -> None:
    assert parse_backtest_date({"backtest_date": "2023-03-31"}) == datetime(2023, 3, 31)
    assert parse_backtest_date({"as_of": "2023-03-31"}) == datetime(2023, 3, 31)
    assert parse_backtest_date({"lookback": "90"}) is None