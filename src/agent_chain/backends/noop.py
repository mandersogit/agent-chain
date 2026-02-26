"""No-op backend for verify steps (agent="none")."""

import pathlib as _pathlib

import agent_chain.backends as _backends
import agent_chain.types as _types


class NoopBackend(_backends.AgentBackend):
    """Backend that performs no agent invocation.

    Used for ``verify`` steps that only run the gate command.
    """

    def name(self) -> str:
        """Return this backend's registry name.

        Returns:
            Name used for no-op/verify-only steps.
        """
        return "none"

    def build_command(
        self,
        brief_path: _pathlib.Path,
        step_output_dir: _pathlib.Path,
        working_dir: _pathlib.Path,
        config: _types.StepConfig,
    ) -> list[str]:
        """Return the command for this backend.

        Args:
            brief_path: Path to the step brief file.
            step_output_dir: Output directory for the step.
            working_dir: Working directory for command execution.
            config: Step-level backend configuration.

        Returns:
            An empty command list because this backend launches no process.
        """
        return []

    def parse_telemetry(
        self,
        telemetry_path: _pathlib.Path,
        wall_time_seconds: float,
    ) -> _types.TelemetryRecord:
        """Return zero-valued telemetry for a no-op step.

        Args:
            telemetry_path: Path where telemetry would normally be read from.
            wall_time_seconds: Observed wall time for the step.

        Returns:
            A telemetry record with zero token counts and no cost data.
        """
        return _types.TelemetryRecord(
            fresh_input_tokens=0,
            cached_input_tokens=0,
            output_tokens=0,
            total_input_tokens=0,
            num_turns=0,
            wall_time_seconds=wall_time_seconds,
            shadow_cost_usd=None,
        )

    def output_file_name(self, config: _types.StepConfig) -> str:
        """Return the output artifact filename for this backend.

        Args:
            config: Step-level backend configuration.

        Returns:
            An empty string because no output artifact is produced.
        """
        return ""

    def telemetry_file_name(self) -> str:
        """Return the telemetry artifact filename for this backend.

        Returns:
            An empty string because no telemetry file is produced.
        """
        return ""
