"""Tests for metric detection."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from frp.execution.metrics import (
    detect_metrics,
    parse_stdout_metrics,
    read_metrics_file,
)


def test_read_metrics_file(tmp_path: Path) -> None:
    (tmp_path / "metrics.json").write_text(
        json.dumps({"sharpe": 1.42, "cagr": 0.183, "max_drawdown": -0.121})
    )
    metrics = read_metrics_file(tmp_path / "metrics.json")
    by_key = {m.key: m.value for m in metrics}
    assert by_key["sharpe"] == pytest.approx(1.42)
    assert by_key["cagr"] == pytest.approx(0.183)
    assert by_key["max_drawdown"] == pytest.approx(-0.121)
    assert all(m.source == "metrics.json" for m in metrics)


def test_read_metrics_file_missing(tmp_path: Path) -> None:
    assert read_metrics_file(tmp_path / "metrics.json") == []


def test_read_metrics_file_invalid_json(tmp_path: Path) -> None:
    (tmp_path / "metrics.json").write_text("{not json}")
    with pytest.raises(ValueError):
        read_metrics_file(tmp_path / "metrics.json")


def test_parse_stdout_metrics() -> None:
    out = "irrelevant line\nFRP_METRIC sharpe=1.42\nFRP_METRIC cagr = 0.18\nnope"
    metrics = parse_stdout_metrics(out)
    by_key = {m.key: m.value for m in metrics}
    assert by_key == {"sharpe": pytest.approx(1.42), "cagr": pytest.approx(0.18)}
    assert all(m.source == "stdout" for m in metrics)


def test_detect_prefers_file_over_stdout(tmp_path: Path) -> None:
    (tmp_path / "metrics.json").write_text(json.dumps({"sharpe": 1.42}))
    out = "FRP_METRIC sharpe=9.99\nFRP_METRIC cagr=0.18"
    metrics = detect_metrics(tmp_path, out)
    by_key = {m.key: (m.value, m.source) for m in metrics}
    assert by_key["sharpe"] == (pytest.approx(1.42), "metrics.json")
    assert by_key["cagr"] == (pytest.approx(0.18), "stdout")