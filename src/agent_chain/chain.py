"""Chain definition loading and validation."""

import pathlib as _pathlib
import tomllib as _tomllib

import agent_chain.types as _types
import agent_chain.variables as _variables

_VALID_STEP_TYPES = frozenset({"implement", "review", "fix", "verify", "custom"})

_VALID_ON_FAILURE = frozenset({"abort", "warn", "skip"})


class StepDefinition:
    """One step within a chain definition."""

    def __init__(
        self,
        *,
        name: str,
        step_type: str,
        agent: str,
        brief: _types.BriefConfig | None,
        agent_config: _types.StepConfig,
        gate: _types.GateConfig | None,
    ) -> None:
        """Initialize a step definition.

        Args:
            name: The step name, must be unique within the chain.
            step_type: Type of step (implement, review, fix, verify, custom).
            agent: Backend name or "none" for verify steps.
            brief: Brief configuration for agent instructions, or None for noop.
            agent_config: Backend-specific configuration options.
            gate: Optional verification gate configuration.
        """
        self.name = name
        self.step_type = step_type
        self.agent = agent
        self.brief = brief
        self.agent_config = agent_config
        self.gate = gate


class ChainDefinition:
    """Parsed, validated representation of a chain TOML file."""

    def __init__(
        self,
        *,
        name: str,
        description: str,
        default_timeout: int,
        working_dir: str | None,
        variables: dict[str, str],
        steps: list[StepDefinition],
        source_path: _pathlib.Path,
    ) -> None:
        """Initialize a chain definition.

        Args:
            name: Chain name from the definition file.
            description: Chain description.
            default_timeout: Default per-step timeout in seconds.
            working_dir: Working directory for step execution, or None for chain file directory.
            variables: Template variables defined in the chain.
            steps: List of step definitions in execution order.
            source_path: Path to the source TOML file.
        """
        self.name = name
        self.description = description
        self.default_timeout = default_timeout
        self.working_dir = working_dir
        self.variables = variables
        self.steps = steps
        self.source_path = source_path


class ValidationError(Exception):
    """Raised when a chain definition fails validation."""


class ValidationWarning:
    """A non-fatal validation issue."""

    def __init__(self, message: str) -> None:
        self.message = message

    def __repr__(self) -> str:
        return f"ValidationWarning({self.message!r})"


class ValidationResult:
    """Outcome of chain validation."""

    def __init__(
        self,
        errors: list[str],
        warnings: list[str],
    ) -> None:
        self.errors = errors
        self.warnings = warnings

    @property
    def ok(self) -> bool:
        """Indicate whether validation completed without errors.

        Returns:
            ``True`` when no validation errors were collected, else ``False``.
        """
        return len(self.errors) == 0


def _parse_step(raw: dict[str, object], index: int) -> StepDefinition:
    """Parse a single step table from the TOML data.

    Args:
        raw: Dictionary representing a step table from the TOML file.
        index: Index of this step in the steps list.

    Returns:
        A ``StepDefinition`` parsed from the raw data.

    Raises:
        ValidationError: If required fields are missing or invalid.
    """
    name = raw.get("name")
    if not isinstance(name, str) or not name:
        raise ValidationError(f"Step {index}: missing or empty 'name'")

    step_type = raw.get("type")
    if not isinstance(step_type, str) or step_type not in _VALID_STEP_TYPES:
        raise ValidationError(
            f"Step {index} ({name}): 'type' must be one of {sorted(_VALID_STEP_TYPES)}"
        )

    agent = raw.get("agent")
    if not isinstance(agent, str) or not agent:
        raise ValidationError(f"Step {index} ({name}): missing or empty 'agent'")

    brief_raw = raw.get("brief")
    brief: _types.BriefConfig | None = None
    if isinstance(brief_raw, dict):
        brief = _types.BriefConfig(**brief_raw)  # type: ignore[typeddict-item]

    agent_config_raw = raw.get("agent_config")
    agent_config: _types.StepConfig
    if isinstance(agent_config_raw, dict):
        agent_config = _types.StepConfig(**agent_config_raw)  # type: ignore[typeddict-item]
    else:
        agent_config = _types.StepConfig()

    gate_raw = raw.get("gate")
    gate: _types.GateConfig | None = None
    if isinstance(gate_raw, dict):
        gate = _types.GateConfig(**gate_raw)  # type: ignore[typeddict-item]

    return StepDefinition(
        name=name,
        step_type=step_type,
        agent=agent,
        brief=brief,
        agent_config=agent_config,
        gate=gate,
    )


