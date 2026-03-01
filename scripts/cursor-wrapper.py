#!/bin/bash
# -*- mode: python -*-
# vim: set ft=python:
# Polyglot bash/python script - bash delegates to venv python, falls back to system
"true" '''\'
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
if [ -x "$PROJECT_ROOT/local.venv/bin/python" ]; then
    exec "$PROJECT_ROOT/local.venv/bin/python" "$0" "$@"
else
    exec /usr/bin/env python3 "$0" "$@"
fi
'''
"""Wrapper CLI around cursor-agent for robust non-interactive execution."""

# ruff: noqa: E402, UP036 (polyglot script: imports not at top, version guard intentional)

import collections as _collections
import json as _json
import os as _os
import pathlib as _pathlib
import select as _select
import signal as _signal
import shlex as _shlex
import shutil as _shutil
import subprocess as _subprocess
import sys as _sys
import time as _time
import typing as _typing

import click as _click

_WRAPPER_VERSION = "0.1.0"
_STREAM_JSON = "stream-json"
_JSON = "json"
_TEXT = "text"


class _RunOutcome(_typing.NamedTuple):
    """Result of a cursor-agent execution."""

    result_event: dict[str, _typing.Any] | None
    init_event: dict[str, _typing.Any] | None
    num_turns: int
    num_tool_calls: int
    num_thinking_events: int
    elapsed_seconds: float
    timed_out: bool


def _warn(message: str) -> None:
    """Print a warning to stderr."""
    _click.echo(f"cursor-wrapper: warning: {message}", err=True)


def _discover_agent_command() -> tuple[list[str], str]:
    """Discover cursor-agent command prefix.

    Returns:
        Tuple of command prefix and a human-readable description.

    Raises:
        click.ClickException: If no viable command is discovered.
    """
    env_bin = _os.environ.get("CURSOR_WRAPPER_AGENT_BIN")
    if env_bin is not None:
        parts = _shlex.split(env_bin)
        if not parts:
            raise _click.ClickException(
                "CURSOR_WRAPPER_AGENT_BIN is set but empty after shell parsing."
            )
        return parts, f"env override: {env_bin}"

    standalone_path = _shutil.which("cursor-agent")
    if standalone_path:
        return ["cursor-agent"], f"standalone: {standalone_path}"

    cursor_path = _shutil.which("cursor")
    if cursor_path:
        try:
            check_result = _subprocess.run(
                [cursor_path, "agent", "--version"],
                capture_output=True,
                text=True,
                timeout=3,
            )
            if check_result.returncode == 0:
                return [cursor_path, "agent"], f"subcommand: {cursor_path} agent"
        except (_subprocess.SubprocessError, OSError):
            pass

    raise _click.ClickException(
        "Could not find cursor-agent. Checked CURSOR_WRAPPER_AGENT_BIN, "
        "'cursor-agent' on PATH, and validated 'cursor agent --version'."
    )


def _build_exec_command(
    command_prefix: list[str],
    prompt: str,
    model: str | None,
    mode: str | None,
    force: bool,
    sandbox: str | None,
    workspace: _pathlib.Path,
    max_turns: int | None,
    extra_flags: tuple[str, ...],
) -> list[str]:
    """Build cursor-agent command from wrapper options.

    Args:
        command_prefix: Base command list (e.g. ``["cursor-agent"]``).
        prompt: Prompt text passed as the final positional argument.
        model: Model identifier, or None to omit the flag.
        mode: Execution mode (e.g. "plan", "ask"), or None to omit.
        force: Whether to pass ``--force`` (True) or ``--no-force`` (False).
        sandbox: Sandbox mode string, or None to omit the flag.
        workspace: Resolved workspace directory.
        max_turns: Maximum turn count, or None to omit the flag.
        extra_flags: Raw flag strings, each shell-split before appending.

    Returns:
        Full argv list for subprocess invocation.
    """
    cmd = [*command_prefix, "--output-format", _STREAM_JSON]
    if model:
        cmd.extend(["--model", model])
    if mode:
        cmd.extend(["--mode", mode])
    cmd.append("--force" if force else "--no-force")
    if sandbox:
        cmd.extend(["--sandbox", sandbox])
    # cursor-agent requires CWD to be the workspace directory; --workspace
    # alone is insufficient.  We pass it for belt-and-suspenders but rely on
    # cwd= in _run_and_monitor.
    cmd.extend(["--workspace", str(workspace)])
    if max_turns is not None:
        _warn("--max-turns ignored — cursor-agent does not support this flag.")
    for flag in extra_flags:
        cmd.extend(_shlex.split(flag))
    cmd.extend(["--", prompt])
    return cmd


