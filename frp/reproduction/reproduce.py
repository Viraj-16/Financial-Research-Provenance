"""Reproduction orchestrator.

Re-runs an original experiment's command in the current project state,
re-fingerprinting the datasets it originally consumed, and produces a child
experiment plus a :class:`ReproductionReport`.

Honesty note: FRP re-runs the *recorded command* in the *current* environment.
It cannot resurrect a past Python/dependency state or past dataset bytes that
no longer exist on disk. The report therefore enumerates any known input
differences rather than claiming exact reproducibility.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from sqlalchemy.orm import Session

from frp.capture.environment import capture_environment
from frp.capture.git import capture_git
from frp.capture.parameters import capture_parameters
from frp.datasets.fingerprint import fingerprint_dataset
from frp.execution.metrics import detect_metrics
from frp.execution.runner import run_command
from frp.experiments.service import (
    CaptureBundle,
    create_experiment,
    get_experiment,
    get_or_create_project,
)
from frp.models import Experiment, Project
from frp.reproduction.compare import ReproductionReport, build_reproduction_report
from frp.store.paths import ProjectPaths


@dataclass
class ReproductionOutcome:
    original: Experiment
    reproduced: Experiment
    report: ReproductionReport


class ReproductionError(Exception):
    """Raised when an experiment cannot be reproduced (e.g. missing inputs)."""


def _original_input_paths(original: Experiment) -> list[tuple[str, str]]:
    """Return (name, canonical_path) for each input dataset of the original."""
    pairs: list[tuple[str, str]] = []
    for link in original.datasets:
        if link.role != "input":
            continue
        snap = link.snapshot
        if snap is not None and snap.dataset is not None:
            pairs.append((snap.dataset.name, snap.dataset.canonical_path))
    return pairs


def reproduce_experiment(
    session: Session,
    paths: ProjectPaths,
    project: Project,
    original: Experiment,
    tolerance: float,
    timeout: int | None = None,
) -> ReproductionOutcome:
    """Re-run ``original`` and compare, returning a child experiment + report."""
    command = original.command.split(" ")

    git = capture_git(paths.root)
    environment = capture_environment()
    parameters = capture_parameters(paths.root, None)

    # Re-fingerprint the datasets the original consumed (by canonical path).
    input_datasets = []
    for name, canonical_path in _original_input_paths(original):
        p = Path(canonical_path)
        if not p.is_file():
            raise ReproductionError(
                f"Input dataset '{name}' not found at {canonical_path}; cannot reproduce."
            )
        input_datasets.append(fingerprint_dataset(p, name=name))

    execution = run_command(command, cwd=paths.root, timeout=timeout)
    metrics = detect_metrics(paths.root, execution.stdout)

    input_resolved = {Path(d.path).resolve() for d in input_datasets}
    artifact_files = [f for f in execution.new_files if f.resolve() not in input_resolved]

    bundle = CaptureBundle(
        command=command,
        git=git,
        environment=environment,
        parameters=parameters,
        execution=execution,
        metrics=metrics,
        artifact_files=artifact_files,
        input_datasets=input_datasets,
    )

    reproduced = create_experiment(
        session, paths, project, bundle, parent_experiment_id=original.id
    )

    report = build_reproduction_report(original, reproduced, tolerance)
    return ReproductionOutcome(original=original, reproduced=reproduced, report=report)


def load_and_reproduce(
    session: Session,
    paths: ProjectPaths,
    project_name: str,
    experiment_id: str,
    tolerance: float,
    timeout: int | None = None,
) -> ReproductionOutcome:
    """Resolve an experiment id and reproduce it (raises if not found)."""
    original = get_experiment(session, experiment_id)
    if original is None:
        raise ReproductionError(f"Experiment not found: {experiment_id}")
    project = get_or_create_project(session, project_name, str(paths.root))
    return reproduce_experiment(session, paths, project, original, tolerance, timeout)