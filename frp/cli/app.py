"""FRP CLI application (entry point ``frpx``).

Phase 1 commands: init, status, run, list, show.
"""

from __future__ import annotations

import json as json_mod
import sys
from pathlib import Path

import typer

from frp.capture.environment import capture_environment
from frp.capture.git import capture_git
from frp.capture.parameters import capture_parameters
from frp.cli import render
from frp.dashboard.data import build_dashboard_data
from frp.dashboard.server import render_dashboard_html, serve_dashboard
from frp.datasets.fingerprint import fingerprint_dataset
from frp.datasets.registry import latest_snapshot, list_datasets, register_snapshot
from frp.diff.dataset_diff import dataset_diff_to_dict, diff_datasets
from frp.diff.experiment_diff import diff_experiments, diff_to_dict
from frp.execution.metrics import detect_metrics
from frp.execution.runner import run_command
from frp.experiments.service import (
    CaptureBundle,
    create_experiment,
    get_experiment,
    get_or_create_project,
    list_experiments,
)
from frp.reproduction.compare import report_to_json
from frp.reproduction.reproduce import ReproductionError, load_and_reproduce
from frp.store import config as config_mod
from frp.store.db import init_db, session_scope
from frp.store.paths import ProjectNotFoundError, ProjectPaths, resolve_project
from frp.validation.lookahead import check_lookahead, parse_backtest_date
from frp.validation.quality import validate_file

app = typer.Typer(
    name="frpx",
    help="Financial Research Provenance — version the entire research state.",
    no_args_is_help=True,
    add_completion=False,
)

dataset_app = typer.Typer(help="Register and inspect datasets.", no_args_is_help=True)
app.add_typer(dataset_app, name="dataset")


def _resolve_or_exit() -> ProjectPaths:
    try:
        return resolve_project()
    except ProjectNotFoundError as exc:
        render.error(str(exc))
        raise typer.Exit(code=2) from exc


@app.command()
def init(
    name: str = typer.Option(None, "--name", help="Project name (defaults to directory name)."),
) -> None:
    """Initialize an FRP project in the current directory."""
    paths = ProjectPaths(Path.cwd())
    if paths.exists():
        render.step_warn(f"FRP project already initialized at {paths.frp_dir}")
        raise typer.Exit(code=0)

    project_name = name or paths.root.name
    paths.ensure_dirs()
    init_db(paths.db_path)
    config_mod.write_config(
        paths.config_path, config_mod.ProjectConfig(name=project_name)
    )

    engine = init_db(paths.db_path)
    with session_scope(engine) as session:
        get_or_create_project(session, project_name, str(paths.root))

    render.step_ok(f"Initialized FRP project '{project_name}'")
    render.console.print(f"  Store: {paths.frp_dir}")
    render.console.print(
        "\n[dim]Note: FRP executes research code locally and is NOT sandboxed. "
        "Only run code you trust.[/dim]"
    )


@app.command()
def status() -> None:
    """Show project status: git state, config, and last experiment."""
    paths = _resolve_or_exit()
    cfg = config_mod.read_config(paths.config_path)
    git = capture_git(paths.root)

    render.console.print(f"[bold]Project:[/bold] {cfg.name}")
    render.console.print(f"[bold]Root:[/bold] {paths.root}")
    if git.is_repo:
        dirty = " [yellow](dirty)[/yellow]" if git.dirty else " [green](clean)[/green]"
        sha = git.commit_sha[:8] if git.commit_sha else "-"
        render.console.print(f"[bold]Git:[/bold] {git.branch or '-'} @ {sha}{dirty}")
    else:
        render.console.print("[bold]Git:[/bold] not a git repository")

    engine = init_db(paths.db_path)
    with session_scope(engine) as session:
        project = get_or_create_project(session, cfg.name, str(paths.root))
        experiments = list_experiments(session, project)
        render.console.print(f"[bold]Experiments:[/bold] {len(experiments)}")
        if experiments:
            latest = experiments[0]
            render.console.print(f"  Latest: {latest.id} ({latest.status})")


