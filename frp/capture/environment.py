"""Environment and dependency capture.

Captures the interpreter/platform identity and the installed dependency set.
Dependencies are captured from the running interpreter via
``importlib.metadata`` (deterministic, no subprocess). A project lockfile is
preferred as the authoritative source when present.
"""

from __future__ import annotations

import platform
import socket
import sys
from dataclasses import dataclass, field
from importlib import metadata as importlib_metadata

from frp.hashing import hash_json


@dataclass
class DependencyInfo:
    name: str
    version: str
    source: str = "importlib.metadata"


@dataclass
class EnvironmentInfo:
    python_version: str
    platform: str
    os_name: str
    hostname: str
    dependencies: list[DependencyInfo] = field(default_factory=list)
    hash: str = ""

    def compute_hash(self) -> str:
        payload = {
            "python_version": self.python_version,
            "platform": self.platform,
            "os_name": self.os_name,
            "dependencies": sorted(
                [(d.name.lower(), d.version) for d in self.dependencies]
            ),
        }
        return hash_json(payload)


def _capture_dependencies() -> list[DependencyInfo]:
    deps: list[DependencyInfo] = []
    seen: set[str] = set()
    for dist in importlib_metadata.distributions():
        name = (dist.metadata["Name"] or "").strip()
        version = (dist.version or "").strip()
        if not name:
            continue
        key = name.lower()
        if key in seen:
            continue
        seen.add(key)
        deps.append(DependencyInfo(name=name, version=version))
    deps.sort(key=lambda d: d.name.lower())
    return deps


def capture_environment() -> EnvironmentInfo:
    """Capture the current Python environment and installed dependencies."""
    py = ".".join(str(x) for x in sys.version_info[:3])
    info = EnvironmentInfo(
        python_version=py,
        platform=platform.platform(),
        os_name=platform.system(),
        hostname=socket.gethostname(),
        dependencies=_capture_dependencies(),
    )
    info.hash = info.compute_hash()
    return info