def _resolve_prompt(prompt_arg: str | None) -> str:
    """Read prompt text from argument or stdin.

    Args:
        prompt_arg: Positional prompt string, ``"-"`` to force stdin,
            or None to auto-detect from tty status.

    Returns:
        Non-empty prompt string.

    Raises:
        click.ClickException: If the prompt is empty or not provided.
    """
    should_read_stdin = prompt_arg == "-" or (prompt_arg is None and not _sys.stdin.isatty())
    if should_read_stdin:
        prompt = _sys.stdin.read()
        if not prompt.strip():
            raise _click.ClickException("Prompt from stdin is empty.")
        return prompt
    if prompt_arg is None:
        raise _click.ClickException("No prompt provided. Pass PROMPT or pipe stdin.")
    return prompt_arg


def _kill(proc: _subprocess.Popen[bytes], wait_seconds: float = 5.0) -> None:
    """Terminate a process group gracefully, then force-kill if it does not exit.

    Sends SIGTERM/SIGKILL to the entire process group so that child
    processes spawned by the cursor agent are not orphaned.

    Args:
        proc: Running subprocess to terminate (must have been started
            with ``start_new_session=True``).
        wait_seconds: Seconds to wait for graceful exit before sending SIGKILL.
    """
    if proc.poll() is not None:
        return
    try:
        pgid = _os.getpgid(proc.pid)
        _os.killpg(pgid, _signal.SIGTERM)
    except (ProcessLookupError, PermissionError):
        proc.terminate()
    try:
        proc.wait(timeout=wait_seconds)
        return
    except _subprocess.TimeoutExpired:
        pass
    if proc.poll() is None:
        try:
            pgid = _os.getpgid(proc.pid)
            _os.killpg(pgid, _signal.SIGKILL)
        except (ProcessLookupError, PermissionError):
            proc.kill()
    try:
        proc.wait(timeout=1.0)
    except _subprocess.TimeoutExpired:
        pass


def _event_label(event: dict[str, _typing.Any]) -> str:
    """Format an event type string for log output.

    Args:
        event: Parsed NDJSON event dict.

    Returns:
        The event type, or ``"type.subtype"`` when a subtype field is present.
    """
    event_type = str(event.get("type", "unknown"))
    subtype = event.get("subtype")
    if subtype is None:
        return event_type
    return f"{event_type}.{subtype}"


def _parse_event(line: str) -> dict[str, _typing.Any] | None:
    """Parse an NDJSON line into an event dict.

    Args:
        line: Single stripped NDJSON line.

    Returns:
        Parsed dict, or None if the line is not valid JSON or not a dict.
    """
    try:
        payload = _json.loads(line)
    except _json.JSONDecodeError:
        return None
    if isinstance(payload, dict):
        return payload
    return None


