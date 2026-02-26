"""Completion report generation and sentinel file writing."""

from __future__ import annotations

import datetime as _datetime
import json as _json
import pathlib as _pathlib
import typing as _typing

import agent_chain.chain as _chain
import agent_chain.telemetry as _telemetry
import agent_chain.types as _types

if _typing.TYPE_CHECKING:
    import agent_chain.runner as _runner

_SCHEMA_VERSION = 1


def _classify_chain_status(
    results: list[_runner.StepResult],
) -> _types.ChainStatus:
    """Determine the overall chain status from step results.

    Args:
        results: List of completed step results.

    Returns:
        The overall ``ChainStatus`` based on step outcomes.
    """
    has_warnings = False
    for r in results:
        if r.status == _types.StepStatus.INTERRUPTED:
            return _types.ChainStatus.INTERRUPTED
        if r.status == _types.StepStatus.GATE_FAILED:
            on_failure = (
                r.gate_result.get("on_failure") if r.gate_result else None
            )
            if on_failure == "warn":
                has_warnings = True
            else:
                return _types.ChainStatus.GATE_FAILED
        if r.status in (
            _types.StepStatus.FAILED,
            _types.StepStatus.TIMEOUT,
            _types.StepStatus.CRASHED,
            _types.StepStatus.CONFIG_ERROR,
        ):
            return _types.ChainStatus.FAILED

    if has_warnings:
        return _types.ChainStatus.SUCCESS_WARNINGS
    return _types.ChainStatus.SUCCESS


def _relative_path(
    path: _pathlib.Path | None, output_dir: _pathlib.Path
) -> str | None:
    """Make a path relative to the output directory, or return None.

    Args:
        path: Path to make relative, or None.
        output_dir: Base directory for relative path calculation.

    Returns:
        Relative path as string, absolute path as fallback, or None if input is None.
    """
    if path is None:
        return None
    try:
        return str(path.relative_to(output_dir))
    except ValueError:
        return str(path)


def _build_step_dict(
    result: _runner.StepResult, output_dir: _pathlib.Path
) -> dict[str, object]:
    """Build the JSON-serializable dict for a single step result.

    Args:
        result: Completed step result to serialize.
        output_dir: Base directory for relative path conversion.

    Returns:
        Dictionary with step metadata, status, telemetry, and gate results.
    """
    step: dict[str, object] = {
        "name": result.name,
        "type": result.step_type,
        "agent": result.agent,
        "status": result.status.value,
        "wall_time_seconds": result.wall_time_seconds,
        "output_path": _relative_path(result.output_path, output_dir),
        "telemetry_path": _relative_path(result.telemetry_path, output_dir),
        "telemetry": dict(result.telemetry) if result.telemetry else None,
        "gate": result.gate_result,
        "exit_code": result.exit_code,
    }
    return step


def build_report(
    chain_def: _chain.ChainDefinition,
    output_dir: _pathlib.Path,
    started_at: _datetime.datetime,
    finished_at: _datetime.datetime,
    results: list[_runner.StepResult],
) -> dict[str, object]:
    """Build the full completion report as a dict.

    Args:
        chain_def: The chain definition that was executed.
        output_dir: The chain output directory.
        started_at: UTC timestamp when execution started.
        finished_at: UTC timestamp when execution finished.
        results: List of step results.

    Returns:
        A JSON-serializable report dict.
    """
    chain_status = _classify_chain_status(results)

    agg = _telemetry.AggregatedTelemetry()
    steps_completed = 0
    steps_failed = 0
    steps_skipped = 0

    step_dicts: list[dict[str, object]] = []
    for r in results:
        step_dicts.append(_build_step_dict(r, output_dir))
        if r.telemetry is not None:
            agg.add(r.telemetry)
        if r.status == _types.StepStatus.SUCCESS or r.status == _types.StepStatus.GATE_FAILED:
            steps_completed += 1
        elif r.status == _types.StepStatus.NOT_STARTED or r.status == _types.StepStatus.SKIPPED:
            steps_skipped += 1
        else:
            if r.status not in (_types.StepStatus.NOT_STARTED, _types.StepStatus.SKIPPED):
                steps_failed += 1

    totals = agg.totals()
    totals["steps_completed"] = steps_completed
    totals["steps_failed"] = steps_failed
    totals["steps_skipped"] = steps_skipped

    status_detail: str | None = None
    for r in results:
        if r.status not in (_types.StepStatus.SUCCESS, _types.StepStatus.NOT_STARTED,
                            _types.StepStatus.SKIPPED):
            status_detail = f"Step {r.name!r} {r.status.value}"
            break

    return {
        "schema_version": _SCHEMA_VERSION,
        "chain": {
            "name": chain_def.name,
            "definition_path": str(chain_def.source_path),
            "output_dir": str(output_dir.resolve()),
            "started_at": started_at.isoformat(),
            "finished_at": finished_at.isoformat(),
            "status": chain_status.value,
            "status_detail": status_detail,
        },
        "steps": step_dicts,
        "totals": totals,
    }


