"""Experiment service: create immutable experiments and query them.

This is the orchestration heart of Phase 1. Given captured inputs (git,
environment, parameters, execution result, metrics), it persists a single
immutable :class:`Experiment` aggregate and computes its ``content_hash``.
"""

from __future__ import annotations

import mimetypes
import shutil
from dataclasses import dataclass, field
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from frp.capture.environment import EnvironmentInfo
from frp.capture.git import GitInfo
from frp.capture.parameters import ParameterInfo
from frp.datasets.fingerprint import DatasetFingerprint
from frp.datasets.registry import register_snapshot
from frp.execution.metrics import MetricInfo
from frp.execution.runner import ExecutionResult
from frp.experiments.ids import new_experiment_id, validate_experiment_id
from frp.hashing import hash_file, hash_json
from frp.models import (
    Artifact,
    Dependency,
    Environment,
    Experiment,
    ExperimentDataset,
    GitCommit,
    LineageEdge,
    Metric,
    Parameter,
    Project,
)
from frp.store.paths import ProjectPaths


@dataclass
class CaptureBundle:
    """All captured inputs needed to create an experiment."""

    command: list[str]
    git: GitInfo
    environment: EnvironmentInfo
    parameters: list[ParameterInfo]
    execution: ExecutionResult
    metrics: list[MetricInfo]
    artifact_files: list[Path]
    input_datasets: list[DatasetFingerprint] = field(default_factory=list)


def get_or_create_project(session: Session, name: str, root_path: str) -> Project:
    existing = session.scalar(select(Project).where(Project.root_path == root_path))
    if existing is not None:
        return existing
    project = Project(name=name, root_path=root_path)
    session.add(project)
    session.flush()
    return project


def _safe_relative(root: Path, target: Path) -> Path:
    """Return ``target`` relative to ``root`` or raise if it escapes ``root``."""
    resolved = target.resolve()
    root_resolved = root.resolve()
    try:
        return resolved.relative_to(root_resolved)
    except ValueError as exc:
        raise ValueError(
            f"Refusing to record artifact outside project root: {target}"
        ) from exc


def _persist_environment(session: Session, env: EnvironmentInfo) -> Environment:
    row = Environment(
        python_version=env.python_version,
        platform=env.platform,
        os_name=env.os_name,
        hostname=env.hostname,
        hash=env.hash,
    )
    session.add(row)
    session.flush()
    for dep in env.dependencies:
        session.add(
            Dependency(
                environment_id=row.id,
                name=dep.name,
                version=dep.version,
                source=dep.source,
            )
        )
    return row


def _persist_git(session: Session, git: GitInfo) -> GitCommit | None:
    if not git.is_repo:
        return None
    row = GitCommit(
        commit_sha=git.commit_sha,
        branch=git.branch,
        dirty=git.dirty,
        diff_hash=git.diff_hash,
        remote_url=git.remote_url,
    )
    session.add(row)
    session.flush()
    return row


def _input_payload(bundle: CaptureBundle) -> dict:
    """The reproducible-inputs portion of an experiment (no outputs/metrics)."""
    return {
        "command": bundle.command,
        "git": {
            "commit_sha": bundle.git.commit_sha,
            "dirty": bundle.git.dirty,
            "diff_hash": bundle.git.diff_hash,
        },
        "environment_hash": bundle.environment.hash,
        "parameters": sorted([(p.key, p.value, p.type) for p in bundle.parameters]),
        "input_datasets": sorted(
            [(d.name, d.sha256) for d in bundle.input_datasets]
        ),
    }


def _compute_input_hash(bundle: CaptureBundle) -> str:
    """Hash covering ONLY reproducible inputs (code + data + params + env)."""
    return hash_json(_input_payload(bundle))


def _compute_content_hash(bundle: CaptureBundle, artifact_hashes: dict[str, str]) -> str:
    """Hash covering the FULL result state (inputs + outputs + metrics)."""
    payload = {
        "inputs": _input_payload(bundle),
        "metrics": sorted([(m.key, m.value) for m in bundle.metrics]),
        "artifacts": sorted(artifact_hashes.items()),
        "exit_code": bundle.execution.exit_code,
    }
    return hash_json(payload)


