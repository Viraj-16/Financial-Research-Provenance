"""Shared pytest fixtures for FRP tests."""

from __future__ import annotations

from pathlib import Path

import pytest

from frp.store.db import init_db, make_session_factory
from frp.store.paths import ProjectPaths


@pytest.fixture()
def project(tmp_path: Path) -> ProjectPaths:
    paths = ProjectPaths(tmp_path)
    paths.ensure_dirs()
    init_db(paths.db_path)
    return paths


@pytest.fixture()
def session_factory(project: ProjectPaths):
    engine = init_db(project.db_path)
    return make_session_factory(engine)