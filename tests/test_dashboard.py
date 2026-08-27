"""Tests for the read-only dashboard (Phase 6)."""

from __future__ import annotations

import json
from datetime import datetime, timezone

from frp.capture.environment import capture_environment
from frp.capture.git import GitInfo
from frp.capture.parameters import ParameterInfo
from frp.dashboard.data import build_dashboard_data
from frp.dashboard.server import render_dashboard_html
from frp.execution.metrics import MetricInfo
from frp.execution.runner import ExecutionResult
from frp.experiments.service import (
    CaptureBundle,
    create_experiment,
    get_or_create_project,
)
from frp.store.paths import ProjectPaths


def _bundle() -> CaptureBundle:
    now = datetime.now(timezone.utc)
    return CaptureBundle(
        command=["python", "backtest.py"],
        git=GitInfo("abc123", "main", False, None, None, is_repo=True),
        environment=capture_environment(),
        parameters=[ParameterInfo("lookback", "90", "int", "params.json")],
        execution=ExecutionResult(["python", "backtest.py"], 0, "", "", now, now, 5, []),
        metrics=[MetricInfo("sharpe", 1.42, "metrics.json")],
        artifact_files=[],
    )


def test_dashboard_data_empty(project: ProjectPaths, session_factory) -> None:
    with session_factory() as session:
        proj = get_or_create_project(session, "demo", str(project.root))
        data = build_dashboard_data(session, proj)
        assert data["project"]["name"] == "demo"
        assert data["project"]["experiment_count"] == 0
        assert data["experiments"] == []


def test_dashboard_data_with_experiment(project: ProjectPaths, session_factory) -> None:
    with session_factory() as session:
        proj = get_or_create_project(session, "demo", str(project.root))
        exp = create_experiment(session, project, proj, _bundle())
        session.commit()
        data = build_dashboard_data(session, proj)
        assert data["project"]["experiment_count"] == 1
        assert data["project"]["latest_experiment"] == exp.id
        e = data["experiments"][0]
        assert e["id"] == exp.id
        assert e["metrics"]["sharpe"] == 1.42
        assert e["git_commit"] == "abc123"
        assert e["environment"]["python"]


def test_dashboard_html_is_self_contained(project: ProjectPaths, session_factory) -> None:
    with session_factory() as session:
        proj = get_or_create_project(session, "demo", str(project.root))
        create_experiment(session, project, proj, _bundle())
        session.commit()
        data = build_dashboard_data(session, proj)

    html = render_dashboard_html(data)
    assert "<!DOCTYPE html>" in html
    assert "Financial Research Provenance" in html
    # Data is embedded as JSON and must be parseable.
    start = html.index('<script id="frp-data" type="application/json">') + len(
        '<script id="frp-data" type="application/json">'
    )
    end = html.index("</script>", start)
    embedded = json.loads(html[start:end])
    assert embedded["project"]["name"] == "demo"
    assert len(embedded["experiments"]) == 1