@app.command(
    context_settings={"allow_extra_args": True, "ignore_unknown_options": True},
)
def run(
    ctx: typer.Context,
    param: list[str] = typer.Option(
        None, "--param", "-p", help="Override parameter key=value (repeatable)."
    ),
    input_path: list[str] = typer.Option(
        None,
        "--input",
        "-i",
        help="Declare an input dataset to fingerprint (repeatable).",
    ),
    timeout: int = typer.Option(None, "--timeout", help="Kill the command after N seconds."),
) -> None:
    """Run a command through FRP and record an immutable experiment.

    Example: frpx run python backtest.py
    """
    command = list(ctx.args)
    if not command:
        render.error("No command provided. Example: frpx run python backtest.py")
        raise typer.Exit(code=2)

    paths = _resolve_or_exit()
    cfg = config_mod.read_config(paths.config_path)

    render.console.print("[bold]FRP Experiment[/bold]\n")

    git = capture_git(paths.root)
    if git.is_repo:
        render.step_ok("Git commit captured")
        if git.dirty:
            render.step_warn("Working tree is dirty — reproducibility is not guaranteed")
    else:
        render.step_warn("Not a git repository — code provenance limited")

    environment = capture_environment()
    render.step_ok("Python environment captured")

    try:
        parameters = capture_parameters(paths.root, param)
    except ValueError as exc:
        render.error(str(exc))
        raise typer.Exit(code=2) from exc
    render.step_ok(f"Parameters captured ({len(parameters)})")

    input_datasets = []
    for raw in input_path or []:
        ds_path = (paths.root / raw).resolve() if not Path(raw).is_absolute() else Path(raw)
        try:
            input_datasets.append(fingerprint_dataset(ds_path))
        except FileNotFoundError as exc:
            render.error(str(exc))
            raise typer.Exit(code=2) from exc
    if input_datasets:
        render.step_ok(f"Dataset fingerprints calculated ({len(input_datasets)})")

    # Look-ahead warning: compare declared backtest_date vs. dataset publication dates.
    param_map = {p.key: p.value for p in parameters}
    lookahead_warnings = check_lookahead(parse_backtest_date(param_map), input_datasets)
    if lookahead_warnings:
        render.step_warn("Potential look-ahead bias detected")
        render.render_lookahead(lookahead_warnings)

    try:
        execution = run_command(command, cwd=paths.root, timeout=timeout)
    except FileNotFoundError as exc:
        render.error(f"Command not found: {command[0]}")
        raise typer.Exit(code=127) from exc

    if execution.stdout:
        render.console.print(execution.stdout, end="")
    if execution.stderr:
        render.console.print(execution.stderr, end="")

    if execution.exit_code == 0:
        render.step_ok("Execution completed")
    else:
        render.step_fail(f"Execution failed (exit code {execution.exit_code})")

    try:
        metrics = detect_metrics(paths.root, execution.stdout)
    except ValueError as exc:
        render.error(str(exc))
        raise typer.Exit(code=2) from exc
    if metrics:
        render.step_ok(f"Metrics detected ({len(metrics)})")
    else:
        render.step_warn("No metrics detected (add metrics.json or FRP_METRIC lines)")

    # Exclude declared inputs from detected outputs (a file can't be both).
    input_resolved = {Path(d.path).resolve() for d in input_datasets}
    artifact_files = [f for f in execution.new_files if f.resolve() not in input_resolved]

    bundle = CaptureBundle(
        command=command,
        git=git,
        environment=environment,
        parameters=parameters,
        execution=execution,
        metrics=metrics,
        artifact_files=artifact_files,
        input_datasets=input_datasets,
    )

    engine = init_db(paths.db_path)
    with session_scope(engine) as session:
        project = get_or_create_project(session, cfg.name, str(paths.root))
        experiment = create_experiment(session, paths, project, bundle)
        experiment_id = experiment.id
        # Re-read inside session for rendering
        render.render_run_summary(experiment)

    if execution.exit_code != 0:
        raise typer.Exit(code=1)

    _ = experiment_id


