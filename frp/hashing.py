"""Content hashing utilities shared across FRP.

All hashes are SHA-256. Two flavors are provided:

* :func:`hash_file` streams a file's raw bytes (dataset/artifact identity).
* :func:`hash_json` produces a stable hash of a canonicalized JSON structure
  (used for environment fingerprints and experiment ``content_hash``).
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

_CHUNK = 1024 * 1024  # 1 MiB


def hash_file(path: Path) -> str:
    """Stream-hash the raw bytes of a file with SHA-256."""
    h = hashlib.sha256()
    with path.open("rb") as fh:
        while True:
            chunk = fh.read(_CHUNK)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


def hash_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def canonical_json(obj: Any) -> str:
    """Serialize ``obj`` to canonical JSON (sorted keys, no whitespace)."""
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), default=str)


def hash_json(obj: Any) -> str:
    """SHA-256 of the canonical JSON serialization of ``obj``."""
    return hash_bytes(canonical_json(obj).encode("utf-8"))