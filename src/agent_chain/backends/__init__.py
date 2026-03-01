"""Agent backend interface and registry."""

import abc as _abc
import pathlib as _pathlib

import agent_chain.types as _types


class AgentBackend(_abc.ABC):
    """Abstract interface that agent backends must implement."""

    @_abc.abstractmethod
    def name(self) -> str:
        """Return the backend's registered name.

        Returns:
            The backend name as used in step definitions.
        """
        ...

    @_abc.abstractmethod
    def build_command(
        self,
        brief_path: _pathlib.Path,
        step_output_dir: _pathlib.Path,
        working_dir: _pathlib.Path,
        config: _types.StepConfig,
    ) -> list[str]:
        """Build the subprocess command (argv list) for this agent invocation.

        Args:
            brief_path: Path to the step brief file to be provided to the agent.
            step_output_dir: Output directory where the agent writes results.
            working_dir: Working directory for the subprocess.
            config: Backend-specific configuration options.

        Returns:
            Command argv list ready for subprocess execution.
        """
        ...

    @_abc.abstractmethod
    def parse_telemetry(
        self,
        telemetry_path: _pathlib.Path,
        wall_time_seconds: float,
    ) -> _types.TelemetryRecord:
        """Parse the agent's native telemetry file into a normalized TelemetryRecord.

        Args:
            telemetry_path: Path to the backend's telemetry output file.
            wall_time_seconds: Observed wall time for the step execution.

        Returns:
            Normalized telemetry record with token counts and timing information.
        """
        ...

    @_abc.abstractmethod
    def output_file_name(self, config: _types.StepConfig) -> str:
        """Return the expected output file name for this backend.

        Args:
            config: Backend-specific configuration options.

        Returns:
            The output artifact filename written by this backend.
        """
        ...

    @_abc.abstractmethod
    def telemetry_file_name(self) -> str:
        """Return the expected telemetry file name for this backend.

        Returns:
            The telemetry artifact filename written by this backend.
        """
        ...

    def fallback_output_from_telemetry(
        self,
        telemetry_path: _pathlib.Path,
        output_path: _pathlib.Path,
    ) -> bool:
        """Attempt to reconstruct missing output from backend telemetry.

        Args:
            telemetry_path: Path to the backend telemetry artifact.
            output_path: Path where the primary output artifact should be written.

        Returns:
            ``True`` when output was recovered and written, else ``False``.
        """
        del telemetry_path
        del output_path
        return False


import agent_chain.backends.claude_code as _claude_code  # noqa: E402
import agent_chain.backends.codex_cli as _codex_cli  # noqa: E402
import agent_chain.backends.cursor_cli as _cursor_cli  # noqa: E402
import agent_chain.backends.noop as _noop  # noqa: E402

REGISTRY: dict[str, type[AgentBackend]] = {
    "codex-cli": _codex_cli.CodexCliBackend,
    "claude-code": _claude_code.ClaudeCodeBackend,
    "cursor-cli": _cursor_cli.CursorCliBackend,
    "none": _noop.NoopBackend,
}


def get_backend(name: str) -> AgentBackend:
    """Look up and instantiate a backend by name.

    Args:
        name: Backend name to look up in the registry.

    Returns:
        An instantiated backend object.

    Raises:
        ValueError: If *name* is not registered.
    """
    cls = REGISTRY.get(name)
    if cls is None:
        raise ValueError(
            f"Unknown agent backend: {name!r}. "
            f"Available: {', '.join(sorted(REGISTRY))}"
        )
    return cls()


def known_backend_names() -> frozenset[str]:
    """Return the set of all registered backend names.

    Returns:
        Frozenset of all available backend names.
    """
    return frozenset(REGISTRY)
