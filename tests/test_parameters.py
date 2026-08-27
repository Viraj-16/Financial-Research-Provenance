"""Tests for parameter capture."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from frp.capture.parameters import capture_parameters


def test_capture_from_params_file(tmp_path: Path) -> None:
    (tmp_path / "params.json").write_text(
        json.dumps({"lookback": 90, "rebalance": "monthly", "use_costs": True})
    )
    params = capture_parameters(tmp_path)
    by_key = {p.key: p for p in params}
    assert by_key["lookback"].value == "90"
    assert by_key["lookback"].type == "int"
    assert by_key["rebalance"].value == "monthly"
    assert by_key["use_costs"].type == "bool"
    assert all(p.source == "params.json" for p in params)


def test_cli_override_takes_precedence(tmp_path: Path) -> None:
    (tmp_path / "params.json").write_text(json.dumps({"lookback": 90}))
    params = capture_parameters(tmp_path, ["lookback=120"])
    by_key = {p.key: p for p in params}
    assert by_key["lookback"].value == "120"
    assert by_key["lookback"].source == "cli"


def test_invalid_cli_param(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        capture_parameters(tmp_path, ["novalue"])


def test_invalid_params_json(tmp_path: Path) -> None:
    (tmp_path / "params.json").write_text("[1,2,3]")
    with pytest.raises(ValueError):
        capture_parameters(tmp_path)


def test_no_params(tmp_path: Path) -> None:
    assert capture_parameters(tmp_path) == []