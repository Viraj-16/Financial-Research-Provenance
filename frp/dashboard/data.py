"""Serialize the FRP store into a dashboard-friendly JSON structure.

Read-only: this never mutates the store. It powers both the static HTML
dashboard and a ``--json`` export for external tools (e.g. a Next.js frontend).
"""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from frp.experiments.service import list_experiments
from frp.models import Project


def _experiment_summary(exp: Any) -> dict:
    gc = exp.git_commit
    return {
        "id": exp.id,
        "status": exp.status,
        "command": exp.command,
        "started_at": exp.started_at.isoformat() if exp.started_at else None,
        "duration_ms": exp.duration_ms,
        "git_commit": gc.commit_sha if gc else None,
        "input_hash": exp.input_hash,
        "content_hash": exp.content_hash,
        "parent_experiment_id": exp.parent_experiment_id,
        "parameters": {p.key: p.value for p in exp.parameters},
        "metrics": {m.key: m.value for m in exp.metrics},
        "artifacts": [
            {"path": a.rel_path, "sha256": a.sha256, "size_bytes": a.size_bytes}
            for a in exp.artifacts
        ],
        "environment": (
            {
                "python": exp.environment.python_version,
                "platform": exp.environment.platform,
                "dependency_count": len(exp.environment.dependencies),
            }
            if exp.environment
            else None
        ),
    }


def build_dashboard_data(session: Session, project: Project) -> dict:
    """Build the full dashboard payload for a project."""
    experiments = list_experiments(session, project)
    exp_payload = [_experiment_summary(e) for e in experiments]

    latest = exp_payload[0] if exp_payload else None
    return {
        "project": {
            "name": project.name,
            "root_path": project.root_path,
            "experiment_count": len(exp_payload),
            "latest_experiment": latest["id"] if latest else None,
            "last_activity": latest["started_at"] if latest else None,
        },
        "experiments": exp_payload,
    }