def _run_and_monitor(
    cmd: list[str],
    workspace: _pathlib.Path,
    output_format: str,
    output_stream: _typing.TextIO,
    timeout_seconds: int,
    verbose: bool,
) -> _RunOutcome:
    """Launch cursor-agent and process its NDJSON output stream.

    Reads stdout line-by-line using ``select.select`` for timeout-aware
    polling and byte-level reads. Returns on the first ``result`` event
    or when the process exits.

    Args:
        cmd: Full argv list for the cursor-agent subprocess.
        workspace: Working directory passed to the subprocess.
        output_format: One of ``stream-json``, ``json``, or ``text``.
            Only ``stream-json`` writes events to ``output_stream``
            during monitoring.
        output_stream: Writable text stream for stream-json passthrough.
        timeout_seconds: Hard wall-clock deadline in seconds; 0 disables.
        verbose: When True, log each event label to stderr.

    Returns:
        ``_RunOutcome`` summarising the execution.
    """
    proc = _subprocess.Popen(
        cmd,
        stdin=_subprocess.DEVNULL,
        stdout=_subprocess.PIPE,
        stderr=_sys.stderr,
        cwd=workspace,
        start_new_session=True,
    )
    if proc.stdout is None:
        raise _click.ClickException("Failed to capture cursor-agent stdout.")

    try:
        fd = proc.stdout.fileno()
        buffer = b""
        start = _time.monotonic()
        deadline = start + timeout_seconds if timeout_seconds > 0 else None
        events = _collections.deque[dict[str, _typing.Any]](maxlen=200)
        result_event: dict[str, _typing.Any] | None = None
        init_event: dict[str, _typing.Any] | None = None
        num_turns = 0
        num_tool_calls = 0
        num_thinking_events = 0

        while True:
            if deadline is not None:
                remaining = deadline - _time.monotonic()
                if remaining <= 0:
                    _kill(proc)
                    return _RunOutcome(
                        result_event=None,
                        init_event=init_event,
                        num_turns=num_turns,
                        num_tool_calls=num_tool_calls,
                        num_thinking_events=num_thinking_events,
                        elapsed_seconds=_time.monotonic() - start,
                        timed_out=True,
                    )
                poll_timeout = min(remaining, 5.0)
            else:
                poll_timeout = 5.0

            ready, _, _ = _select.select([fd], [], [], poll_timeout)
            if not ready:
                if proc.poll() is not None:
                    break
                continue

            chunk = _os.read(fd, 65536)
            if not chunk:
                break

            buffer += chunk
            while b"\n" in buffer:
                line, buffer = buffer.split(b"\n", 1)
                decoded = line.decode("utf-8", errors="replace").strip()
                if not decoded:
                    continue

                if output_format == _STREAM_JSON:
                    output_stream.write(decoded + "\n")
                    output_stream.flush()

                event = _parse_event(decoded)
                if event is None:
                    continue

                events.append(event)
                if verbose:
                    elapsed = _time.monotonic() - start
                    _click.echo(
                        f"cursor-wrapper: [{elapsed:.1f}s] {_event_label(event)}",
                        err=True,
                    )

                event_type = event.get("type")
                subtype = event.get("subtype")
                if event_type == "system" and subtype == "init" and init_event is None:
                    init_event = event
                if event_type == "assistant":
                    num_turns += 1
                if event_type == "thinking":
                    num_thinking_events += 1
                if event_type == "tool_call" and subtype == "started":
                    num_tool_calls += 1
                if event_type == "result":
                    result_event = event
                    _kill(proc)
                    return _RunOutcome(
                        result_event=result_event,
                        init_event=init_event,
                        num_turns=num_turns,
                        num_tool_calls=num_tool_calls,
                        num_thinking_events=num_thinking_events,
                        elapsed_seconds=_time.monotonic() - start,
                        timed_out=False,
                    )

        if buffer.strip():
            decoded = buffer.decode("utf-8", errors="replace").strip()
            if decoded and output_format == _STREAM_JSON:
                output_stream.write(decoded + "\n")
                output_stream.flush()
            event = _parse_event(decoded)
            if event is not None and event.get("type") == "result":
                result_event = event

        _kill(proc, wait_seconds=0.1)
        return _RunOutcome(
            result_event=result_event,
            init_event=init_event,
            num_turns=num_turns,
            num_tool_calls=num_tool_calls,
            num_thinking_events=num_thinking_events,
            elapsed_seconds=_time.monotonic() - start,
            timed_out=False,
        )
    finally:
        proc.stdout.close()


