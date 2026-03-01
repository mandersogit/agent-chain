"""Shared types for agent-chain."""

import enum as _enum
import pathlib as _pathlib
import typing as _typing

DEFAULT_STEP_TIMEOUT: int = 21600  # 6 hours; 0 means no limit


class StepStatus(_enum.Enum):
    """Status of a completed or in-progress step."""

    SUCCESS = "success"
    FAILED = "failed"
    GATE_FAILED = "gate_failed"
    TIMEOUT = "timeout"
    CRASHED = "crashed"
    CONFIG_ERROR = "config_error"
    INTERRUPTED = "interrupted"
    NOT_STARTED = "not_started"
    SKIPPED = "skipped"


class StepConfig(_typing.TypedDict, total=False):
    """Agent configuration extracted from [steps.agent_config]."""

    model: str
    force: bool
    mode: str
    sandbox: str
    permission_mode: str
    reasoning_effort: str
    effort: str
    max_turns: int
    timeout: int
    output_schema: str
    extra_flags: list[str]


class AgentResult(_typing.NamedTuple):
    """Result of an agent invocation."""

    exit_code: int
    output_path: _pathlib.Path
    telemetry_path: _pathlib.Path
    wall_time_seconds: float


class TelemetryRecord(_typing.TypedDict):
    """Normalized telemetry — provider-independent."""

    # Token usage — zero when backend cannot report tokens.
    # Check tokens_available to distinguish "unknown" from "zero."
    fresh_input_tokens: int
    cached_input_tokens: int
    output_tokens: int
    total_input_tokens: int
    tokens_available: bool

    # Timing
    wall_time_seconds: float
    api_time_seconds: float | None

    # Activity counts
    num_turns: int
    num_tool_calls: int
    num_thinking_events: int

    # Identity
    model: str | None
    backend: str | None

    # Cost
    shadow_cost_usd: float | None


class GateConfig(_typing.TypedDict, total=False):
    """Verification gate configuration."""

    command: str
    expected_exit_code: int
    on_failure: str
    timeout: int


class BriefConfig(_typing.TypedDict, total=False):
    """Brief sourcing configuration."""

    source: str
    path: str
    text: str


class ChainStatus(_enum.Enum):
    """Overall chain completion status."""

    SUCCESS = "success"
    SUCCESS_WARNINGS = "success_warnings"
    FAILED = "failed"
    GATE_FAILED = "gate_failed"
    INTERRUPTED = "interrupted"
