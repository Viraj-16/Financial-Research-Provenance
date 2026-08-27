"""Tests for experiment id generation and validation."""

from __future__ import annotations

import pytest

from frp.experiments.ids import (
    is_valid_experiment_id,
    new_experiment_id,
    validate_experiment_id,
)


def test_new_id_is_valid() -> None:
    for _ in range(20):
        assert is_valid_experiment_id(new_experiment_id())


def test_new_ids_are_unique() -> None:
    ids = {new_experiment_id() for _ in range(100)}
    assert len(ids) == 100


@pytest.mark.parametrize(
    "bad",
    [
        "exp_",
        "exp_xyz",
        "experiment_123456789012",
        "'; DROP TABLE experiment;--",
        "exp_ABCDEF123456",  # uppercase not allowed
        "../../etc/passwd",
        "",
    ],
)
def test_invalid_ids_rejected(bad: str) -> None:
    assert not is_valid_experiment_id(bad)
    with pytest.raises(ValueError):
        validate_experiment_id(bad)