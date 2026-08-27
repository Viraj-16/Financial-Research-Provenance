"""Local subprocess runner for research commands.

SECURITY: This executes code locally in the user's own shell context. It is
NOT sandboxed. FRP never fetches or executes remote code. See docs/SECURITY.md.
"""

from __future__ import annotations

import subprocess
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path


@dataclass
class ExecutionResult:
    command: list[str]
    exit_code: int
    stdout: str
    stderr: str
    started_at: datetime
    finished_at: datetime
    duration_ms: int
    new_files: list[Path] = field(default_factory=list)


def _snapshot_files(root: Path) -> dict[Path, float]:
    """Map of file -> mtime for the project tree, excluding the .frp store."""
    snapshot: dict[Path, float] = {}
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        parts = set(path.relative_to(root).parts)
        if ".frp" in parts or ".git" in parts:
            continue
        try:
            snapshot[path] = path.stat().st_mtime
        except OSError:
            continue
    return snapshot


def run_command(command: list[str], cwd: Path, timeout: int | None = None) -> ExecutionResult:
    """Run ``command`` in ``cwd``, capturing output, timing, and new files."""
    before = _snapshot_files(cwd)
    started_at = datetime.now(timezone.utc)
    t0 = time.perf_counter()

    proc = subprocess.run(
        command,
        cwd=str(cwd),
        capture_output=True,
        text=True,
        timeout=timeout,
    )

    duration_ms = int((time.perf_counter() - t0) * 1000)
    finished_at = datetime.now(timezone.utc)
    after = _snapshot_files(cwd)

    new_files: list[Path] = []
    for path, mtime in after.items():
        if path not in before or before[path] != mtime:
            new_files.append(path)
    new_files.sort()

    return ExecutionResult(
        command=command,
        exit_code=proc.returncode,
        stdout=proc.stdout,
        stderr=proc.stderr,
        started_at=started_at,
        finished_at=finished_at,
        duration_ms=duration_ms,
        new_files=new_files,
    )