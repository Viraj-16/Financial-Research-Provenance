"""FRP micro-benchmarks (synthetic data only).

Measures, with the real implementation on this machine:
  * dataset fingerprinting speed vs. row count
  * experiment capture overhead
  * diff time

Results are printed as measured; nothing here is fabricated. Numbers vary by
machine and dataset — treat them as local indications, not published claims.

Run:  python benchmarks/bench.py
"""

from __future__ import annotations

import tempfile
import time
from datetime import date, datetime, timezone
from pathlib import Path

import polars as pl

from frp.capture.environment import capture_environment
from frp.capture.git import GitInfo
from frp.capture.parameters import ParameterInfo
from frp.datasets.fingerprint import fingerprint_dataset
from frp.diff.experiment_diff import diff_experiments
from frp.execution.metrics import MetricInfo
from frp.execution.runner import ExecutionResult
from frp.experiments.service import (
    CaptureBundle,
    create_experiment,
    get_or_create_project,
)
from frp.store.db import init_db, session_scope
from frp.store.paths import ProjectPaths


def _timed(fn, repeat: int = 3) -> float:
    """Return the best (min) wall time over `repeat` runs, in milliseconds."""
    best = float("inf")
    for _ in range(repeat):
        start = time.perf_counter()
        fn()
        best = min(best, time.perf_counter() - start)
    return best * 1000.0


def _make_prices(path: Path, rows: int) -> None:
    base = date(2000, 1, 1).toordinal()
    pl.DataFrame(
        {
            "ticker": ["SYN"] * rows,
            "date": [date.fromordinal(base + (i % 9000)) for i in range(rows)],
            "close": [100.0 + (i % 500) * 0.1 for i in range(rows)],
            "volume": [1000 + (i % 100) for i in range(rows)],
        }
    ).write_parquet(path)


def bench_fingerprint(tmp: Path) -> None:
    print("\n[dataset fingerprinting] (synthetic prices.parquet)")
    for rows in (1_000, 10_000, 100_000, 1_000_000):
        p = tmp / f"prices_{rows}.parquet"
        _make_prices(p, rows)
        size_mb = p.stat().st_size / 1e6
        ms = _timed(lambda p=p: fingerprint_dataset(p))
        print(f"  rows={rows:>9,}  size={size_mb:6.2f} MB  fingerprint={ms:8.2f} ms")


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


def bench_capture_and_diff(tmp: Path) -> None:
    root = tmp / "proj"
    root.mkdir()
    paths = ProjectPaths(root)
    paths.ensure_dirs()
    engine = init_db(paths.db_path)

    print("\n[experiment capture] (no artifacts, in-DB)")
    created: list[str] = []

    def _capture() -> None:
        with session_scope(engine) as session:
            proj = get_or_create_project(session, "bench", str(root))
            exp = create_experiment(session, paths, proj, _bundle())
            created.append(exp.id)

    ms = _timed(_capture, repeat=5)
    print(f"  capture (best of 5) = {ms:8.2f} ms")

    print("\n[experiment diff]")
    with session_scope(engine) as session:
        proj = get_or_create_project(session, "bench", str(root))
        a = create_experiment(session, paths, proj, _bundle())
        b = create_experiment(session, paths, proj, _bundle())
        session.flush()
        ms = _timed(lambda: diff_experiments(a, b), repeat=100)
    print(f"  diff (best of 100) = {ms:8.4f} ms")

    # Release the SQLite file handle so temp cleanup succeeds on Windows.
    engine.dispose()


def main() -> None:
    print("FRP benchmarks — synthetic data only; measured on this machine.")
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as td:
        tmp = Path(td)
        bench_fingerprint(tmp)
        bench_capture_and_diff(tmp)


if __name__ == "__main__":
    main()