@app.command(name="list")
def list_cmd(
    as_json: bool = typer.Option(False, "--json", help="Output machine-readable JSON."),
) -> None:
    """List experiments in this project."""
    paths = _resolve_or_exit()
    cfg = config_mod.read_config(paths.config_path)
    engine = init_db(paths.db_path)
    with session_scope(engine) as session:
        project = get_or_create_project(session, cfg.name, str(paths.root))
        experiments = list_experiments(session, project)
        if as_json:
            payload = [
                {
                    "id": e.id,
                    "status": e.status,
                    "started_at": e.started_at.isoformat() if e.started_at else None,
                    "git_commit": e.git_commit.commit_sha if e.git_commit else None,
                    "input_hash": e.input_hash,
                    "content_hash": e.content_hash,
                    "metrics": {m.key: m.value for m in e.metrics},
                }
                for e in experiments
            ]
            render.console.print_json(json_mod.dumps(payload))
            return
        if not experiments:
            render.console.print("No experiments yet. Run 'frpx run <command>'.")
            return
        render.render_experiment_table(experiments)


@app.command()
def show(
    experiment_id: str = typer.Argument(..., help="Experiment id (exp_...)."),
    as_json: bool = typer.Option(False, "--json", help="Output machine-readable JSON."),
) -> None:
    """Show full details of an experiment."""
    paths = _resolve_or_exit()
    engine = init_db(paths.db_path)
    with session_scope(engine) as session:
        try:
            experiment = get_experiment(session, experiment_id)
        except ValueError as exc:
            render.error(str(exc))
            raise typer.Exit(code=2) from exc
        if experiment is None:
            render.error(f"Experiment not found: {experiment_id}")
            raise typer.Exit(code=1)
        if as_json:
            gc = experiment.git_commit
            payload = {
                "id": experiment.id,
                "status": experiment.status,
                "command": experiment.command,
                "exit_code": experiment.exit_code,
                "duration_ms": experiment.duration_ms,
                "input_hash": experiment.input_hash,
                "content_hash": experiment.content_hash,
                "git": {
                    "commit_sha": gc.commit_sha if gc else None,
                    "branch": gc.branch if gc else None,
                    "dirty": gc.dirty if gc else None,
                },
                "parameters": {p.key: p.value for p in experiment.parameters},
                "metrics": {m.key: m.value for m in experiment.metrics},
                "artifacts": [
                    {"path": a.rel_path, "sha256": a.sha256, "size_bytes": a.size_bytes}
                    for a in experiment.artifacts
                ],
                "input_datasets": [
                    {"snapshot_id": d.dataset_snapshot_id, "role": d.role}
                    for d in experiment.datasets
                ],
            }
            render.console.print_json(json_mod.dumps(payload))
            return
        render.render_experiment_detail(experiment)


@app.command()
def reproduce(
    experiment_id: str = typer.Argument(..., help="Experiment id to reproduce (exp_...)."),
    timeout: int = typer.Option(None, "--timeout", help="Kill the re-run after N seconds."),
    as_json: bool = typer.Option(False, "--json", help="Output machine-readable JSON."),
) -> None:
    """Re-run an experiment and compare results against the original.

    FRP re-runs the recorded command in the CURRENT environment. It cannot
    restore a past interpreter/dependency state; input differences are reported
    rather than silently ignored.
    """
    paths = _resolve_or_exit()
    cfg = config_mod.read_config(paths.config_path)
    engine = init_db(paths.db_path)
    with session_scope(engine) as session:
        try:
            outcome = load_and_reproduce(
                session, paths, cfg.name, experiment_id, cfg.metric_tolerance, timeout
            )
        except ValueError as exc:  # invalid id
            render.error(str(exc))
            raise typer.Exit(code=2) from exc
        except ReproductionError as exc:
            render.error(str(exc))
            raise typer.Exit(code=1) from exc

        if as_json:
            render.console.print_json(report_to_json(outcome.report))
        else:
            render.render_reproduction_report(outcome.report)

        if not outcome.report.reproduced:
            raise typer.Exit(code=1)


