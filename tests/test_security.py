"""Security-focused tests (Phase 7).

These verify FRP's defensive boundaries: it rejects invalid experiment ids,
refuses to record artifacts outside the project root (path traversal), and
fails cleanly on malformed metadata rather than crashing or trusting input.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest

from frp.capture.environment import capture_environment
from frp.capture.git import GitInfo
from frp.execution.runner import ExecutionResult
from frp.experiments.ids import validate_experiment_id
from frp.experiments.service import (
    CaptureBundle,
    _safe_relative,
    create_experiment,
    get_experiment,
    get_or_create_project,
)
from frp.store.paths import ProjectPaths


@pytest.mark.parametrize(
    "bad_id",
    [
        "",
        "exp",  # missing hex
        "exp_",  # empty hex
        "exp_ZZZZ",  # non-hex
        "'; DROP TABLE experiments;--",  # sql-ish
        "../../etc/passwd",  # path-ish
        "exp_" + "a" * 100,  # too long
    ],
)
def test_invalid_experiment_ids_rejected(bad_id: str) -> None:
    with pytest.raises(ValueError):
        validate_experiment_id(bad_id)


def test_get_experiment_validates_id(project: ProjectPaths, session_factory) -> None:
    with session_factory() as session:
        with pytest.raises(ValueError):
            get_experiment(session, "../../secrets")


def test_path_traversal_artifact_rejected(project: ProjectPaths) -> None:
    root = project.root
    outside = (root.parent / "outside.txt").resolve()
    with pytest.raises(ValueError):
        _safe_relative(root, outside)


def test_artifact_outside_root_rejected(project: ProjectPaths, session_factory) -> None:
    # Craft a bundle whose artifact lives outside the project root.
    outside = (project.root.parent / "evil.bin")
    outside.write_bytes(b"x")
    now = datetime.now(timezone.utc)
    bundle = CaptureBundle(
        command=["python", "x.py"],
        git=GitInfo(None, None, False, None, None, is_repo=False),
        environment=capture_environment(),
        parameters=[],
        execution=ExecutionResult(["python", "x.py"], 0, "", "", now, now, 1, []),
        metrics=[],
        artifact_files=[outside],
    )
    with session_factory() as session:
        proj = get_or_create_project(session, "demo", str(project.root))
        with pytest.raises(ValueError):
            create_experiment(session, project, proj, bundle)


def test_malformed_sidecar_metadata(tmp_path: Path) -> None:
    from frp.datasets.fingerprint import fingerprint_dataset

    p = tmp_path / "data.csv"
    p.write_text("a,b\n1,2\n")
    # Malformed JSON sidecar must raise a clean ValueError, not crash.
    p.with_name("data.csv.frpmeta.json").write_text("{ not valid json")
    with pytest.raises(ValueError):
        fingerprint_dataset(p)


def test_sidecar_must_be_object(tmp_path: Path) -> None:
    from frp.datasets.fingerprint import fingerprint_dataset

    p = tmp_path / "data.csv"
    p.write_text("a,b\n1,2\n")
    p.with_name("data.csv.frpmeta.json").write_text("[1, 2, 3]")  # not an object
    with pytest.raises(ValueError):
        fingerprint_dataset(p)