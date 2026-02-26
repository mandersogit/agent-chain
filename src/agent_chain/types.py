"""Shared types for agent-chain."""

import enum as _enum
import pathlib as _pathlib
import typing as _typing


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
    """Normalized token usage — provider-independent."""

    fresh_input_tokens: int
    cached_input_tokens: int
    output_tokens: int
    total_input_tokens: int
    num_turns: int
    wall_time_seconds: float
    shadow_cost_usd: float | None


class GateConfig(_typing.TypedDict, total=False):
    """Verification gate configuration."""

    command: str
    expected_exit_code: int
    on_failure: str


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