def _persist_input_datasets(
    session: Session, project: Project, exp_id: str, bundle: CaptureBundle
) -> None:
    """Fingerprint + link input datasets and record lineage edges."""
    for fp in bundle.input_datasets:
        snapshot = register_snapshot(session, project, fp)
        session.add(
            ExperimentDataset(
                experiment_id=exp_id,
                dataset_snapshot_id=snapshot.id,
                role="input",
            )
        )
        session.add(
            LineageEdge(
                experiment_id=exp_id,
                from_node=f"dataset:{fp.name}",
                to_node=f"experiment:{exp_id}",
                edge_type="consumes",
            )
        )


def create_experiment(
    session: Session,
    paths: ProjectPaths,
    project: Project,
    bundle: CaptureBundle,
    parent_experiment_id: str | None = None,
) -> Experiment:
    """Persist an immutable experiment aggregate and return it.

    ``parent_experiment_id`` links a reproduction run back to its original.
    """
    exp_id = new_experiment_id()

    git_row = _persist_git(session, bundle.git)
    env_row = _persist_environment(session, bundle.environment)

    # Copy artifacts into the immutable artifact store and hash them.
    artifact_dir = paths.artifacts_for(exp_id)
    artifact_dir.mkdir(parents=True, exist_ok=True)
    artifact_rows: list[Artifact] = []
    artifact_hashes: dict[str, str] = {}
    for src in bundle.artifact_files:
        rel = _safe_relative(paths.root, src)
        sha = hash_file(src)
        size = src.stat().st_size
        dest = artifact_dir / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dest)
        mime, _ = mimetypes.guess_type(str(src))
        artifact_rows.append(
            Artifact(
                experiment_id=exp_id,
                rel_path=str(rel).replace("\\", "/"),
                sha256=sha,
                size_bytes=size,
                mime=mime,
            )
        )
        artifact_hashes[str(rel).replace("\\", "/")] = sha

    content_hash = _compute_content_hash(bundle, artifact_hashes)
    input_hash = _compute_input_hash(bundle)

    experiment = Experiment(
        id=exp_id,
        project_id=project.id,
        status="completed" if bundle.execution.exit_code == 0 else "failed",
        git_commit_id=git_row.id if git_row else None,
        environment_id=env_row.id,
        command=" ".join(bundle.command),
        exit_code=bundle.execution.exit_code,
        started_at=bundle.execution.started_at,
        finished_at=bundle.execution.finished_at,
        duration_ms=bundle.execution.duration_ms,
        content_hash=content_hash,
        input_hash=input_hash,
        parent_experiment_id=parent_experiment_id,
    )
    session.add(experiment)
    session.flush()

    _persist_input_datasets(session, project, exp_id, bundle)

    for a in artifact_rows:
        session.add(
            LineageEdge(
                experiment_id=exp_id,
                from_node=f"experiment:{exp_id}",
                to_node=f"artifact:{a.rel_path}",
                edge_type="produces",
            )
        )

    for p in bundle.parameters:
        session.add(
            Parameter(
                experiment_id=exp_id,
                key=p.key,
                value=p.value,
                type=p.type,
                source=p.source,
            )
        )
    for m in bundle.metrics:
        session.add(
            Metric(
                experiment_id=exp_id,
                key=m.key,
                value=m.value,
                unit=m.unit,
                source=m.source,
            )
        )
    for a in artifact_rows:
        session.add(a)

    session.flush()
    return experiment


def get_experiment(session: Session, experiment_id: str) -> Experiment | None:
    validate_experiment_id(experiment_id)
    return session.get(Experiment, experiment_id)


def list_experiments(session: Session, project: Project) -> list[Experiment]:
    stmt = (
        select(Experiment)
        .where(Experiment.project_id == project.id)
        .order_by(Experiment.started_at.desc())
    )
    return list(session.scalars(stmt).all())