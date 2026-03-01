"""Claude Code agent backend."""

import json as _json
import os as _os
import pathlib as _pathlib
import shutil as _shutil

import agent_chain.backends as _backends
import agent_chain.types as _types

_ENV_VAR = "AGENT_CHAIN_CLAUDE_BIN"
_BINARY_NAME = "claude"
_FALLBACK_PATH = _pathlib.Path.home() / ".local" / "bin" / "claude"


def _find_binary() -> _pathlib.Path:
    """Locate the Claude Code CLI binary.

    Discovery order is environment variable override, PATH lookup,
    then ``~/.local/bin/claude`` fallback.

    Returns:
        Resolved path to the Claude CLI binary.
    """
    env = _os.environ.get(_ENV_VAR)
    if env:
        return _pathlib.Path(env)
    which = _shutil.which(_BINARY_NAME)
    if which:
        return _pathlib.Path(which)
    return _FALLBACK_PATH


class ClaudeCodeBackend(_backends.AgentBackend):
    """Backend for Anthropic Claude Code CLI."""

    def __init__(self) -> None:
        self._binary = _find_binary()

    def name(self) -> str:
        """Return this backend's registry name.

        Returns:
            Backend name used in chain step `agent` fields.
        """
        return "claude-code"

    def build_command(
        self,
        brief_path: _pathlib.Path,
        step_output_dir: _pathlib.Path,
        working_dir: _pathlib.Path,
        config: _types.StepConfig,
    ) -> list[str]:
        """Build the subprocess command for Claude Code agent invocation.

        Args:
            brief_path: Path to the step brief file.
            step_output_dir: Output directory for the step.
            working_dir: Working directory for command execution.
            config: Step-level backend configuration.

        Returns:
            Command argv list for launching Claude Code CLI.
        """
        cmd: list[str] = [
            str(self._binary),
            "-p",
            "--output-format", "json",
        ]

        model = config.get("model", "sonnet")
        if not isinstance(model, str):
            raise TypeError(f"model must be a string, got {type(model).__name__}")
        cmd += ["--model", model]

        effort = config.get("effort", "high")
        if not isinstance(effort, str):
            raise TypeError(f"effort must be a string, got {type(effort).__name__}")
        cmd += ["--effort", effort]

        perm = config.get("permission_mode", "dangerously-skip-permissions")
        if not isinstance(perm, str):
            raise TypeError(f"permission_mode must be a string, got {type(perm).__name__}")
        if perm == "plan":
            cmd += ["--permission-mode", "plan"]
        else:
            cmd.append("--dangerously-skip-permissions")

        if "max_turns" in config:
            max_turns = config["max_turns"]
            if not isinstance(max_turns, int):
                raise TypeError(f"max_turns must be an int, got {type(max_turns).__name__}")
            cmd += ["--max-turns", str(max_turns)]

        if "output_schema" in config:
            output_schema = config["output_schema"]
            if not isinstance(output_schema, str):
                msg = f"output_schema must be a string, got {type(output_schema).__name__}"
                raise TypeError(msg)
            schema_path = _pathlib.Path(output_schema)
            if schema_path.exists():
                schema_path = schema_path.resolve()
                step_base = step_output_dir.resolve()
                try:
                    schema_path.relative_to(step_base)
                except ValueError as exc:
                    raise ValueError(
                        f"output_schema path {schema_path} is outside step directory {step_base}"
                    ) from exc
                schema_text = schema_path.read_text()
                cmd += ["--json-schema", schema_text]

        extra_flags = config.get("extra_flags", [])
        if not isinstance(extra_flags, list):
            raise TypeError(f"extra_flags must be a list, got {type(extra_flags).__name__}")
        for flag in extra_flags:
            if not isinstance(flag, str):
                raise TypeError(f"extra_flags items must be strings, got {type(flag).__name__}")
        cmd += extra_flags

        return cmd

    def parse_telemetry(
        self,
        telemetry_path: _pathlib.Path,
        wall_time_seconds: float,
    ) -> _types.TelemetryRecord:
        """Parse Claude Code raw.json telemetry into normalized record.

        Args:
            telemetry_path: Path to the raw.json telemetry file.
            wall_time_seconds: Observed wall time for the step.

        Returns:
            Normalized telemetry record with token counts and cost data.
        """
        if not telemetry_path.exists():
            return _types.TelemetryRecord(
                fresh_input_tokens=0,
                cached_input_tokens=0,
                output_tokens=0,
                total_input_tokens=0,
                tokens_available=False,
                wall_time_seconds=wall_time_seconds,
                api_time_seconds=None,
                num_turns=0,
                num_tool_calls=0,
                num_thinking_events=0,
                model=None,
                backend=self.name(),
                shadow_cost_usd=None,
            )

        data = _json.loads(telemetry_path.read_text(encoding="utf-8"))
        usage = data.get("usage", {})

        # Claude Code: input_tokens = fresh only. Cache is separate.
        fresh = usage.get("input_tokens", 0)
        cache_write = usage.get("cache_creation_input_tokens", 0)
        cache_read = usage.get("cache_read_input_tokens", 0)
        cached = cache_write + cache_read
        output = usage.get("output_tokens", 0)

        duration_ms = data.get("duration_ms")
        effective_wall_time = (
            duration_ms / 1000.0 if duration_ms is not None else wall_time_seconds
        )

        content = data.get("content", [])
        num_tool_calls = sum(
            1 for block in content
            if isinstance(block, dict) and block.get("type") == "tool_use"
        )

        return _types.TelemetryRecord(
            fresh_input_tokens=fresh,
            cached_input_tokens=cached,
            output_tokens=output,
            total_input_tokens=fresh + cached,
            tokens_available=True,
            wall_time_seconds=effective_wall_time,
            api_time_seconds=None,
            num_turns=data.get("num_turns", 0),
            num_tool_calls=num_tool_calls,
            num_thinking_events=0,
            model=data.get("model"),
            backend=self.name(),
            shadow_cost_usd=data.get("total_cost_usd"),
        )

    def output_file_name(self, config: _types.StepConfig) -> str:
        """Return the output artifact filename for Claude runs.

        Args:
            config: Step-level backend configuration.

        Returns:
            Filename written by the Claude CLI output mode.
        """
        return "raw.json"

    def telemetry_file_name(self) -> str:
        """Return the telemetry artifact filename for Claude runs.

        Returns:
            Filename containing Claude telemetry data.
        """
        return "raw.json"
