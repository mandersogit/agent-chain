"""Command-line interface for agent-chain."""

import datetime as _datetime
import pathlib as _pathlib
import sys as _sys

import click as _click  # pyright: ignore[reportMissingImports]

import agent_chain as _agent_chain
import agent_chain.backends as _backends
import agent_chain.chain as _chain
import agent_chain.report as _report
import agent_chain.runner as _runner
import agent_chain.types as _types


def _parse_var(
    ctx: _click.Context, param: _click.Parameter, value: tuple[str, ...]
) -> dict[str, str]:
    """Parse repeated --var KEY=VALUE options into a dict.

    Args:
        ctx: Click context (unused).
        param: Click parameter (unused).
        value: Tuple of KEY=VALUE strings from --var flags.

    Returns:
        Dictionary mapping variable names to values.

    Raises:
        BadParameter: If any item does not contain an '=' separator.
    """
    result: dict[str, str] = {}
    for item in value:
        if "=" not in item:
            raise _click.BadParameter(f"Expected KEY=VALUE, got {item!r}")
        key, val = item.split("=", 1)
        result[key] = val
    return result


@_click.group()
@_click.version_option(version=_agent_chain.__version__, prog_name="agent-chain")
def main() -> None:
    """Multi-agent chain orchestration CLI."""


@main.command()  # pyright: ignore[reportFunctionMemberAccess]
@_click.argument("chain_file", type=_click.Path(exists=True))
@_click.option("-o", "--output-dir", type=_click.Path(), default=None,
               help="Output directory for step results and report.")
@_click.option("-v", "--verbose", is_flag=True, default=False,
               help="Print step progress to stderr.")
@_click.option("--dry-run", is_flag=True, default=False,
               help="Print what would be executed without launching agents.")
@_click.option("--timeout", type=int, default=_types.DEFAULT_STEP_TIMEOUT,
               help=f"Per-step timeout in seconds (default: {_types.DEFAULT_STEP_TIMEOUT}).")
@_click.option("--start-from", type=str, default=None,
               help="Skip steps before the named step and start execution there.")
@_click.option("--var", multiple=True, callback=_parse_var, expose_value=True,
               help="Set a template variable (KEY=VALUE). Repeatable.")
def run(
    chain_file: str,
    output_dir: str | None,
    verbose: bool,
    dry_run: bool,
    timeout: int,
    start_from: str | None,
    var: dict[str, str],
) -> None:
    """Run a chain definition file."""
    chain_path = _pathlib.Path(chain_file)

    try:
        chain_def = _chain.load(chain_path)
    except _chain.ValidationError as exc:
        _click.echo(f"Error: {exc}", err=True)
        _sys.exit(1)

    validation = _chain.validate(
        chain_def, var, known_backends=_backends.known_backend_names()
    )
    if not validation.ok:
        for err in validation.errors:
            _click.echo(f"Validation error: {err}", err=True)
        _sys.exit(1)
    for warn in validation.warnings:
        _click.echo(f"Warning: {warn}", err=True)

    if output_dir is None:
        timestamp = _datetime.datetime.now().strftime("%Y%m%dT%H%M%S")
        resolved_output_dir = _pathlib.Path(f".agent-chain/{chain_def.name}-{timestamp}")
    else:
        resolved_output_dir = _pathlib.Path(output_dir)

    if chain_def.working_dir is not None:
        working_dir = _pathlib.Path(chain_def.working_dir).resolve()
    else:
        working_dir = chain_path.parent.resolve()

    runner = _runner.ChainRunner(
        chain_def=chain_def,
        output_dir=resolved_output_dir,
        working_dir=working_dir,
        cli_vars=var,
        global_timeout=timeout,
        verbose=verbose,
        dry_run=dry_run,
        start_from=start_from,
    )

    results = runner.run()

    if dry_run:
        _sys.exit(0)

    chain_status = _types.ChainStatus.SUCCESS
    for r in results:
        if r.status == _types.StepStatus.INTERRUPTED:
            chain_status = _types.ChainStatus.INTERRUPTED
            break
        if r.status in (_types.StepStatus.FAILED, _types.StepStatus.TIMEOUT,
                        _types.StepStatus.CRASHED, _types.StepStatus.CONFIG_ERROR):
            chain_status = _types.ChainStatus.FAILED
            break
        if r.status == _types.StepStatus.GATE_FAILED:
            chain_status = _types.ChainStatus.GATE_FAILED
            break

    _click.echo(f"Chain completed: {chain_status.value}")
    _click.echo(f"Report: {resolved_output_dir / 'report.json'}")

    if chain_status != _types.ChainStatus.SUCCESS:
        _sys.exit(1)


@main.command()  # pyright: ignore[reportFunctionMemberAccess]
@_click.argument("chain_file", type=_click.Path(exists=True))
@_click.option("--strict", is_flag=True, default=False,
               help="Fail on warnings (missing optional fields, unused variables).")
@_click.option("--var", multiple=True, callback=_parse_var, expose_value=True,
               help="Provide variables for template validation (KEY=VALUE).")
def validate(chain_file: str, strict: bool, var: dict[str, str]) -> None:
    """Validate a chain definition file."""
    chain_path = _pathlib.Path(chain_file)

    try:
        chain_def = _chain.load(chain_path)
    except _chain.ValidationError as exc:
        _click.echo(f"Error: {exc}", err=True)
        _sys.exit(1)

    result = _chain.validate(
        chain_def, var, known_backends=_backends.known_backend_names()
    )

    for err in result.errors:
        _click.echo(f"Error: {err}", err=True)
    for warn in result.warnings:
        _click.echo(f"Warning: {warn}", err=True)

    if not result.ok:
        _sys.exit(1)

    if strict and result.warnings:
        _click.echo("Strict mode: warnings treated as errors", err=True)
        _sys.exit(1)

    _click.echo(f"Valid: {chain_def.name} ({len(chain_def.steps)} steps)")


@main.command()  # pyright: ignore[reportFunctionMemberAccess]
@_click.argument("output_dir", type=_click.Path(exists=True))
@_click.option("--format", "output_format", type=_click.Choice(["text", "json", "markdown"]),
               default="text", help="Output format (default: text).")
@_click.option("--include-telemetry", is_flag=True, default=False,
               help="Include per-step token breakdowns.")
def report(output_dir: str, output_format: str, include_telemetry: bool) -> None:
    """Display a report from chain run output."""
    report_path = _pathlib.Path(output_dir) / "report.json"

    if not report_path.exists():
        _click.echo(f"Error: {report_path} not found", err=True)
        _sys.exit(1)

    rendered = _report.render_report(
        report_path, output_format=output_format, include_telemetry=include_telemetry
    )
    _click.echo(rendered)
