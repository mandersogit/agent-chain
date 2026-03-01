"""cursor-cli agent backend."""

import json as _json
import os as _os
import pathlib as _pathlib
import shutil as _shutil
import sys as _sys

import agent_chain.backends as _backends
import agent_chain.types as _types

_ENV_VAR = "AGENT_CHAIN_CURSOR_BIN"
_BINARY_NAME = "cursor-wrapper"


def _find_command_prefix() -> list[str]:
    """Find the cursor-wrapper command prefix.

    Discovery order is environment variable override, PATH lookup,
    then repository-local fallback script invocation via ``sys.executable``.

    Returns:
        Command prefix argv list.
    """
    env = _os.environ.get(_ENV_VAR)
    if env:
        return [str(_pathlib.Path(env))]

    which = _shutil.which(_BINARY_NAME)
    if which:
        return [str(_pathlib.Path(which))]

    script_path = _pathlib.Path(__file__).resolve().parents[3] / "scripts" / "cursor-wrapper.py"
    return [_sys.executable, str(script_path)]


class CursorCliBackend(_backends.AgentBackend):
    """Backend for Cursor wrapper CLI execution."""

    def __init__(self) -> None:
        self._command_prefix = _find_command_prefix()

    def name(self) -> str:
        """Return this backend's registry name.

        Returns:
            Backend name used in chain step `agent` fields.
        """
        return "cursor-cli"

    def build_command(
        self,
        brief_path: _pathlib.Path,
        step_output_dir: _pathlib.Path,
        working_dir: _pathlib.Path,
        config: _types.StepConfig,
    ) -> list[str]:
        """Build the subprocess command for cursor-wrapper invocation.

        Args:
            brief_path: Path to the step brief file.
            step_output_dir: Output directory for the step.
            working_dir: Working directory for command execution.
            config: Step-level backend configuration.

        Returns:
            Command argv list for launching cursor-wrapper.
        """
        cmd: list[str] = [
            *self._command_prefix,
            "exec",
            "--output-format",
            "stream-json",
            "--workspace",
            str(working_dir),
        ]

        if "model" in config:
            model = config["model"]
            if not isinstance(model, str):
                raise TypeError(f"model must be a string, got {type(model).__name__}")
            cmd += ["--model", model]

        mode = config.get("mode")

        # Default force=False for read-only modes (plan/ask) to avoid
        # cursor-wrapper warnings about --force having no effect.
        force = config.get("force", mode not in {"plan", "ask"})
        if not isinstance(force, bool):
            raise TypeError(f"force must be a bool, got {type(force).__name__}")
        if force:
            cmd.append("--force")
        else:
            cmd.append("--no-force")

        if mode is not None:
            if not isinstance(mode, str):
                raise TypeError(f"mode must be a string, got {type(mode).__name__}")
            if mode not in {"plan", "ask"}:
                raise ValueError(f"mode must be 'plan' or 'ask', got {mode!r}")
            cmd += ["--mode", mode]

        if "sandbox" in config:
            sandbox = config["sandbox"]
            if not isinstance(sandbox, str):
                raise TypeError(f"sandbox must be a string, got {type(sandbox).__name__}")
            if sandbox not in {"enabled", "disabled"}:
                raise ValueError(f"sandbox must be 'enabled' or 'disabled', got {sandbox!r}")
            cmd += ["--sandbox", sandbox]

        if "max_turns" in config:
            _sys.stderr.write(
                "cursor-cli: warning: max_turns ignored"
                " — cursor-agent does not support --max-turns\n"
            )

        if "timeout" in config:
            timeout = config["timeout"]
            if not isinstance(timeout, int):
                raise TypeError(f"timeout must be an int, got {type(timeout).__name__}")
            cmd += ["--timeout", str(timeout)]

        extra_flags = config.get("extra_flags", [])
        if not isinstance(extra_flags, list):
            raise TypeError(f"extra_flags must be a list, got {type(extra_flags).__name__}")
        for flag in extra_flags:
            if not isinstance(flag, str):
                raise TypeError(f"extra_flags items must be strings, got {type(flag).__name__}")
            cmd += ["--extra-flag", flag]

        cmd.append("-")
        return cmd

    def parse_telemetry(
        self,
        telemetry_path: _pathlib.Path,
        wall_time_seconds: float,
    ) -> _types.TelemetryRecord:
        """Parse cursor-wrapper NDJSON output into normalized telemetry.

        Args:
            telemetry_path: Path to the output.jsonl stream file.
            wall_time_seconds: Observed wall time for the step.

        Returns:
            Normalized telemetry record with activity counts and timing.
        """
        num_turns = 0
        num_tool_calls = 0
        num_thinking_events = 0
        model: str | None = None
        duration_ms: float | None = None
        duration_api_ms: float | None = None

        if telemetry_path.exists():
            try:
                with telemetry_path.open() as telemetry_file:
                    for line in telemetry_file:
                        if not line.strip():
                            continue
                        try:
                            event = _json.loads(line)
                        except _json.JSONDecodeError:
                            continue
                        if not isinstance(event, dict):
                            continue

                        event_type = event.get("type")
                        if event_type == "assistant":
                            num_turns += 1
                        elif event_type == "tool_call" and event.get("subtype") == "started":
                            num_tool_calls += 1
                        elif event_type == "thinking":
                            num_thinking_events += 1
                        elif event_type == "system" and event.get("subtype") == "init":
                            event_model = event.get("model")
                            if isinstance(event_model, str):
                                model = event_model
                        elif event_type == "result":
                            raw_duration_ms = event.get("duration_ms")
                            raw_duration_api_ms = event.get("duration_api_ms")
                            if isinstance(raw_duration_ms, (int, float)):
                                duration_ms = float(raw_duration_ms)
                            if isinstance(raw_duration_api_ms, (int, float)):
                                duration_api_ms = float(raw_duration_api_ms)
            except OSError:
                pass

        effective_wall_time = wall_time_seconds
        if duration_ms is not None:
            effective_wall_time = duration_ms / 1000.0

        effective_api_time: float | None = None
        if duration_api_ms is not None:
            effective_api_time = duration_api_ms / 1000.0

        return _types.TelemetryRecord(
            fresh_input_tokens=0,
            cached_input_tokens=0,
            output_tokens=0,
            total_input_tokens=0,
            tokens_available=False,
            wall_time_seconds=effective_wall_time,
            api_time_seconds=effective_api_time,
            num_turns=num_turns,
            num_tool_calls=num_tool_calls,
            num_thinking_events=num_thinking_events,
            model=model,
            backend=self.name(),
            shadow_cost_usd=None,
        )

    def output_file_name(self, config: _types.StepConfig) -> str:
        """Return the output artifact filename for cursor-wrapper runs.

        Args:
            config: Step-level backend configuration.

        Returns:
            Filename containing stream NDJSON output.
        """
        del config
        return "output.jsonl"

    def telemetry_file_name(self) -> str:
        """Return the telemetry artifact filename for cursor-wrapper runs.

        Returns:
            Filename containing stream NDJSON output.
        """
        return "output.jsonl"