@app.command()
def diff(
    experiment_a: str = typer.Argument(..., help="First experiment id (exp_...)."),
    experiment_b: str = typer.Argument(..., help="Second experiment id (exp_...)."),
    as_json: bool = typer.Option(False, "--json", help="Output machine-readable JSON."),
) -> None:
    """Show what changed between two experiments (code/data/params/env/results)."""
    paths = _resolve_or_exit()
    engine = init_db(paths.db_path)
    with session_scope(engine) as session:
        try:
            a = get_experiment(session, experiment_a)
            b = get_experiment(session, experiment_b)
        except ValueError as exc:
            render.error(str(exc))
            raise typer.Exit(code=2) from exc
        if a is None:
            render.error(f"Experiment not found: {experiment_a}")
            raise typer.Exit(code=1)
        if b is None:
            render.error(f"Experiment not found: {experiment_b}")
            raise typer.Exit(code=1)

        experiment_diff = diff_experiments(a, b)
        if as_json:
            render.console.print_json(json_mod.dumps(diff_to_dict(experiment_diff)))
        else:
            render.render_experiment_diff(experiment_diff)


@app.command()
def dashboard(
    export: str = typer.Option(
        None, "--export", help="Write the dashboard HTML to this path instead of serving."
    ),
    as_json: bool = typer.Option(False, "--json", help="Print the dashboard data as JSON."),
    host: str = typer.Option("127.0.0.1", "--host", help="Host to bind when serving."),
    port: int = typer.Option(8787, "--port", help="Port to bind when serving."),
) -> None:
    """Serve (or export) a read-only web dashboard over the local store.

    The dashboard executes no research code and only reads the local database.
    """
    paths = _resolve_or_exit()
    cfg = config_mod.read_config(paths.config_path)
    engine = init_db(paths.db_path)
    with session_scope(engine) as session:
        project = get_or_create_project(session, cfg.name, str(paths.root))
        data = build_dashboard_data(session, project)

    if as_json:
        render.console.print_json(json_mod.dumps(data))
        return

    html = render_dashboard_html(data)
    if export:
        out = (paths.root / export).resolve() if not Path(export).is_absolute() else Path(export)
        out.write_text(html, encoding="utf-8")
        render.step_ok(f"Dashboard written to {out}")
        return

    render.console.print(
        f"[bold]FRP dashboard[/bold] for '{cfg.name}' → "
        f"[cyan]http://{host}:{port}[/cyan]  [dim](Ctrl+C to stop)[/dim]"
    )
    try:
        serve_dashboard(html, host=host, port=port)
    except OSError as exc:
        render.error(f"Could not start server: {exc}")
        raise typer.Exit(code=1) from exc


@app.command()
def validate(
    path: str = typer.Argument(..., help="Dataset file to validate."),
    as_json: bool = typer.Option(False, "--json", help="Output machine-readable JSON."),
) -> None:
    """Run data-quality checks on a dataset (generic + financial where applicable)."""
    paths = _resolve_or_exit()
    ds_path = (paths.root / path).resolve() if not Path(path).is_absolute() else Path(path)
    try:
        results = validate_file(ds_path)
    except (FileNotFoundError, ValueError) as exc:
        render.error(str(exc))
        raise typer.Exit(code=2) from exc

    if as_json:
        payload = [
            {
                "check_name": r.check_name,
                "severity": r.severity,
                "passed": r.passed,
                "detail": r.detail,
            }
            for r in results
        ]
        render.console.print_json(json_mod.dumps(payload))
    else:
        render.render_validation(results)

    if any(r.severity == "error" and not r.passed for r in results):
        raise typer.Exit(code=1)


