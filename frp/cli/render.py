"""Rich-based rendering helpers for the FRP CLI."""

from __future__ import annotations

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from frp.diff.dataset_diff import DatasetDiff
from frp.diff.experiment_diff import ExperimentDiff
from frp.models import Experiment
from frp.reproduction.compare import ReproductionReport

console = Console()


def step_ok(message: str) -> None:
    console.print(f"[green]\u2713[/green] {message}")


def step_warn(message: str) -> None:
    console.print(f"[yellow]\u26a0[/yellow] {message}")


def step_fail(message: str) -> None:
    console.print(f"[red]\u2717[/red] {message}")


def error(message: str) -> None:
    console.print(f"[bold red]error:[/bold red] {message}")


def _fmt_metric(key: str, value: float) -> str:
    key_l = key.lower()
    if "drawdown" in key_l or "cagr" in key_l or "return" in key_l or key_l.endswith("_pct"):
        return f"{value * 100:.1f}%"
    return f"{value:.4g}"


def render_run_summary(experiment: Experiment) -> None:
    lines = [f"[bold]Experiment:[/bold] {experiment.id}"]
    if experiment.git_commit and experiment.git_commit.commit_sha:
        sha = experiment.git_commit.commit_sha[:8]
        dirty = " [yellow](dirty)[/yellow]" if experiment.git_commit.dirty else ""
        lines.append(f"[bold]Git commit:[/bold] {sha}{dirty}")
    lines.append(f"[bold]Duration:[/bold] {experiment.duration_ms} ms")
    if experiment.metrics:
        lines.append("")
        for metric in sorted(experiment.metrics, key=lambda m: m.key):
            lines.append(f"[cyan]{metric.key}[/cyan]: {_fmt_metric(metric.key, metric.value)}")
    lines.append("")
    lines.append(f"Run [bold]frpx show {experiment.id}[/bold] to inspect the experiment.")
    console.print(Panel("\n".join(lines), title="FRP Experiment", border_style="green"))


def render_experiment_table(experiments: list[Experiment]) -> None:
    table = Table(title="Experiments")
    table.add_column("ID", style="cyan", no_wrap=True)
    table.add_column("Started")
    table.add_column("Commit")
    table.add_column("Status")
    table.add_column("Key metrics")

    for exp in experiments:
        gc = exp.git_commit
        commit = gc.commit_sha[:8] if gc is not None and gc.commit_sha else "-"
        started = exp.started_at.strftime("%Y-%m-%d %H:%M") if exp.started_at else "-"
        status_style = "green" if exp.status == "completed" else "red"
        metrics = ", ".join(
            f"{m.key}={_fmt_metric(m.key, m.value)}"
            for m in sorted(exp.metrics, key=lambda m: m.key)[:3]
        )
        table.add_row(
            exp.id,
            started,
            commit,
            f"[{status_style}]{exp.status}[/{status_style}]",
            metrics or "-",
        )
    console.print(table)


def render_experiment_detail(experiment: Experiment) -> None:
    console.print(Panel(f"[bold]{experiment.id}[/bold]", border_style="cyan"))

    console.print("[bold]CODE[/bold]")
    if experiment.git_commit:
        gc = experiment.git_commit
        console.print(f"  Git commit: {gc.commit_sha or '-'}")
        console.print(f"  Branch: {gc.branch or '-'}")
        console.print(f"  Dirty: {gc.dirty}")
    else:
        console.print("  (not a git repository)")

    console.print("\n[bold]ENVIRONMENT[/bold]")
    if experiment.environment:
        env = experiment.environment
        console.print(f"  Python: {env.python_version}")
        console.print(f"  Platform: {env.platform}")
        console.print(f"  Dependencies: {len(env.dependencies)} captured")

    console.print("\n[bold]PARAMETERS[/bold]")
    if experiment.parameters:
        for p in sorted(experiment.parameters, key=lambda p: p.key):
            console.print(f"  {p.key} = {p.value}  [dim]({p.type}, {p.source})[/dim]")
    else:
        console.print("  (none)")

    console.print("\n[bold]EXECUTION[/bold]")
    console.print(f"  Command: {experiment.command}")
    console.print(f"  Started: {experiment.started_at}")
    console.print(f"  Duration: {experiment.duration_ms} ms")
    console.print(f"  Exit code: {experiment.exit_code}")

    console.print("\n[bold]OUTPUTS[/bold]")
    if experiment.artifacts:
        for a in sorted(experiment.artifacts, key=lambda a: a.rel_path):
            console.print(f"  {a.rel_path}  [dim]{a.sha256[:12]}… ({a.size_bytes} bytes)[/dim]")
    else:
        console.print("  (none)")

    console.print("\n[bold]RESULTS[/bold]")
    if experiment.metrics:
        for m in sorted(experiment.metrics, key=lambda m: m.key):
            console.print(f"  {m.key}: {_fmt_metric(m.key, m.value)}")
    else:
        console.print("  (no metrics detected)")

    console.print(f"\n[dim]content_hash: {experiment.content_hash}[/dim]")


