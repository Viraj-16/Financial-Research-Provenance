"""Tests for experiment and dataset diff (Phase 4)."""

from __future__ import annotations

from datetime import date, datetime, timezone
from pathlib import Path

import polars as pl

from frp.capture.environment import EnvironmentInfo, capture_environment
from frp.capture.git import GitInfo
from frp.capture.parameters import ParameterInfo
from frp.datasets.fingerprint import fingerprint_dataset
from frp.diff.dataset_diff import diff_datasets
from frp.diff.experiment_diff import diff_experiments
from frp.execution.metrics import MetricInfo
from frp.execution.runner import ExecutionResult
from frp.experiments.service import (
    CaptureBundle,
    create_experiment,
    get_or_create_project,
)
from frp.store.paths import ProjectPaths


def _bundle(
    *,
    sharpe: float = 1.0,
    lookback: str = "90",
    commit: str | None = "abc123",
    env: EnvironmentInfo | None = None,
) -> CaptureBundle:
    now = datetime.now(timezone.utc)
    return CaptureBundle(
        command=["python", "backtest.py"],
        git=GitInfo(commit, "main", False, None, None, is_repo=commit is not None),
        environment=env or capture_environment(),
        parameters=[ParameterInfo("lookback", lookback, "int", "params.json")],
        execution=ExecutionResult(["python", "backtest.py"], 0, "", "", now, now, 5, []),
        metrics=[MetricInfo("sharpe", sharpe, "metrics.json")],
        artifact_files=[],
    )


def test_diff_same_experiment(project: ProjectPaths, session_factory) -> None:
    with session_factory() as session:
        proj = get_or_create_project(session, "demo", str(project.root))
        a = create_experiment(session, project, proj, _bundle())
        session.commit()
        d = diff_experiments(a, a)
        assert d.any_change is False


def test_diff_changed_parameter(project: ProjectPaths, session_factory) -> None:
    with session_factory() as session:
        proj = get_or_create_project(session, "demo", str(project.root))
        a = create_experiment(session, project, proj, _bundle(lookback="90"))
        b = create_experiment(session, project, proj, _bundle(lookback="120"))
        session.commit()
        d = diff_experiments(a, b)
        changed = {c.key: c for c in d.parameters if c.changed}
        assert "lookback" in changed
        assert changed["lookback"].a == "90"
        assert changed["lookback"].b == "120"
        assert d.any_change is True


def test_diff_changed_code(project: ProjectPaths, session_factory) -> None:
    with session_factory() as session:
        proj = get_or_create_project(session, "demo", str(project.root))
        a = create_experiment(session, project, proj, _bundle(commit="aaa"))
        b = create_experiment(session, project, proj, _bundle(commit="bbb"))
        session.commit()
        d = diff_experiments(a, b)
        assert any(c.changed for c in d.code)


def test_diff_changed_metrics(project: ProjectPaths, session_factory) -> None:
    with session_factory() as session:
        proj = get_or_create_project(session, "demo", str(project.root))
        a = create_experiment(session, project, proj, _bundle(sharpe=1.42))
        b = create_experiment(session, project, proj, _bundle(sharpe=1.08))
        session.commit()
        d = diff_experiments(a, b)
        m = {x.key: x for x in d.metrics}["sharpe"]
        assert m.a == 1.42
        assert m.b == 1.08
        assert m.changed is True


def test_diff_changed_environment(project: ProjectPaths, session_factory) -> None:
    env_a = capture_environment()
    env_b = EnvironmentInfo(
        python_version="3.99.0",
        platform=env_a.platform,
        os_name=env_a.os_name,
        hostname=env_a.hostname,
        dependencies=[],
    )
    env_b.hash = env_b.compute_hash()
    with session_factory() as session:
        proj = get_or_create_project(session, "demo", str(project.root))
        a = create_experiment(session, project, proj, _bundle(env=env_a))
        b = create_experiment(session, project, proj, _bundle(env=env_b))
        session.commit()
        d = diff_experiments(a, b)
        py = {c.key: c for c in d.environment}["python"]
        assert py.changed is True


def _parquet(path: Path, rows: int, extra_col: bool = False) -> None:
    data = {
        "ticker": ["AAA", "BBB", "CCC"][:rows],
        "date": [date(2023, 1, 1), date(2023, 1, 2), date(2023, 1, 3)][:rows],
        "close": [10.0, 20.0, 30.0][:rows],
    }
    if extra_col:
        data["volume"] = [100, 200, 300][:rows]
    pl.DataFrame(data).write_parquet(path)


def test_dataset_diff_identical(tmp_path: Path) -> None:
    a = tmp_path / "a.parquet"
    b = tmp_path / "b.parquet"
    _parquet(a, 3)
    _parquet(b, 3)
    d = diff_datasets(fingerprint_dataset(a), fingerprint_dataset(b))
    assert d.identical is True


def test_dataset_diff_row_and_schema(tmp_path: Path) -> None:
    a = tmp_path / "a.parquet"
    b = tmp_path / "b.parquet"
    _parquet(a, 2)
    _parquet(b, 3, extra_col=True)
    d = diff_datasets(fingerprint_dataset(a), fingerprint_dataset(b))
    assert d.identical is False
    assert d.row_count_delta == 1
    assert "volume" in d.added_columns
    assert d.schema_changed is True