@dataset_app.command("diff")
def dataset_diff_cmd(
    path_a: str = typer.Argument(..., help="First dataset file."),
    path_b: str = typer.Argument(..., help="Second dataset file."),
    as_json: bool = typer.Option(False, "--json", help="Output machine-readable JSON."),
) -> None:
    """Compare two dataset files (rows, schema, columns, dtypes, date range)."""
    paths = _resolve_or_exit()

    def _resolve(raw: str):  # noqa: ANN202
        return (paths.root / raw).resolve() if not Path(raw).is_absolute() else Path(raw)

    try:
        fp_a = fingerprint_dataset(_resolve(path_a))
        fp_b = fingerprint_dataset(_resolve(path_b))
    except (FileNotFoundError, ValueError) as exc:
        render.error(str(exc))
        raise typer.Exit(code=2) from exc

    ds_diff = diff_datasets(fp_a, fp_b)
    if as_json:
        render.console.print_json(json_mod.dumps(dataset_diff_to_dict(ds_diff)))
    else:
        render.render_dataset_diff(ds_diff)


@dataset_app.command("add")
def dataset_add(
    path: str = typer.Argument(..., help="Path to the dataset file to fingerprint."),
    name: str = typer.Option(None, "--name", help="Logical dataset name."),
) -> None:
    """Fingerprint and register a dataset (identity + metadata; bytes not copied)."""
    paths = _resolve_or_exit()
    cfg = config_mod.read_config(paths.config_path)
    ds_path = (paths.root / path).resolve() if not Path(path).is_absolute() else Path(path)
    try:
        fp = fingerprint_dataset(ds_path, name=name)
    except (FileNotFoundError, ValueError) as exc:
        render.error(str(exc))
        raise typer.Exit(code=2) from exc

    engine = init_db(paths.db_path)
    with session_scope(engine) as session:
        project = get_or_create_project(session, cfg.name, str(paths.root))
        snapshot = register_snapshot(session, project, fp)
        snapshot_id = snapshot.id

    render.step_ok(f"Registered dataset '{fp.name}'")
    render.console.print(f"  SHA256: {fp.sha256}")
    render.console.print(f"  Size: {fp.size_bytes} bytes")
    if fp.row_count is not None:
        render.console.print(f"  Rows: {fp.row_count}")
        render.console.print(f"  Columns: {', '.join(fp.column_names)}")
    if fp.date_range:
        render.console.print(
            f"  Date range ({fp.date_range['column']}): "
            f"{fp.date_range['min']} → {fp.date_range['max']}"
        )
    render.console.print(f"  Snapshot id: {snapshot_id}")


@dataset_app.command("list")
def dataset_list_cmd() -> None:
    """List registered datasets and their latest snapshot."""
    paths = _resolve_or_exit()
    cfg = config_mod.read_config(paths.config_path)
    engine = init_db(paths.db_path)
    with session_scope(engine) as session:
        project = get_or_create_project(session, cfg.name, str(paths.root))
        datasets = list_datasets(session, project)
        if not datasets:
            render.console.print("No datasets registered. Run 'frpx dataset add <path>'.")
            return
        for ds in datasets:
            snap = latest_snapshot(session, ds)
            sha = snap.sha256[:12] if snap else "-"
            rows = snap.row_count if snap and snap.row_count is not None else "-"
            render.console.print(
                f"[cyan]{ds.name}[/cyan]  {sha}…  rows={rows}  [dim]{ds.canonical_path}[/dim]"
            )


def main() -> None:  # pragma: no cover - console_script shim
    app()


if __name__ == "__main__":  # pragma: no cover
    sys.exit(app())  # type: ignore[func-returns-value]