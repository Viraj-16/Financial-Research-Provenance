"""Tests for reproduction (Phase 3)."""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from frp.capture.environment import capture_environment
from frp.capture.git import GitInfo
from frp.capture.parameters import ParameterInfo
from frp.datasets.fingerprint import fingerprint_dataset
from frp.execution.metrics import MetricInfo
from frp.execution.runner import ExecutionResult
from frp.experiments.service import (
    CaptureBundle,
    create_experiment,
    get_or_create_project,
)
from frp.reproduction.compare import build_reproduction_report
from frp.reproduction.reproduce import reproduce_experiment
from frp.store.paths import ProjectPaths

DETERMINISTIC_SCRIPT = """
import json, sys
lookback = 90
for a in sys.argv[1:]:
    if a.startswith("lookback="):
        lookback = int(a.split("=")[1])
# deterministic "metric" derived from the parameter
json.dump({"sharpe": round(lookback / 100.0, 4)}, open("metrics.json", "w"))
print("done")
"""


def _write_script(root: Path) -> Path:
    script = root / "backtest.py"
    script.write_text(DETERMINISTIC_SCRIPT)
    # The original experiment's parameters must be reproducible from the project
    # state, so persist them where capture_parameters() will read them.
    (root / "params.json").write_text(json.dumps({"lookback": 90}))
    return script


def _git() -> GitInfo:
    # tmp_path projects are not git repos; match what capture_git() returns
    # during reproduction so the "code" input compares equal.
    return GitInfo(None, None, False, None, None, is_repo=False)


def _bundle(command: list[str], sharpe: float) -> CaptureBundle:
    now = datetime.now(timezone.utc)
    return CaptureBundle(
        command=command,
        git=_git(),
        environment=capture_environment(),
        parameters=[ParameterInfo("lookback", "90", "int", "params.json")],
        execution=ExecutionResult(command, 0, "", "", now, now, 5, []),
        metrics=[MetricInfo("sharpe", sharpe, "metrics.json")],
        artifact_files=[],
    )


def test_reproducible_experiment(project: ProjectPaths, session_factory) -> None:
    _write_script(project.root)
    command = [sys.executable, "backtest.py", "lookback=90"]
    with session_factory() as session:
        proj = get_or_create_project(session, "demo", str(project.root))
        original = create_experiment(session, project, proj, _bundle(command, 0.9))
        session.commit()
        outcome = reproduce_experiment(session, project, proj, original, tolerance=1e-9)
        session.commit()
        assert outcome.report.reproduced is True
        assert outcome.report.inputs_match is True
        assert outcome.reproduced.parent_experiment_id == original.id


def test_reproduction_metric_difference(project: ProjectPaths, session_factory) -> None:
    _write_script(project.root)
    command = [sys.executable, "backtest.py", "lookback=90"]
    with session_factory() as session:
        proj = get_or_create_project(session, "demo", str(project.root))
        # Original recorded a stale metric that the script won't reproduce.
        original = create_experiment(session, project, proj, _bundle(command, 1.42))
        session.commit()
        outcome = reproduce_experiment(session, project, proj, original, tolerance=1e-9)
        session.commit()
        assert outcome.report.reproduced is False
        assert outcome.report.metrics_match is False
        delta = {d.key: d for d in outcome.report.metric_deltas}["sharpe"]
        assert delta.original == 1.42
        assert delta.reproduced == 0.9  # lookback 90 / 100


def test_compare_changed_parameter(project: ProjectPaths, session_factory) -> None:
    command = [sys.executable, "backtest.py"]
    with session_factory() as session:
        proj = get_or_create_project(session, "demo", str(project.root))
        a = create_experiment(session, project, proj, _bundle(command, 0.9))
        b_bundle = _bundle(command, 1.2)
        b_bundle.parameters = [ParameterInfo("lookback", "120", "int", "params.json")]
        b = create_experiment(session, project, proj, b_bundle)
        session.commit()
        report = build_reproduction_report(a, b, tolerance=1e-9)
        cats = {d.category for d in report.input_differences}
        assert "parameters" in cats
        assert report.inputs_match is False


def test_compare_changed_dataset(project: ProjectPaths, session_factory) -> None:
    # Two different dataset contents under the same logical name.
    p1 = project.root / "prices.csv"
    p1.write_text("a,b\n1,2\n")
    fp1 = fingerprint_dataset(p1, name="prices")
    command = [sys.executable, "backtest.py"]
    with session_factory() as session:
        proj = get_or_create_project(session, "demo", str(project.root))
        ba = _bundle(command, 0.9)
        ba.input_datasets = [fp1]
        a = create_experiment(session, project, proj, ba)

        p1.write_text("a,b\n1,2\n3,4\n")  # changed content
        fp2 = fingerprint_dataset(p1, name="prices")
        bb = _bundle(command, 0.9)
        bb.input_datasets = [fp2]
        b = create_experiment(session, project, proj, bb)
        session.commit()

        report = build_reproduction_report(a, b, tolerance=1e-9)
        cats = {d.category for d in report.input_differences}
        assert "data" in cats