def _emit_result(
    output_format: str,
    output_stream: _typing.TextIO,
    run_outcome: _RunOutcome,
) -> None:
    """Write final output for ``json`` or ``text`` format modes.

    Does nothing for ``stream-json`` (events were already streamed) or
    when no result event was captured.

    Args:
        output_format: One of ``stream-json``, ``json``, or ``text``.
        output_stream: Writable text stream to emit the result to.
        run_outcome: Completed run outcome containing event data.
    """
    result_event = run_outcome.result_event
    if output_format == _STREAM_JSON or result_event is None:
        return

    if output_format == _TEXT:
        result_text = str(result_event.get("result", ""))
        output_stream.write(result_text)
        if not result_text.endswith("\n"):
            output_stream.write("\n")
        output_stream.flush()
        return

    init_event = run_outcome.init_event or {}
    summary = {
        "result": result_event.get("result", ""),
        "model": init_event.get("model"),
        "session_id": init_event.get("session_id"),
        "request_id": result_event.get("request_id"),
        "duration_ms": result_event.get("duration_ms"),
        "duration_api_ms": result_event.get("duration_api_ms"),
        "num_turns": run_outcome.num_turns,
        "num_tool_calls": run_outcome.num_tool_calls,
        "num_thinking_events": run_outcome.num_thinking_events,
        "is_error": bool(result_event.get("is_error", False)),
        "input_tokens": 0,
        "output_tokens": 0,
        "shadow_cost_usd": None,
    }
    output_stream.write(_json.dumps(summary))
    output_stream.write("\n")
    output_stream.flush()


def _result_exit_code(result_event: dict[str, _typing.Any] | None) -> int:
    """Derive the wrapper process exit code from a result event.

    Args:
        result_event: Parsed result event dict, or None if not received.

    Returns:
        0 on success, 1 on error or missing event.
    """
    if result_event is None:
        return 1
    if bool(result_event.get("is_error", False)):
        return 1
    if str(result_event.get("subtype", "")) == "failure":
        return 1
    return 0


@_click.group()
def main() -> None:
    """cursor-wrapper CLI."""


