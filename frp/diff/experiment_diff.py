"""Experiment-to-experiment diff.

Answers: WHAT CHANGED BETWEEN THESE TWO RESULTS? Produces sectioned diffs for
code, data, parameters, environment, and results (metrics). Deterministic and
side-effect-free.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from frp.models import Experiment


@dataclass
class FieldChange:
    key: str
    a: str | None
    b: str | None

    @property
    def changed(self) -> bool:
        return self.a != self.b


@dataclass
class MetricChange:
    key: str
    a: float | None
    b: float | None

    @property
    def changed(self) -> bool:
        return self.a != self.b


@dataclass
class ExperimentDiff:
    experiment_a: str
    experiment_b: str
    code: list[FieldChange] = field(default_factory=list)
    data: list[FieldChange] = field(default_factory=list)
    parameters: list[FieldChange] = field(default_factory=list)
    environment: list[FieldChange] = field(default_factory=list)
    metrics: list[MetricChange] = field(default_factory=list)

    @property
    def any_change(self) -> bool:
        return any(
            [
                any(c.changed for c in self.code),
                any(c.changed for c in self.data),
                any(c.changed for c in self.parameters),
                any(c.changed for c in self.environment),
                any(c.changed for c in self.metrics),
            ]
        )


def _params_map(exp: Experiment) -> dict[str, str]:
    return {p.key: p.value for p in exp.parameters}


def _metrics_map(exp: Experiment) -> dict[str, float]:
    return {m.key: m.value for m in exp.metrics}


def _input_dataset_hashes(exp: Experiment) -> dict[str, str]:
    result: dict[str, str] = {}
    for link in exp.datasets:
        if link.role != "input":
            continue
        snap = link.snapshot
        if snap is not None and snap.dataset is not None:
            result[snap.dataset.name] = snap.sha256
    return result


def diff_experiments(a: Experiment, b: Experiment) -> ExperimentDiff:
    diff = ExperimentDiff(experiment_a=a.id, experiment_b=b.id)

    # CODE
    a_git, b_git = a.git_commit, b.git_commit
    diff.code.append(
        FieldChange(
            "git_commit",
            a_git.commit_sha if a_git else None,
            b_git.commit_sha if b_git else None,
        )
    )

    # DATA (by logical dataset name → content hash)
    a_data = _input_dataset_hashes(a)
    b_data = _input_dataset_hashes(b)
    for name in sorted(set(a_data) | set(b_data)):
        diff.data.append(FieldChange(name, a_data.get(name), b_data.get(name)))

    # PARAMETERS
    a_params = _params_map(a)
    b_params = _params_map(b)
    for key in sorted(set(a_params) | set(b_params)):
        diff.parameters.append(FieldChange(key, a_params.get(key), b_params.get(key)))

    # ENVIRONMENT
    a_env, b_env = a.environment, b.environment
    diff.environment.append(
        FieldChange(
            "python",
            a_env.python_version if a_env else None,
            b_env.python_version if b_env else None,
        )
    )
    diff.environment.append(
        FieldChange(
            "dependencies_hash",
            a_env.hash if a_env else None,
            b_env.hash if b_env else None,
        )
    )

    # METRICS
    a_metrics = _metrics_map(a)
    b_metrics = _metrics_map(b)
    for key in sorted(set(a_metrics) | set(b_metrics)):
        diff.metrics.append(MetricChange(key, a_metrics.get(key), b_metrics.get(key)))

    return diff


def diff_to_dict(diff: ExperimentDiff) -> dict:
    def fc(items: list[FieldChange]) -> list[dict]:
        return [
            {"key": c.key, "a": c.a, "b": c.b, "changed": c.changed}
            for c in items
        ]

    return {
        "experiment_a": diff.experiment_a,
        "experiment_b": diff.experiment_b,
        "code": fc(diff.code),
        "data": fc(diff.data),
        "parameters": fc(diff.parameters),
        "environment": fc(diff.environment),
        "metrics": [
            {"key": m.key, "a": m.a, "b": m.b, "changed": m.changed}
            for m in diff.metrics
        ],
        "any_change": diff.any_change,
    }