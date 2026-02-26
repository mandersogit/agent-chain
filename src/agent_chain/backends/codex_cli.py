"""codex-cli agent backend."""

import json as _json
import os as _os
import pathlib as _pathlib
import shutil as _shutil

import agent_chain.backends as _backends
import agent_chain.types as _types

_ENV_VAR = "AGENT_CHAIN_CODEX_BIN"
_BINARY_NAME = "codex"
_FALLBACK_PATH = _pathlib.Path.home() / ".local" / "bin" / "codex"


def _find_binary() -> _pathlib.Path:
    env = _os.environ.get(_ENV_VAR)
    if env:
        return _pathlib.Path(env)
    which = _shutil.which(_BINARY_NAME)
    if which:
        return _pathlib.Path(which)
    return _FALLBACK_PATH


class CodexCliBackend(_backends.AgentBackend):
    """Backend for OpenAI codex-cli."""

    def __init__(self) -> None:
        self._binary = _find_binary()

    def name(self) -> str:
        """Return this backend's registry name.

        Returns:
            Backend name used in chain step `agent` fields.
        """
        return "codex-cli"

    def build_command(
        self,
        brief_path: _pathlib.Path,
        step_output_dir: _pathlib.Path,
        working_dir: _pathlib.Path,
        config: _types.StepConfig,
    ) -> list[str]:
        """Build the subprocess command for codex-cli agent invocation.

        Args:
            brief_path: Path to the step brief file.
            step_output_dir: Output directory for the step.
            working_dir: Working directory for command execution.
            config: Step-level backend configuration.

        Returns:
            Command argv list for launching codex-cli exec.
        """
        output_name = self.output_file_name(config)
        cmd: list[str] = [
            str(self._binary),
            "exec",
            "--json",
        ]

        sandbox = config.get("sandbox", "full-auto")
        if not isinstance(sandbox, str):
            raise TypeError(f"sandbox must be a string, got {type(sandbox).__name__}")
        if sandbox == "read-only":
            cmd += ["--sandbox", "read-only"]
        else:
            cmd.append("--full-auto")

        effort = config.get("reasoning_effort", "medium")
        if not isinstance(effort, str):
            raise TypeError(f"reasoning_effort must be a string, got {type(effort).__name__}")
        cmd += ["-c", f"model_reasoning_effort={effort}"]

        cmd += ["-C", str(working_dir)]

        if "output_schema" in config:
            output_schema = config["output_schema"]
            if not isinstance(output_schema, str):
                msg = f"output_schema must be a string, got {type(output_schema).__name__}"
                raise TypeError(msg)
            cmd += ["--output-schema", output_schema]

        cmd += ["-o", str(step_output_dir / output_name)]
        extra_flags = config.get("extra_flags", [])
        if not isinstance(extra_flags, list):
            raise TypeError(f"extra_flags must be a list, got {type(extra_flags).__name__}")
        for flag in extra_flags:
            if not isinstance(flag, str):
                raise TypeError(f"extra_flags items must be strings, got {type(flag).__name__}")
        cmd += extra_flags

        cmd.append("-")
        return cmd

    def parse_telemetry(
        self,
        telemetry_path: _pathlib.Path,
        wall_time_seconds: float,
    ) -> _types.TelemetryRecord:
        """Parse codex-cli events.jsonl telemetry into normalized record.

        Args:
            telemetry_path: Path to the events.jsonl telemetry file.
            wall_time_seconds: Observed wall time for the step.

        Returns:
            Normalized telemetry record with token counts (no cost data).
        """
        totals = {"input_tokens": 0, "cached_input_tokens": 0, "output_tokens": 0}
        num_turns = 0

        if telemetry_path.exists():
            for line in telemetry_path.read_text().splitlines():
                if not line.strip():
                    continue
                event = _json.loads(line)
                if event.get("type") == "turn.completed":
                    num_turns += 1
                    usage = event.get("usage", {})
                    for k in totals:
                        totals[k] += usage.get(k, 0)

        fresh = totals["input_tokens"] - totals["cached_input_tokens"]

        return _types.TelemetryRecord(
            fresh_input_tokens=fresh,
            cached_input_tokens=totals["cached_input_tokens"],
            output_tokens=totals["output_tokens"],
            total_input_tokens=totals["input_tokens"],
            num_turns=num_turns,
            wall_time_seconds=wall_time_seconds,
            shadow_cost_usd=None,
        )

    def output_file_name(self, config: _types.StepConfig) -> str:
        """Return the output artifact filename for a Codex run.

        Args:
            config: Step-level backend configuration.

        Returns:
            `output.json` when an output schema is configured, otherwise
            `output.md`.
        """
        if "output_schema" in config:
            return "output.json"
        return "output.md"

    def telemetry_file_name(self) -> str:
        """Return the telemetry artifact filename for Codex runs.

        Returns:
            Filename containing Codex event telemetry.
        """
        return "events.jsonl"