def render_reproduction_report(report: ReproductionReport) -> None:
    console.print(
        f"[bold]Reproducing[/bold] {report.experiment_id} "
        f"→ new experiment {report.reproduced_id}\n"
    )

    console.print("[bold]INPUTS[/bold]")
    if report.input_differences:
        for diff in report.input_differences:
            console.print(f"  [yellow]⚠[/yellow] {diff.category}: {diff.detail}")
    else:
        console.print("  [green]✓[/green] All known inputs match")

    console.print("\n[bold]RESULTS[/bold]")
    if not report.metric_deltas:
        console.print("  [dim](no metrics to compare)[/dim]")
    for d in report.metric_deltas:
        orig = f"{d.original:.6g}" if d.original is not None else "-"
        repro = f"{d.reproduced:.6g}" if d.reproduced is not None else "-"
        mark = "[green]✓[/green]" if d.within_tolerance else "[yellow]⚠[/yellow]"
        arrow = "=" if d.within_tolerance else "→"
        console.print(f"  {mark} {d.key}: {orig} {arrow} {repro}")

    console.print()
    if report.reproduced:
        console.print("[bold green]✓ REPRODUCED[/bold green]")
    else:
        console.print("[bold yellow]⚠ REPRODUCTION DIFFERENCE[/bold yellow]")
        if report.input_differences:
            console.print(
                "[dim]Known input differences may explain the change (see INPUTS above).[/dim]"
            )
        else:
            console.print(
                "[dim]Inputs matched but results differ — the experiment may be "
                "non-deterministic (unseeded randomness, time, threading).[/dim]"
            )


def _fc_line(label: str, a: str | None, b: str | None, changed: bool) -> None:
    a_s = a if a is not None else "-"
    b_s = b if b is not None else "-"
    if changed:
        console.print(f"  [yellow]⚠[/yellow] {label}: {a_s} → {b_s}")
    else:
        console.print(f"  [green]✓[/green] {label}: {a_s}")


def render_experiment_diff(diff: ExperimentDiff) -> None:
    console.print(
        f"[bold]Diff[/bold] {diff.experiment_a} → {diff.experiment_b}\n"
    )

    console.print("[bold]CODE[/bold]")
    for c in diff.code:
        short_a = c.a[:8] if c.a else None
        short_b = c.b[:8] if c.b else None
        _fc_line(c.key, short_a, short_b, c.changed)

    console.print("\n[bold]DATA[/bold]")
    if diff.data:
        for c in diff.data:
            if c.changed:
                console.print(f"  [yellow]⚠[/yellow] {c.key} changed")
            else:
                console.print(f"  [green]✓[/green] {c.key} unchanged")
    else:
        console.print("  [dim](no declared input datasets)[/dim]")

    console.print("\n[bold]PARAMETERS[/bold]")
    if diff.parameters:
        for c in diff.parameters:
            _fc_line(c.key, c.a, c.b, c.changed)
    else:
        console.print("  [dim](none)[/dim]")

    console.print("\n[bold]ENVIRONMENT[/bold]")
    for c in diff.environment:
        short_a = c.a[:12] if c.a and c.key.endswith("hash") else c.a
        short_b = c.b[:12] if c.b and c.key.endswith("hash") else c.b
        _fc_line(c.key, short_a, short_b, c.changed)

    console.print("\n[bold]RESULTS[/bold]")
    if diff.metrics:
        for m in diff.metrics:
            a_s = f"{m.a:.6g}" if m.a is not None else "-"
            b_s = f"{m.b:.6g}" if m.b is not None else "-"
            if m.changed:
                console.print(f"  [yellow]⚠[/yellow] {m.key}: {a_s} → {b_s}")
            else:
                console.print(f"  [green]✓[/green] {m.key}: {a_s}")
    else:
        console.print("  [dim](no metrics)[/dim]")

    console.print()
    if diff.any_change:
        console.print("[bold yellow]Experiments differ.[/bold yellow]")
    else:
        console.print("[bold green]Experiments are identical across tracked fields.[/bold green]")


def render_dataset_diff(diff: DatasetDiff) -> None:
    console.print(f"[bold]Dataset diff[/bold] {diff.name_a} → {diff.name_b}\n")

    if diff.identical:
        console.print("[green]✓[/green] Identical content (same SHA-256)")
        return

    console.print("[bold]ROWS[/bold]")
    delta = diff.row_count_delta
    delta_s = f" ({delta:+d})" if delta is not None else ""
    console.print(f"  {diff.row_count_a} → {diff.row_count_b}{delta_s}")

    console.print("\n[bold]SCHEMA[/bold]")
    if diff.added_columns:
        console.print(f"  [green]+[/green] added: {', '.join(diff.added_columns)}")
    if diff.removed_columns:
        console.print(f"  [red]-[/red] removed: {', '.join(diff.removed_columns)}")
    for col, ta, tb in diff.dtype_changes:
        console.print(f"  [yellow]⚠[/yellow] {col}: {ta} → {tb}")
    if not diff.schema_changed:
        console.print("  [green]✓[/green] unchanged")

    console.print("\n[bold]DATE RANGE[/bold]")
    console.print(f"  a: {diff.date_range_a or '-'}")
    console.print(f"  b: {diff.date_range_b or '-'}")


def render_validation(results: list) -> None:  # list[CheckResult]
    marks = {"info": "[green]✓[/green]", "warning": "[yellow]⚠[/yellow]", "error": "[red]✗[/red]"}
    for r in results:
        mark = marks.get(r.severity, "•")
        console.print(f"  {mark} {r.check_name}: {r.detail}")
    errors = sum(1 for r in results if r.severity == "error" and not r.passed)
    warnings = sum(1 for r in results if r.severity == "warning" and not r.passed)
    console.print()
    if errors:
        console.print(f"[bold red]{errors} error(s), {warnings} warning(s)[/bold red]")
    elif warnings:
        console.print(f"[bold yellow]{warnings} warning(s)[/bold yellow]")
    else:
        console.print("[bold green]All checks passed.[/bold green]")


def render_lookahead(warnings: list) -> None:  # list[LookAheadWarning]
    for w in warnings:
        console.print(
            f"  [yellow]⚠[/yellow] {w.dataset}: publication {w.publication_date} "
            f"> backtest {w.backtest_date}"
        )
        console.print(f"    [dim]{w.message}[/dim]")