def write_report(
    chain_def: _chain.ChainDefinition,
    output_dir: _pathlib.Path,
    started_at: _datetime.datetime,
    finished_at: _datetime.datetime,
    results: list[_runner.StepResult],
) -> _pathlib.Path:
    """Write the completion report and sentinel file.

    Args:
        chain_def: The chain definition that was executed.
        output_dir: The chain output directory.
        started_at: UTC timestamp when execution started.
        finished_at: UTC timestamp when execution finished.
        results: List of step results.

    Returns:
        Path to the written report.json file.
    """
    report_data = build_report(chain_def, output_dir, started_at, finished_at, results)

    report_path = output_dir / "report.json"
    report_path.write_text(_json.dumps(report_data, indent=2) + "\n")

    chain_status = _classify_chain_status(results)
    sentinel_path = output_dir / "DONE"
    sentinel_path.write_text(chain_status.value + "\n")

    return report_path


def render_report(
    report_path: _pathlib.Path,
    output_format: str = "text",
    include_telemetry: bool = False,
) -> str:
    """Render a saved report.json for display.

    Args:
        report_path: Path to the report.json file.
        output_format: One of "text", "json", or "markdown".
        include_telemetry: Whether to include per-step telemetry details.

    Returns:
        Formatted report string.
    """
    data = _json.loads(report_path.read_text())

    if output_format == "json":
        if not include_telemetry:
            for step in data.get("steps", []):
                step.pop("telemetry", None)
        return _json.dumps(data, indent=2)

    chain_info = data.get("chain", {})
    totals = data.get("totals", {})
    steps = data.get("steps", [])

    lines: list[str] = []

    if output_format == "markdown":
        lines.append(f"# Chain Report: {chain_info.get('name', 'unknown')}")
    else:
        lines.append(f"Chain: {chain_info.get('name', 'unknown')}")

    lines.append(f"Status: {chain_info.get('status', 'unknown')}")
    if chain_info.get("status_detail"):
        lines.append(f"Detail: {chain_info['status_detail']}")
    lines.append(f"Started: {chain_info.get('started_at', '')}")
    lines.append(f"Finished: {chain_info.get('finished_at', '')}")
    lines.append("")

    if output_format == "markdown":
        lines.append("## Steps")
    else:
        lines.append("Steps:")

    for step in steps:
        status_str = step.get("status", "unknown")
        wall = step.get("wall_time_seconds", 0)
        name = step.get("name", "?")
        lines.append(f"  {name}: {status_str} ({wall:.1f}s)")

        if include_telemetry and step.get("telemetry"):
            t = step["telemetry"]
            t_in = t.get("total_input_tokens", 0)
            t_out = t.get("output_tokens", 0)
            lines.append(f"    Tokens: {t_in} in, {t_out} out")
            lines.append(f"    Turns: {t.get('num_turns', 0)}")
            if t.get("shadow_cost_usd") is not None:
                lines.append(f"    Cost: ${t['shadow_cost_usd']:.2f}")

    lines.append("")
    if output_format == "markdown":
        lines.append("## Totals")
    else:
        lines.append("Totals:")

    lines.append(f"  Input tokens: {totals.get('total_input_tokens', 0)}")
    lines.append(f"  Output tokens: {totals.get('output_tokens', 0)}")
    lines.append(f"  Turns: {totals.get('num_turns', 0)}")
    lines.append(f"  Wall time: {totals.get('wall_time_seconds', 0):.1f}s")
    if totals.get("shadow_cost_usd") is not None:
        lines.append(f"  Cost: ${totals['shadow_cost_usd']:.2f}")
        if totals.get("cost_incomplete"):
            lines.append("  (cost incomplete — some steps lack cost data)")
    lines.append(f"  Steps: {totals.get('steps_completed', 0)} completed, "
                 f"{totals.get('steps_failed', 0)} failed, "
                 f"{totals.get('steps_skipped', 0)} skipped")

    return "\n".join(lines)
