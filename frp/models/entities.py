"""ORM entity definitions for the FRP provenance model.

Immutability model
-------------------
Provenance rows are written once by the experiment service and never updated.
Each experiment carries a ``content_hash`` computed over its full aggregate and
a ``frozen_at`` timestamp. Re-running research produces a *new* experiment id;
existing rows are never mutated.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from frp.models.base import Base, utcnow


class Project(Base):
    __tablename__ = "project"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    root_path: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    experiments: Mapped[list[Experiment]] = relationship(back_populates="project")
    datasets: Mapped[list[Dataset]] = relationship(back_populates="project")


class GitCommit(Base):
    __tablename__ = "git_commit"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    commit_sha: Mapped[str | None] = mapped_column(String(64), nullable=True)
    branch: Mapped[str | None] = mapped_column(String(255), nullable=True)
    dirty: Mapped[bool] = mapped_column(Boolean, default=False)
    diff_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    remote_url: Mapped[str | None] = mapped_column(Text, nullable=True)


class Environment(Base):
    __tablename__ = "environment"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    python_version: Mapped[str] = mapped_column(String(32), nullable=False)
    platform: Mapped[str] = mapped_column(String(255), nullable=False)
    os_name: Mapped[str] = mapped_column(String(64), nullable=False)
    hostname: Mapped[str] = mapped_column(String(255), nullable=False)
    hash: Mapped[str] = mapped_column(String(64), nullable=False)

    dependencies: Mapped[list[Dependency]] = relationship(
        back_populates="environment", cascade="all, delete-orphan"
    )


class Dependency(Base):
    __tablename__ = "dependency"
    __table_args__ = (
        UniqueConstraint("environment_id", "name", "version", name="uq_dependency"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    environment_id: Mapped[int] = mapped_column(ForeignKey("environment.id"), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    version: Mapped[str] = mapped_column(String(128), nullable=False)
    source: Mapped[str] = mapped_column(String(64), default="pip-freeze")

    environment: Mapped[Environment] = relationship(back_populates="dependencies")


class Dataset(Base):
    """A logical dataset (by canonical path). Content lives in snapshots."""

    __tablename__ = "dataset"
    __table_args__ = (
        UniqueConstraint("project_id", "canonical_path", name="uq_dataset_path"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("project.id"), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    canonical_path: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    project: Mapped[Project] = relationship(back_populates="datasets")
    snapshots: Mapped[list[DatasetSnapshot]] = relationship(back_populates="dataset")


class DatasetSnapshot(Base):
    """Immutable fingerprint of a dataset's content at a point in time."""

    __tablename__ = "dataset_snapshot"
    __table_args__ = (
        UniqueConstraint("dataset_id", "sha256", name="uq_snapshot_hash"),
        Index("ix_snapshot_sha", "sha256"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    dataset_id: Mapped[int] = mapped_column(ForeignKey("dataset.id"), nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    row_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    schema_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    column_names_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    dtypes_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    date_range_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    # Point-in-time foundation (populated only when data actually provides it):
    source: Mapped[str | None] = mapped_column(String(255), nullable=True)
    publication_date: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    effective_date: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    revision_ts: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    dataset: Mapped[Dataset] = relationship(back_populates="snapshots")


class Experiment(Base):
    __tablename__ = "experiment"
    __table_args__ = (
        Index("ix_experiment_project_time", "project_id", "started_at"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)  # exp_xxxx
    project_id: Mapped[int] = mapped_column(ForeignKey("project.id"), nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="created")
    git_commit_id: Mapped[int | None] = mapped_column(ForeignKey("git_commit.id"), nullable=True)
    environment_id: Mapped[int | None] = mapped_column(ForeignKey("environment.id"), nullable=True)
    command: Mapped[str] = mapped_column(Text, nullable=False)
    exit_code: Mapped[int | None] = mapped_column(Integer, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # content_hash covers the FULL result state (inputs + outputs + metrics).
    content_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    # input_hash covers ONLY reproducible inputs (code + data + params + env).
    # Two experiments with the same input_hash but different content_hash mean
    # "same inputs, different result" — the core question FRP answers.
    input_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    frozen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    parent_experiment_id: Mapped[str | None] = mapped_column(
        ForeignKey("experiment.id"), nullable=True
    )

    project: Mapped[Project] = relationship(back_populates="experiments")
    git_commit: Mapped[GitCommit | None] = relationship()
    environment: Mapped[Environment | None] = relationship()
    parameters: Mapped[list[Parameter]] = relationship(
        back_populates="experiment", cascade="all, delete-orphan"
    )
    artifacts: Mapped[list[Artifact]] = relationship(
        back_populates="experiment", cascade="all, delete-orphan"
    )
    metrics: Mapped[list[Metric]] = relationship(
        back_populates="experiment", cascade="all, delete-orphan"
    )
    datasets: Mapped[list[ExperimentDataset]] = relationship(
        back_populates="experiment", cascade="all, delete-orphan"
    )
    lineage_edges: Mapped[list[LineageEdge]] = relationship(
        back_populates="experiment", cascade="all, delete-orphan"
    )
    validation_results: Mapped[list[ValidationResult]] = relationship(
        back_populates="experiment", cascade="all, delete-orphan"
    )


class ExperimentDataset(Base):
    """Association between an experiment and a dataset snapshot with a role."""

    __tablename__ = "experiment_dataset"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    experiment_id: Mapped[str] = mapped_column(ForeignKey("experiment.id"), nullable=False)
    dataset_snapshot_id: Mapped[int] = mapped_column(
        ForeignKey("dataset_snapshot.id"), nullable=False
    )
    role: Mapped[str] = mapped_column(String(16), default="input")  # input|output

    experiment: Mapped[Experiment] = relationship(back_populates="datasets")
    snapshot: Mapped[DatasetSnapshot] = relationship()


class Parameter(Base):
    __tablename__ = "parameter"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    experiment_id: Mapped[str] = mapped_column(ForeignKey("experiment.id"), nullable=False)
    key: Mapped[str] = mapped_column(String(255), nullable=False)
    value: Mapped[str] = mapped_column(Text, nullable=False)
    type: Mapped[str] = mapped_column(String(32), default="str")
    source: Mapped[str] = mapped_column(String(32), default="params.json")

    experiment: Mapped[Experiment] = relationship(back_populates="parameters")


class Artifact(Base):
    __tablename__ = "artifact"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    experiment_id: Mapped[str] = mapped_column(ForeignKey("experiment.id"), nullable=False)
    rel_path: Mapped[str] = mapped_column(Text, nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    mime: Mapped[str | None] = mapped_column(String(128), nullable=True)

    experiment: Mapped[Experiment] = relationship(back_populates="artifacts")


class Metric(Base):
    __tablename__ = "metric"
    __table_args__ = (Index("ix_metric_experiment_key", "experiment_id", "key"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    experiment_id: Mapped[str] = mapped_column(ForeignKey("experiment.id"), nullable=False)
    key: Mapped[str] = mapped_column(String(128), nullable=False)
    value: Mapped[float] = mapped_column(Float, nullable=False)
    unit: Mapped[str | None] = mapped_column(String(32), nullable=True)
    source: Mapped[str] = mapped_column(String(32), default="metrics.json")

    experiment: Mapped[Experiment] = relationship(back_populates="metrics")


class LineageEdge(Base):
    __tablename__ = "lineage_edge"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    experiment_id: Mapped[str] = mapped_column(ForeignKey("experiment.id"), nullable=False)
    from_node: Mapped[str] = mapped_column(String(255), nullable=False)
    to_node: Mapped[str] = mapped_column(String(255), nullable=False)
    edge_type: Mapped[str] = mapped_column(String(64), default="produces")

    experiment: Mapped[Experiment] = relationship(back_populates="lineage_edges")


class ValidationResult(Base):
    __tablename__ = "validation_result"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    experiment_id: Mapped[str | None] = mapped_column(ForeignKey("experiment.id"), nullable=True)
    dataset_snapshot_id: Mapped[int | None] = mapped_column(
        ForeignKey("dataset_snapshot.id"), nullable=True
    )
    check_name: Mapped[str] = mapped_column(String(128), nullable=False)
    severity: Mapped[str] = mapped_column(String(16), default="info")  # info|warning|error
    passed: Mapped[bool] = mapped_column(Boolean, default=True)
    detail_json: Mapped[str | None] = mapped_column(Text, nullable=True)

    experiment: Mapped[Experiment | None] = relationship(back_populates="validation_results")