"""Tests for dataset fingerprinting and registry (Phase 2)."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import polars as pl

from frp.datasets.fingerprint import fingerprint_dataset
from frp.datasets.registry import (
    latest_snapshot,
    list_datasets,
    register_snapshot,
)
from frp.experiments.service import get_or_create_project
from frp.store.paths import ProjectPaths


def _make_parquet(path: Path, rows: int = 3) -> None:
    df = pl.DataFrame(
        {
            "ticker": ["AAA", "BBB", "CCC"][:rows],
            "date": [
                date(2023, 1, 1),
                date(2023, 1, 2),
                date(2023, 1, 3),
            ][:rows],
            "close": [10.0, 20.0, 30.0][:rows],
        }
    )
    df.write_parquet(path)


def test_same_dataset_same_hash(tmp_path: Path) -> None:
    a = tmp_path / "a.parquet"
    b = tmp_path / "b.parquet"
    _make_parquet(a)
    _make_parquet(b)
    fa = fingerprint_dataset(a)
    fb = fingerprint_dataset(b)
    assert fa.sha256 == fb.sha256


def test_changed_dataset_different_hash(tmp_path: Path) -> None:
    a = tmp_path / "a.parquet"
    b = tmp_path / "b.parquet"
    _make_parquet(a, rows=3)
    _make_parquet(b, rows=2)
    assert fingerprint_dataset(a).sha256 != fingerprint_dataset(b).sha256


def test_fingerprint_metadata(tmp_path: Path) -> None:
    p = tmp_path / "prices.parquet"
    _make_parquet(p)
    fp = fingerprint_dataset(p)
    assert fp.row_count == 3
    assert set(fp.column_names) == {"ticker", "date", "close"}
    assert fp.dtypes["close"].lower().startswith("float")
    assert fp.date_range is not None
    assert fp.date_range["column"] == "date"
    assert fp.date_range["min"] == "2023-01-01"
    assert fp.date_range["max"] == "2023-01-03"


def test_csv_fingerprint(tmp_path: Path) -> None:
    p = tmp_path / "data.csv"
    p.write_text("a,b\n1,2\n3,4\n")
    fp = fingerprint_dataset(p)
    assert fp.row_count == 2
    assert fp.column_names == ["a", "b"]


def test_non_tabular_fingerprint(tmp_path: Path) -> None:
    p = tmp_path / "notes.txt"
    p.write_text("hello")
    fp = fingerprint_dataset(p)
    assert fp.sha256
    assert fp.row_count is None
    assert fp.column_names == []


def test_sidecar_point_in_time(tmp_path: Path) -> None:
    p = tmp_path / "prices.parquet"
    _make_parquet(p)
    p.with_name("prices.parquet.frpmeta.json").write_text(
        '{"source": "vendor", "publication_date": "2023-05-04"}'
    )
    fp = fingerprint_dataset(p)
    assert fp.source == "vendor"
    assert fp.publication_date == "2023-05-04"


def test_registry_dedup_snapshot(project: ProjectPaths, session_factory) -> None:
    p = project.root / "prices.parquet"
    _make_parquet(p)
    fp = fingerprint_dataset(p)
    with session_factory() as session:
        proj = get_or_create_project(session, "demo", str(project.root))
        s1 = register_snapshot(session, proj, fp)
        s2 = register_snapshot(session, proj, fp)
        session.commit()
        assert s1.id == s2.id  # same content => same snapshot
        assert len(list_datasets(session, proj)) == 1
        assert latest_snapshot(session, s1.dataset).id == s1.id