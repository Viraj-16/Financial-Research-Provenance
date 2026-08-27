"""Comparison primitives for reproduction and diff.

These are deterministic, side-effect-free helpers used by both ``reproduce``
(Phase 3) and ``diff`` (Phase 4). They never claim exact reproducibility; they
report observed differences between two experiment aggregates.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field

from frp.models import Experiment


@dataclass
class MetricDelta:
    key: str
    original: float | None
    reproduced: float | None
    within_tolerance: bool


@dataclass
class InputDifference:
    category: str  # code | environment | parameters | data
    detail: str


@dataclass
class ReproductionReport:
    experiment_id: str
    reproduced_id: str
    inputs_match: bool
    metrics_match: bool
    input_differences: list[InputDifference] = field(default_factory=list)
    metric_deltas: list[MetricDelta] = field(default_factory=list)

    @property
    def reproduced(self) -> bool:
        return self.inputs_match and self.metrics_match


def _metrics_map(exp: Experiment) -> dict[str, float]:
    return {m.key: m.value for m in exp.metrics}


def _params_map(exp: Experiment) -> dict[str, str]:
    return {p.key: p.value for p in exp.parameters}


def _input_dataset_hashes(exp: Experiment) -> dict[str, str]:
    """Map dataset name -> sha256 for input-role datasets."""
    result: dict[str, str] = {}
    for link in exp.datasets:
        if link.role != "input":
            continue
        snap = link.snapshot
        if snap is not None and snap.dataset is not None:
            result[snap.dataset.name] = snap.sha256
    return result


def compare_metrics(
    original: Experiment, reproduced: Experiment, tolerance: float
) -> list[MetricDelta]:
    orig = _metrics_map(original)
    repro = _metrics_map(reproduced)
    keys = sorted(set(orig) | set(repro))
    deltas: list[MetricDelta] = []
    for key in keys:
        o = orig.get(key)
        r = repro.get(key)
        if o is None or r is None:
            within = False
        else:
            within = abs(o - r) <= tolerance
        deltas.append(MetricDelta(key=key, original=o, reproduced=r, within_tolerance=within))
    return deltas


def compare_inputs(original: Experiment, reproduced: Experiment) -> list[InputDifference]:
    diffs: list[InputDifference] = []

    # Code
    o_git = original.git_commit
    r_git = reproduced.git_commit
    o_sha = o_git.commit_sha if o_git else None
    r_sha = r_git.commit_sha if r_git else None
    if o_sha != r_sha:
        diffs.append(
            InputDifference("code", f"git commit {o_sha or '-'} → {r_sha or '-'}")
        )
    elif (o_git and o_git.dirty) or (r_git and r_git.dirty):
        diffs.append(InputDifference("code", "working tree was dirty (uncommitted changes)"))

    # Environment (Python version + dependency set hash)
    o_env = original.environment
    r_env = reproduced.environment
    if o_env and r_env:
        if o_env.python_version != r_env.python_version:
            diffs.append(
                InputDifference(
                    "environment",
                    f"Python {o_env.python_version} → {r_env.python_version}",
                )
            )
        if o_env.hash != r_env.hash:
            diffs.append(InputDifference("environment", "dependency set changed"))

    # Parameters
    o_params = _params_map(original)
    r_params = _params_map(reproduced)
    for key in sorted(set(o_params) | set(r_params)):
        if o_params.get(key) != r_params.get(key):
            diffs.append(
                InputDifference(
                    "parameters",
                    f"{key}: {o_params.get(key, '-')} → {r_params.get(key, '-')}",
                )
            )

    # Input datasets
    o_data = _input_dataset_hashes(original)
    r_data = _input_dataset_hashes(reproduced)
    for name in sorted(set(o_data) | set(r_data)):
        if o_data.get(name) != r_data.get(name):
            diffs.append(InputDifference("data", f"{name} content changed"))

    return diffs


def build_reproduction_report(
    original: Experiment, reproduced: Experiment, tolerance: float
) -> ReproductionReport:
    input_diffs = compare_inputs(original, reproduced)
    metric_deltas = compare_metrics(original, reproduced, tolerance)
    metrics_match = all(d.within_tolerance for d in metric_deltas) and bool(metric_deltas)
    return ReproductionReport(
        experiment_id=original.id,
        reproduced_id=reproduced.id,
        inputs_match=not input_diffs,
        metrics_match=metrics_match,
        input_differences=input_diffs,
        metric_deltas=metric_deltas,
    )


def report_to_dict(report: ReproductionReport) -> dict:
    return {
        "experiment_id": report.experiment_id,
        "reproduced_id": report.reproduced_id,
        "reproduced": report.reproduced,
        "inputs_match": report.inputs_match,
        "metrics_match": report.metrics_match,
        "input_differences": [
            {"category": d.category, "detail": d.detail} for d in report.input_differences
        ],
        "metric_deltas": [
            {
                "key": d.key,
                "original": d.original,
                "reproduced": d.reproduced,
                "within_tolerance": d.within_tolerance,
            }
            for d in report.metric_deltas
        ],
    }


def report_to_json(report: ReproductionReport) -> str:
    return json.dumps(report_to_dict(report), indent=2)