"""Dataset registry.

Maps a fingerprint to a logical :class:`Dataset` (by canonical path) and an
immutable :class:`DatasetSnapshot` (deduplicated by content hash). Registering
the same bytes twice returns the existing snapshot rather than creating a
duplicate — snapshots are content-addressed and immutable.
"""

from __future__ import annotations

import json

from sqlalchemy import select
from sqlalchemy.orm import Session

from frp.datasets.fingerprint import DatasetFingerprint, _parse_dt
from frp.models import Dataset, DatasetSnapshot, Project


def get_or_create_dataset(
    session: Session, project: Project, name: str, canonical_path: str
) -> Dataset:
    existing = session.scalar(
        select(Dataset).where(
            Dataset.project_id == project.id,
            Dataset.canonical_path == canonical_path,
        )
    )
    if existing is not None:
        return existing
    dataset = Dataset(project_id=project.id, name=name, canonical_path=canonical_path)
    session.add(dataset)
    session.flush()
    return dataset


def register_snapshot(
    session: Session, project: Project, fp: DatasetFingerprint
) -> DatasetSnapshot:
    """Register (or reuse) an immutable snapshot for a fingerprint."""
    dataset = get_or_create_dataset(session, project, fp.name, fp.path)

    existing = session.scalar(
        select(DatasetSnapshot).where(
            DatasetSnapshot.dataset_id == dataset.id,
            DatasetSnapshot.sha256 == fp.sha256,
        )
    )
    if existing is not None:
        return existing

    snapshot = DatasetSnapshot(
        dataset_id=dataset.id,
        sha256=fp.sha256,
        size_bytes=fp.size_bytes,
        row_count=fp.row_count,
        schema_json=fp.schema_json() if fp.dtypes else None,
        column_names_json=json.dumps(fp.column_names) if fp.column_names else None,
        dtypes_json=fp.schema_json() if fp.dtypes else None,
        date_range_json=json.dumps(fp.date_range) if fp.date_range else None,
        source=fp.source,
        publication_date=_parse_dt(fp.publication_date),
        effective_date=_parse_dt(fp.effective_date),
        revision_ts=_parse_dt(fp.revision_ts),
    )
    session.add(snapshot)
    session.flush()
    return snapshot


def list_datasets(session: Session, project: Project) -> list[Dataset]:
    stmt = select(Dataset).where(Dataset.project_id == project.id).order_by(Dataset.name)
    return list(session.scalars(stmt).all())


def latest_snapshot(session: Session, dataset: Dataset) -> DatasetSnapshot | None:
    stmt = (
        select(DatasetSnapshot)
        .where(DatasetSnapshot.dataset_id == dataset.id)
        .order_by(DatasetSnapshot.observed_at.desc())
    )
    return session.scalars(stmt).first()