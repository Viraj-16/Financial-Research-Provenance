"""Git commit capture.

We shell out to the ``git`` binary (present on the researcher's machine) rather
than adding a dependency. All calls are read-only and fail gracefully if the
repository is not a git repo.
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path

from frp.hashing import hash_bytes


@dataclass
class GitInfo:
    commit_sha: str | None
    branch: str | None
    dirty: bool
    diff_hash: str | None
    remote_url: str | None
    is_repo: bool


def _run_git(root: Path, *args: str) -> tuple[int, str]:
    try:
        proc = subprocess.run(
            ["git", *args],
            cwd=str(root),
            capture_output=True,
            text=True,
            timeout=30,
        )
        return proc.returncode, proc.stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return 1, ""


def capture_git(root: Path) -> GitInfo:
    """Capture the current git state of ``root``."""
    code, _ = _run_git(root, "rev-parse", "--is-inside-work-tree")
    if code != 0:
        return GitInfo(None, None, False, None, None, is_repo=False)

    _, sha = _run_git(root, "rev-parse", "HEAD")
    _, branch = _run_git(root, "rev-parse", "--abbrev-ref", "HEAD")
    _, status = _run_git(root, "status", "--porcelain")
    dirty = bool(status.strip())

    diff_hash = None
    if dirty:
        code, diff = _run_git(root, "diff", "HEAD")
        if code == 0 and diff:
            diff_hash = hash_bytes(diff.encode("utf-8", errors="replace"))

    _, remote = _run_git(root, "config", "--get", "remote.origin.url")

    return GitInfo(
        commit_sha=sha or None,
        branch=branch or None,
        dirty=dirty,
        diff_hash=diff_hash,
        remote_url=remote or None,
        is_repo=True,
    )