@main.command(name="exec")
@_click.option("--model", type=str, default=None, help="Model identifier.")
@_click.option("--mode", type=str, default=None, help="Execution mode (plan, ask).")
@_click.option("--force/--no-force", default=True, help="Allow file modifications.")
@_click.option("--sandbox", type=str, default=None, help="Sandbox mode.")
@_click.option(
    "--workspace",
    type=_click.Path(file_okay=False, dir_okay=True, path_type=_pathlib.Path),
    default=_pathlib.Path("."),
    show_default=True,
    help="Workspace directory.",
)
@_click.option("--max-turns", type=int, default=None, help="Maximum agent turns.")
@_click.option(
    "--output-format",
    type=_click.Choice([_STREAM_JSON, _JSON, _TEXT], case_sensitive=False),
    default=_STREAM_JSON,
    show_default=True,
    help="Wrapper output format.",
)
@_click.option(
    "--timeout",
    type=int,
    default=0,
    show_default=True,
    help="Hard wall-clock timeout in seconds (0 = no limit).",
)
@_click.option(
    "--extra-flag",
    type=str,
    multiple=True,
    help="Additional flags passed through to cursor-agent.",
)
@_click.option(
    "-o",
    "--output",
    type=_click.Path(dir_okay=False, path_type=_pathlib.Path),
    default=None,
    help="Write output to file instead of stdout.",
)
@_click.option("-v", "--verbose", is_flag=True, help="Print progress to stderr.")
@_click.argument("prompt", required=False)
def exec_command(
    model: str | None,
    mode: str | None,
    force: bool,
    sandbox: str | None,
    workspace: _pathlib.Path,
    max_turns: int | None,
    output_format: str,
    timeout: int,
    extra_flag: tuple[str, ...],
    output: _pathlib.Path | None,
    verbose: bool,
    prompt: str | None,
) -> None:
    """Run cursor-agent in headless mode."""
    if timeout < 0:
        raise _click.ClickException("--timeout must be >= 0.")

    prompt_text = _resolve_prompt(prompt)
    workspace = workspace.resolve()

    if force and mode in {"plan", "ask"}:
        _warn("--force has no effect with read-only modes (--mode plan/ask).")
    if (not force) and mode is None:
        _warn(
            "--no-force without --mode may hang in headless mode "
            "(cursor-agent can wait for confirmations)."
        )
    if (not force) and mode == "ask":
        _warn(
            "--no-force with --mode ask may trigger workspace trust prompts "
            "even for previously trusted directories."
        )

    command_prefix, description = _discover_agent_command()
    cmd = _build_exec_command(
        command_prefix=command_prefix,
        prompt=prompt_text,
        model=model,
        mode=mode,
        force=force,
        sandbox=sandbox,
        workspace=workspace,
        max_turns=max_turns,
        extra_flags=extra_flag,
    )

    if verbose:
        _click.echo(f"cursor-wrapper: using {description}", err=True)
        redacted_cmd = [*cmd[:-1], "<prompt>"]
        _click.echo(f"cursor-wrapper: {' '.join(_shlex.quote(part) for part in redacted_cmd)}", err=True)

    out_stream: _typing.TextIO
    out_handle: _typing.TextIO | None = None
    if output is None:
        out_stream = _sys.stdout
    elif output_format == _STREAM_JSON:
        # Open file now so events are streamed directly during monitoring.
        output.parent.mkdir(parents=True, exist_ok=True)
        out_handle = output.open("w", encoding="utf-8")
        out_stream = out_handle
    else:
        # json/text: result is written after monitoring completes;
        # nothing is written to output_stream during monitoring.
        out_stream = _sys.stdout

    try:
        outcome = _run_and_monitor(
            cmd=cmd,
            workspace=workspace,
            output_format=output_format,
            output_stream=out_stream,
            timeout_seconds=timeout,
            verbose=verbose,
        )
    except KeyboardInterrupt:
        _click.echo("cursor-wrapper: interrupted by keyboard", err=True)
        raise _click.exceptions.Exit(130) from None
    finally:
        if out_handle is not None:
            out_handle.close()

    if outcome.timed_out:
        _click.echo(
            f"cursor-wrapper: timeout after {outcome.elapsed_seconds:.1f}s",
            err=True,
        )
        raise _click.exceptions.Exit(124)

    if outcome.result_event is None:
        _click.echo(
            f"cursor-wrapper: no result event received after {outcome.elapsed_seconds:.1f}s",
            err=True,
        )
        raise _click.exceptions.Exit(1)

    if output_format in {_JSON, _TEXT}:
        if output is None:
            _emit_result(output_format=output_format, output_stream=_sys.stdout, run_outcome=outcome)
        else:
            output.parent.mkdir(parents=True, exist_ok=True)
            with output.open("w", encoding="utf-8") as f:
                _emit_result(output_format=output_format, output_stream=f, run_outcome=outcome)

    if verbose:
        _click.echo(
            "cursor-wrapper: done in "
            f"{outcome.elapsed_seconds:.1f}s — {outcome.num_turns} turns, "
            f"{outcome.num_tool_calls} tool calls, {outcome.num_thinking_events} thinking events",
            err=True,
        )

    raise _click.exceptions.Exit(_result_exit_code(outcome.result_event))


@main.command()
def models() -> None:
    """List available cursor-agent models."""
    command_prefix, _ = _discover_agent_command()
    cmd = [*command_prefix, "--list-models"]
    result = _subprocess.run(cmd)
    raise _click.exceptions.Exit(result.returncode)


@main.command()
def version() -> None:
    """Print wrapper and cursor-agent versions."""
    _click.echo(f"cursor-wrapper {_WRAPPER_VERSION}")
    command_prefix, description = _discover_agent_command()
    try:
        result = _subprocess.run(
            [*command_prefix, "--version"],
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (_subprocess.SubprocessError, OSError) as exc:
        raise _click.ClickException(f"Failed to query cursor-agent version: {exc}") from exc
    if result.returncode != 0:
        raise _click.ClickException(
            f"Failed to query cursor-agent version: {result.stderr.strip() or 'unknown error'}"
        )
    version_text = result.stdout.strip() or result.stderr.strip() or "unknown"
    _click.echo(f"cursor-agent ({description}): {version_text}")


if __name__ == "__main__":
    main()