def load(path: _pathlib.Path) -> ChainDefinition:
    """Load and parse a chain definition from a TOML file.

    Args:
        path: Path to the TOML chain definition file.

    Returns:
        A validated ``ChainDefinition``.

    Raises:
        ValidationError: If the file is malformed or missing required fields.
        FileNotFoundError: If *path* does not exist.
    """
    text = path.read_bytes()
    try:
        data = _tomllib.loads(text.decode())
    except _tomllib.TOMLDecodeError as exc:
        raise ValidationError(f"Invalid TOML: {exc}") from exc

    chain_table = data.get("chain")
    if not isinstance(chain_table, dict):
        raise ValidationError("Missing [chain] table")

    name = chain_table.get("name")
    if not isinstance(name, str) or not name:
        raise ValidationError("[chain] must have a non-empty 'name'")

    description = chain_table.get("description", "")
    if not isinstance(description, str):
        description = str(description)

    default_timeout = chain_table.get("default_timeout", 1800)
    if not isinstance(default_timeout, int):
        raise ValidationError("[chain].default_timeout must be an integer")

    working_dir_raw = chain_table.get("working_dir")
    working_dir: str | None = None
    if working_dir_raw is not None:
        if not isinstance(working_dir_raw, str):
            raise ValidationError("[chain].working_dir must be a string")
        working_dir = working_dir_raw

    vars_table = data.get("vars", {})
    if not isinstance(vars_table, dict):
        raise ValidationError("[vars] must be a table")
    variables: dict[str, str] = {str(k): str(v) for k, v in vars_table.items()}

    steps_raw = data.get("steps")
    if not isinstance(steps_raw, list) or len(steps_raw) == 0:
        raise ValidationError("Chain must have at least one [[steps]] entry")

    steps: list[StepDefinition] = []
    seen_names: set[str] = set()
    for i, step_raw in enumerate(steps_raw):
        if not isinstance(step_raw, dict):
            raise ValidationError(f"Step {i}: expected a table, got {type(step_raw).__name__}")
        step = _parse_step(step_raw, i)
        if step.name in seen_names:
            raise ValidationError(f"Duplicate step name: {step.name!r}")
        seen_names.add(step.name)
        steps.append(step)

    return ChainDefinition(
        name=name,
        description=description,
        default_timeout=default_timeout,
        working_dir=working_dir,
        variables=variables,
        steps=steps,
        source_path=path.resolve(),
    )


def validate(
    chain: ChainDefinition,
    cli_vars: dict[str, str] | None = None,
    *,
    known_backends: frozenset[str] | None = None,
) -> ValidationResult:
    """Validate a loaded chain definition.

    Args:
        chain: A parsed ``ChainDefinition``.
        cli_vars: Variables provided via ``--var`` flags.
        known_backends: Set of registered backend names for agent validation.

    Returns:
        A ``ValidationResult`` with errors and warnings.
    """
    errors: list[str] = []
    warnings: list[str] = []

    all_vars = dict(chain.variables)
    if cli_vars:
        all_vars.update(cli_vars)

    # Built-in variables are always available (we add placeholders for validation)
    builtins = [
        "chain.name",
        "chain.output_dir",
        "step.name",
        "step.output_dir",
        "previous_step.name",
        "previous_step.output_dir",
        "previous_step.output_path",
        "previous_step.status",
    ]
    for b in builtins:
        all_vars.setdefault(b, "<builtin>")

    for step in chain.steps:
        # Check agent backend is known
        if known_backends is not None and step.agent not in known_backends and step.agent != "none":
            errors.append(
                f"Step {step.name!r}: unknown agent backend {step.agent!r}"
            )

        # Verify steps must have a gate
        if step.step_type == "verify" and step.gate is None:
            errors.append(f"Step {step.name!r}: verify steps must have a gate")

        # Verify steps must use agent="none"
        if step.step_type == "verify" and step.agent != "none":
            errors.append(
                f"Step {step.name!r}: verify steps must use agent='none'"
            )

        # Non-verify steps need a brief (unless agent is "none")
        if step.step_type != "verify" and step.agent != "none" and step.brief is None:
            errors.append(f"Step {step.name!r}: non-verify steps must have a brief")

        # Validate brief variable references
        if step.brief is not None:
            if step.brief.get("source") == "file":
                brief_path = step.brief.get("path", "")
                if brief_path:
                    missing = _variables.check_undefined(brief_path, all_vars)
                    for m in missing:
                        msg = f"Step {step.name!r}: brief path references "
                        msg += f"undefined variable {{{{{m}}}}}"
                        errors.append(msg)
            elif step.brief.get("source") == "inline":
                text = step.brief.get("text", "")
                if text:
                    missing = _variables.check_undefined(text, all_vars)
                    for m in missing:
                        msg = f"Step {step.name!r}: brief text references "
                        msg += f"undefined variable {{{{{m}}}}}"
                        errors.append(msg)

        # Validate gate variable references
        if step.gate is not None:
            cmd = step.gate.get("command", "")
            if cmd:
                missing = _variables.check_undefined(cmd, all_vars)
                for m in missing:
                    msg = f"Step {step.name!r}: gate command references "
                    msg += f"undefined variable {{{{{m}}}}}"
                    errors.append(msg)
            on_failure = step.gate.get("on_failure", "abort")
            if on_failure not in _VALID_ON_FAILURE:
                valid = sorted(_VALID_ON_FAILURE)
                errors.append(
                    f"Step {step.name!r}: gate on_failure must be one of {valid}"
                )
        else:
            if step.step_type not in ("verify", "custom"):
                warnings.append(f"Step {step.name!r}: no verification gate configured")

    return ValidationResult(errors=errors, warnings=warnings)
