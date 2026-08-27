"""End-to-end tests for the experiment service (capture -> persist -> query)."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from frp.capture.environment import capture_environment
from frp.capture.git import GitInfo
from frp.capture.parameters import ParameterInfo
from frp.execution.metrics import MetricInfo
from frp.execution.runner import ExecutionResult
from frp.experiments.service import (
    CaptureBundle,
    create_experiment,
    get_experiment,
    get_or_create_project,
    list_experiments,
)
from frp.store.paths import ProjectPaths


def _bundle(root: Path, artifact: Path, sharpe: float = 1.42) -> CaptureBundle:
    now = datetime.now(timezone.utc)
    return CaptureBundle(
        command=["python", "backtest.py"],
        git=GitInfo(
            commit_sha="8f31a2c9",
            branch="main",
            dirty=False,
            diff_hash=None,
            remote_url=None,
            is_repo=True,
        ),
        environment=capture_environment(),
        parameters=[ParameterInfo("lookback", "90", "int", "params.json")],
        execution=ExecutionResult(
            command=["python", "backtest.py"],
            exit_code=0,
            stdout="",
            stderr="",
            started_at=now,
            finished_at=now,
            duration_ms=10,
            new_files=[artifact],
        ),
        metrics=[MetricInfo("sharpe", sharpe, "metrics.json")],
        artifact_files=[artifact],
    )


def test_create_and_get_experiment(project: ProjectPaths, session_factory) -> None:
    artifact = project.root / "results.csv"
    artifact.write_text("a,b\n1,2\n")

    with session_factory() as session:
        proj = get_or_create_project(session, "demo", str(project.root))
        exp = create_experiment(session, project, proj, _bundle(project.root, artifact))
        session.commit()
        exp_id = exp.id

    with session_factory() as session:
        got = get_experiment(session, exp_id)
        assert got is not None
        assert got.command == "python backtest.py"
        assert got.git_commit.commit_sha == "8f31a2c9"
        assert got.environment is not None
        assert {p.key for p in got.parameters} == {"lookback"}
        assert {m.key for m in got.metrics} == {"sharpe"}
        assert {a.rel_path for a in got.artifacts} == {"results.csv"}
        assert got.content_hash


def test_rerun_creates_new_immutable_experiment(
    project: ProjectPaths, session_factory
) -> None:
    artifact = project.root / "results.csv"
    artifact.write_text("a,b\n1,2\n")

    with session_factory() as session:
        proj = get_or_create_project(session, "demo", str(project.root))
        first = create_experiment(session, project, proj, _bundle(project.root, artifact, 1.42))
        second = create_experiment(session, project, proj, _bundle(project.root, artifact, 1.42))
        session.commit()
        # New id each run; identical inputs => identical content_hash.
        assert first.id != second.id
        assert first.content_hash == second.content_hash


def test_content_hash_changes_with_metric(project: ProjectPaths, session_factory) -> None:
    artifact = project.root / "results.csv"
    artifact.write_text("a,b\n1,2\n")
    with session_factory() as session:
        proj = get_or_create_project(session, "demo", str(project.root))
        a = create_experiment(session, project, proj, _bundle(project.root, artifact, 1.42))
        b = create_experiment(session, project, proj, _bundle(project.root, artifact, 1.08))
        session.commit()
        assert a.content_hash != b.content_hash


def test_artifact_copied_into_store(project: ProjectPaths, session_factory) -> None:
    artifact = project.root / "results.csv"
    artifact.write_text("a,b\n1,2\n")
    with session_factory() as session:
        proj = get_or_create_project(session, "demo", str(project.root))
        exp = create_experiment(session, project, proj, _bundle(project.root, artifact))
        session.commit()
        copied = project.artifacts_for(exp.id) / "results.csv"
        assert copied.is_file()
        assert copied.read_text() == "a,b\n1,2\n"


def test_list_experiments(project: ProjectPaths, session_factory) -> None:
    artifact = project.root / "results.csv"
    artifact.write_text("x\n")
    with session_factory() as session:
        proj = get_or_create_project(session, "demo", str(project.root))
        create_experiment(session, project, proj, _bundle(project.root, artifact))
        create_experiment(session, project, proj, _bundle(project.root, artifact))
        session.commit()
        experiments = list_experiments(session, proj)
        assert len(experiments) == 2