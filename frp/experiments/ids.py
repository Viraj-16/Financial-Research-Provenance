"""Experiment identifier generation and validation.

Experiment ids look like ``exp_<12 hex chars>``. Ids are content-agnostic and
random; the experiment's reproducibility identity is carried by
``content_hash``, not the id. Validation is used defensively before any DB
lookup to reject malformed input (see security model).
"""

from __future__ import annotations

import re
import secrets

EXPERIMENT_ID_RE = re.compile(r"^exp_[0-9a-f]{12}$")


def new_experiment_id() -> str:
    return f"exp_{secrets.token_hex(6)}"


def is_valid_experiment_id(value: str) -> bool:
    return bool(EXPERIMENT_ID_RE.match(value))


def validate_experiment_id(value: str) -> str:
    """Return ``value`` if it is a well-formed id, else raise ``ValueError``."""
    if not is_valid_experiment_id(value):
        raise ValueError(
            f"Invalid experiment id: {value!r}. Expected format 'exp_<12 hex chars>'."
        )
    return value