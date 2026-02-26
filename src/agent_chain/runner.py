"""Chain runner — step loop, subprocess management, gate execution."""

import datetime as _datetime
import os as _os
import pathlib as _pathlib
import signal as _signal
import subprocess as _subprocess
import sys as _sys
import time as _time

import agent_chain.backends as _backends
import agent_chain.chain as _chain
import agent_chain.report as _report
import agent_chain.types as _types
import agent_chain.variables as _variables

_GRACE_PERIOD_SECONDS = 10


class StepResult:
    """Outcome of a single step execution."""

    def __init__(
        self,
        *,
        name: str,
        step_type: str,
        agent: str,
        status: _types.StepStatus,
        wall_time_seconds: float,
        exit_code: int | None,
        output_path: _pathlib.Path | None,
        telemetry_path: _pathlib.Path | None,
        telemetry: _types.TelemetryRecord | None,
        gate_result: dict[str, object] | None,
    ) -> None:
        """Initialize a step execution result.

        Args:
            name: Name of the executed step.
            step_type: Type of the step (implement, review, fix, verify, custom).
            agent: Backend that executed the step.
            status: Final status of the step execution.
            wall_time_seconds: Elapsed wall time for the step.
            exit_code: Process exit code, or None if not applicable.
            output_path: Path to the step's output artifact, or None if none.
            telemetry_path: Path to the telemetry file, or None if not recorded.
            telemetry: Parsed telemetry record, or None if unavailable.
            gate_result: Gate execution result dict, or None if not run.
        """
        self.name = name
        self.step_type = step_type
        self.agent = agent
        self.status = status
        self.wall_time_seconds = wall_time_seconds
        self.exit_code = exit_code
        self.output_path = output_path
        self.telemetry_path = telemetry_path
        self.telemetry = telemetry
        self.gate_result = gate_result


class ChainRunner:
    """Executes a chain definition step by step."""

    def __init__(
        self,
        chain_def: _chain.ChainDefinition,
        output_dir: _pathlib.Path,
        working_dir: _pathlib.Path,
        cli_vars: dict[str, str] | None = None,
        global_timeout: int = 1800,
        verbose: bool = False,
        dry_run: bool = False,
    ) -> None:
        """Initialize a chain runner.

        Args:
            chain_def: The chain definition to execute.
            output_dir: Base directory for all step outputs.
            working_dir: Working directory for step execution.
            cli_vars: Variables provided via CLI, merged with chain definition variables.
            global_timeout: Global timeout in seconds, used as fallback for per-step timeouts.
            verbose: Print step progress to stderr if True.
            dry_run: If True, print commands without launching agents.
        """
        self._chain = chain_def
        self._output_dir = output_dir
        self._working_dir = working_dir
        self._cli_vars = cli_vars or {}
        self._global_timeout = global_timeout
        self._verbose = verbose
        self._dry_run = dry_run
        self._active_process: _subprocess.Popen[bytes] | None = None
        self._interrupted = False
        self._last_sigint_time: float = 0.0

    def run(self) -> list[StepResult]:
        """Execute all steps in order.

        Returns:
            List of ``StepResult`` objects, one per step.
        """
        self._output_dir.mkdir(parents=True, exist_ok=True)
        steps_dir = self._output_dir / "steps"
        steps_dir.mkdir(exist_ok=True)

        started_at = _datetime.datetime.now(_datetime.UTC)
        results: list[StepResult] = []
        prev_result: StepResult | None = None

        if not self._dry_run:
            self._setup_signal_handlers()

        for i, step_def in enumerate(self._chain.steps):
            if self._interrupted:
                results.append(self._not_started_result(step_def))
                continue

            step_name_safe = _pathlib.Path(step_def.name).name
            if step_name_safe in (".", ".."):
                self._log(f"  Invalid step name: {step_def.name!r}")
                results.append(StepResult(
                    name=step_def.name,
                    step_type=step_def.step_type,
                    agent=step_def.agent,
                    status=_types.StepStatus.CONFIG_ERROR,
                    wall_time_seconds=0.0,
                    exit_code=None,
                    output_path=None,
                    telemetry_path=None,
                    telemetry=None,
                    gate_result=None,
                ))
                prev_result = results[-1]
                continue
            step_output_dir = steps_dir / step_name_safe
            step_output_dir.mkdir(exist_ok=True)

            variables = self._build_variables(step_def, step_output_dir, prev_result)

            if self._dry_run:
                result = self._dry_run_step(step_def, step_output_dir, variables)
            else:
                result = self._run_step(step_def, step_output_dir, variables)

            results.append(result)
            prev_result = result

            if result.status not in (
                _types.StepStatus.SUCCESS,
                _types.StepStatus.SKIPPED,
            ):
                if result.status == _types.StepStatus.GATE_FAILED:
                    gate = step_def.gate
                    on_failure = gate.get("on_failure", "abort") if gate else "abort"
                    if on_failure == "warn":
                        self._log(f"  WARNING: gate failed for step {step_def.name!r}, continuing")
                        continue
                    if on_failure == "skip":
                        self._log(f"  Skipping post-processing for step {step_def.name!r}")
                        continue

                self._log(f"  Chain aborting at step {step_def.name!r}: {result.status.value}")
                for remaining in self._chain.steps[i + 1 :]:
                    results.append(self._not_started_result(remaining))
                break

        if not self._dry_run:
            finished_at = _datetime.datetime.now(_datetime.UTC)
            _report.write_report(
                chain_def=self._chain,
                output_dir=self._output_dir,
                started_at=started_at,
                finished_at=finished_at,
                results=results,
            )

        return results

    def _build_variables(
        self,
        step_def: _chain.StepDefinition,
        step_output_dir: _pathlib.Path,
        prev_result: StepResult | None,
    ) -> dict[str, str]:
        """Build the complete variable context for a step.

        Args:
            step_def: The step definition for this step.
            step_output_dir: Output directory for this step.
            prev_result: Result from the previous step, or None if first step.

        Returns:
            Dictionary mapping variable names to resolved values.
        """
        variables = dict(self._chain.variables)
        variables.update(self._cli_vars)

        variables["chain.name"] = self._chain.name
        variables["chain.output_dir"] = str(self._output_dir.resolve())
        variables["step.name"] = step_def.name
        variables["step.output_dir"] = str(step_output_dir.resolve())

        if prev_result is not None:
            variables["previous_step.name"] = prev_result.name
            prev_step_name_safe = _pathlib.Path(prev_result.name).name
            prev_step_dir = self._output_dir / "steps" / prev_step_name_safe
            variables["previous_step.output_dir"] = str(prev_step_dir.resolve())
            variables["previous_step.output_path"] = (
                str(prev_result.output_path) if prev_result.output_path else ""
            )
            variables["previous_step.status"] = prev_result.status.value
        else:
            variables["previous_step.name"] = ""
            variables["previous_step.output_dir"] = ""
            variables["previous_step.output_path"] = ""
            variables["previous_step.status"] = ""

        return variables

    def _resolve_brief(
        self,
        step_def: _chain.StepDefinition,
        step_output_dir: _pathlib.Path,
        variables: dict[str, str],
    ) -> str | None:
        """Resolve brief text, applying variable substitution.

        Args:
            step_def: The step definition containing the brief configuration.
            step_output_dir: Output directory for this step.
            variables: Variables for template substitution.

        Returns:
            Resolved brief text, or None if no brief is configured.

        Raises:
            FileNotFoundError: If brief source is file and path does not exist.
            KeyError: If a template variable is not defined.
            ValueError: If brief file path is outside chain base directory.
        """
        brief = step_def.brief
        if brief is None:
            return None

        source = brief.get("source", "inline")
        if source == "file":
            raw_path = brief.get("path", "")
            resolved_path = _variables.resolve(raw_path, variables)
            file_path = _pathlib.Path(resolved_path)
            if not file_path.is_absolute():
                file_path = self._chain.source_path.parent / file_path
            file_path = file_path.resolve()
            chain_base = self._chain.source_path.parent.resolve()
            try:
                file_path.relative_to(chain_base)
            except ValueError as exc:
                raise ValueError(
                    f"Brief file path {file_path} is outside chain base directory {chain_base}"
                ) from exc
            text = file_path.read_text()
        elif source == "inline":
            text = brief.get("text", "")
        else:
            return None

        return _variables.resolve(text, variables)

    def _run_step(
        self,
        step_def: _chain.StepDefinition,
        step_output_dir: _pathlib.Path,
        variables: dict[str, str],
    ) -> StepResult:
        """Execute a single step: agent invocation + gate.

        Args:
            step_def: The step definition to execute.
            step_output_dir: Directory for step outputs and logs.
            variables: Variables available for template substitution.

        Returns:
            A ``StepResult`` with execution status, timing, and gate results.
        """
        self._log(f"Step: {step_def.name} ({step_def.step_type}, agent={step_def.agent})")

        is_noop = step_def.agent == "none"
        backend = _backends.get_backend(step_def.agent)

        agent_result: _types.AgentResult | None = None
        telemetry_record: _types.TelemetryRecord | None = None
        exit_code: int | None = None
        status = _types.StepStatus.SUCCESS
        wall_time = 0.0

        if not is_noop:
            try:
                brief_text = self._resolve_brief(step_def, step_output_dir, variables)
            except (FileNotFoundError, KeyError, ValueError, OSError) as exc:
                self._log(f"  Config error: {exc}")
                return StepResult(
                    name=step_def.name,
                    step_type=step_def.step_type,
                    agent=step_def.agent,
                    status=_types.StepStatus.CONFIG_ERROR,
                    wall_time_seconds=0.0,
                    exit_code=None,
                    output_path=None,
                    telemetry_path=None,
                    telemetry=None,
                    gate_result=None,
                )

            brief_path = step_output_dir / "brief.md"
            if brief_text:
                brief_path.write_text(brief_text)

            try:
                cmd = backend.build_command(
                    brief_path, step_output_dir, self._working_dir, step_def.agent_config
                )
            except (OSError, ValueError, TypeError) as exc:
                self._log(f"  Config error: {exc}")
                return StepResult(
                    name=step_def.name,
                    step_type=step_def.step_type,
                    agent=step_def.agent,
                    status=_types.StepStatus.CONFIG_ERROR,
                    wall_time_seconds=0.0,
                    exit_code=None,
                    output_path=None,
                    telemetry_path=None,
                    telemetry=None,
                    gate_result=None,
                )

            telemetry_file = step_output_dir / backend.telemetry_file_name()
            stderr_file = step_output_dir / "stderr.log"
            output_file = step_output_dir / backend.output_file_name(step_def.agent_config)

            try:
                self._check_duplicate_pid(step_output_dir)
            except RuntimeError as exc:
                self._log(f"  Duplicate process: {exc}")
                return StepResult(
                    name=step_def.name,
                    step_type=step_def.step_type,
                    agent=step_def.agent,
                    status=_types.StepStatus.CONFIG_ERROR,
                    wall_time_seconds=0.0,
                    exit_code=None,
                    output_path=None,
                    telemetry_path=None,
                    telemetry=None,
                    gate_result=None,
                )

            try:
                timeout = self._resolve_timeout(step_def)
            except (ValueError, TypeError) as exc:
                self._log(f"  Config error: {exc}")
                return StepResult(
                    name=step_def.name,
                    step_type=step_def.step_type,
                    agent=step_def.agent,
                    status=_types.StepStatus.CONFIG_ERROR,
                    wall_time_seconds=0.0,
                    exit_code=None,
                    output_path=None,
                    telemetry_path=None,
                    telemetry=None,
                    gate_result=None,
                )

            start = _time.monotonic()
            proc = None
            try:
                with (
                    brief_path.open("rb") as stdin_f,
                    telemetry_file.open("wb") as stdout_f,
                    stderr_file.open("wb") as stderr_f,
                ):
                    child_env = _os.environ.copy()
                    child_env.pop("CLAUDECODE", None)
                    proc = _subprocess.Popen(
                        cmd,
                        stdin=stdin_f,
                        stdout=stdout_f,
                        stderr=stderr_f,
                        cwd=str(self._working_dir),
                        env=child_env,
                        start_new_session=True,
                    )
                    self._active_process = proc

                    pid_file = step_output_dir / "agent.pid"
                    try:
                        pid_file.write_text(str(proc.pid))
                    except OSError as exc:
                        self._active_process = None
                        self._terminate_process_tree(proc)
                        raise exc

                    try:
                        exit_code = proc.wait(timeout=timeout)
                    except _subprocess.TimeoutExpired:
                        self._log(f"  Timeout after {timeout}s, terminating...")
                        self._terminate_process_tree(proc)
                        status = _types.StepStatus.TIMEOUT
                        exit_code = proc.returncode
                    finally:
                        self._active_process = None
                        pid_file.unlink(missing_ok=True)

            except OSError as exc:
                self._log(f"  Launch error: {exc}")
                return StepResult(
                    name=step_def.name,
                    step_type=step_def.step_type,
                    agent=step_def.agent,
                    status=_types.StepStatus.CONFIG_ERROR,
                    wall_time_seconds=0.0,
                    exit_code=None,
                    output_path=None,
                    telemetry_path=None,
                    telemetry=None,
                    gate_result=None,
                )

            wall_time = _time.monotonic() - start

            if self._interrupted:
                status = _types.StepStatus.INTERRUPTED
            elif status != _types.StepStatus.TIMEOUT:
                if exit_code is not None and exit_code < 0:
                    status = _types.StepStatus.CRASHED
                elif exit_code is not None and exit_code != 0:
                    status = _types.StepStatus.FAILED

            try:
                telemetry_record = backend.parse_telemetry(telemetry_file, wall_time)
            except Exception:
                telemetry_record = None

            agent_result = _types.AgentResult(
                exit_code=exit_code or 0,
                output_path=output_file,
                telemetry_path=telemetry_file,
                wall_time_seconds=wall_time,
            )
        else:
            wall_time = 0.0

        gate_result: dict[str, object] | None = None
        if step_def.gate is not None and status == _types.StepStatus.SUCCESS:
            gate_result = self._run_gate(step_def, step_output_dir, variables)
            if not gate_result["passed"]:
                status = _types.StepStatus.GATE_FAILED

        return StepResult(
            name=step_def.name,
            step_type=step_def.step_type,
            agent=step_def.agent,
            status=status,
            wall_time_seconds=wall_time,
            exit_code=exit_code,
            output_path=agent_result.output_path if agent_result else None,
            telemetry_path=agent_result.telemetry_path if agent_result else None,
            telemetry=telemetry_record,
            gate_result=gate_result,
        )

    def _run_gate(
        self,
        step_def: _chain.StepDefinition,
        step_output_dir: _pathlib.Path,
        variables: dict[str, str],
    ) -> dict[str, object]:
        """Run a verification gate command.

        Args:
            step_def: The step definition with gate configuration.
            step_output_dir: Directory for gate output logs.
            variables: Variables for command template substitution.

        Returns:
            Dict with command, exit codes, and pass/fail status.
        """
        gate = step_def.gate
        assert gate is not None

        raw_command = gate.get("command", "")
        command = _variables.resolve_shell_safe(raw_command, variables)
        expected_exit_code = gate.get("expected_exit_code", 0)
        on_failure = gate.get("on_failure", "abort")

        self._log(f"  Gate: {command}")

        gate_stdout = step_output_dir / "gate-stdout.log"
        gate_stderr = step_output_dir / "gate-stderr.log"

        try:
            with gate_stdout.open("w") as out_f, gate_stderr.open("w") as err_f:
                result = _subprocess.run(
                    command,
                    shell=True,
                    stdout=out_f,
                    stderr=err_f,
                    cwd=str(self._working_dir),
                    timeout=300,
                )
            passed = result.returncode == expected_exit_code
        except _subprocess.TimeoutExpired:
            passed = False
            result = None
        except OSError:
            passed = False
            result = None

        actual_code = result.returncode if result is not None else -1
        self._log(f"  Gate result: exit_code={actual_code}, passed={passed}")

        return {
            "command": command,
            "exit_code": actual_code,
            "expected_exit_code": expected_exit_code,
            "on_failure": on_failure,
            "passed": passed,
        }

    def _dry_run_step(
        self,
        step_def: _chain.StepDefinition,
        step_output_dir: _pathlib.Path,
        variables: dict[str, str],
    ) -> StepResult:
        """Print what would be executed without launching anything.

        Args:
            step_def: The step definition to preview.
            step_output_dir: Directory where outputs would be written.
            variables: Variables for command template substitution.

        Returns:
            A ``StepResult`` with SUCCESS status but no actual execution.
        """
        is_noop = step_def.agent == "none"
        _sys.stderr.write(f"\n--- Step: {step_def.name} ---\n")
        _sys.stderr.write(f"  Type: {step_def.step_type}\n")
        _sys.stderr.write(f"  Agent: {step_def.agent}\n")

        if not is_noop:
            backend = _backends.get_backend(step_def.agent)
            brief_path = step_output_dir / "brief.md"
            cmd = backend.build_command(
                brief_path, step_output_dir, self._working_dir, step_def.agent_config
            )
            _sys.stderr.write(f"  Command: {' '.join(cmd)}\n")

        if step_def.gate:
            raw_command = step_def.gate.get("command", "")
            command = _variables.resolve(raw_command, variables)
            _sys.stderr.write(f"  Gate: {command}\n")

        _sys.stderr.write(f"  Output dir: {step_output_dir}\n")

        return StepResult(
            name=step_def.name,
            step_type=step_def.step_type,
            agent=step_def.agent,
            status=_types.StepStatus.SUCCESS,
            wall_time_seconds=0.0,
            exit_code=None,
            output_path=None,
            telemetry_path=None,
            telemetry=None,
            gate_result=None,
        )

    def _resolve_timeout(self, step_def: _chain.StepDefinition) -> int:
        """Determine timeout for a step (per-step > chain default > CLI global).

        Args:
            step_def: The step definition to check for timeout settings.

        Returns:
            Timeout in seconds, following priority order in docstring.
        """
        if "timeout" in step_def.agent_config:
            timeout = step_def.agent_config["timeout"]
            if not isinstance(timeout, int):
                raise TypeError(
                    f"timeout must be an int, got {type(timeout).__name__}"
                )
            return timeout
        return self._chain.default_timeout or self._global_timeout

    def _check_duplicate_pid(self, step_output_dir: _pathlib.Path) -> None:
        """Check for an existing agent.pid and abort if the process is alive.

        Args:
            step_output_dir: Directory containing the agent.pid file.

        Raises:
            RuntimeError: If an active agent process is detected.
        """
        pid_file = step_output_dir / "agent.pid"
        if not pid_file.exists():
            return
        try:
            pid = int(pid_file.read_text().strip())
            _os.kill(pid, 0)
            raise RuntimeError(
                f"Agent process {pid} is still running in {step_output_dir}. "
                "Use --force to kill and restart."
            )
        except (ProcessLookupError, ValueError):
            pid_file.unlink(missing_ok=True)
        except OSError as exc:
            raise RuntimeError(f"Cannot verify PID file: {exc}") from exc

    def _terminate_process_tree(self, proc: _subprocess.Popen[bytes]) -> None:
        """Terminate a process and its entire tree using process groups.

        Args:
            proc: The process to terminate.
        """
        try:
            if _sys.platform != "win32":
                _os.killpg(_os.getpgid(proc.pid), _signal.SIGTERM)
            else:
                proc.terminate()
        except (ProcessLookupError, PermissionError):
            pass

        try:
            proc.wait(timeout=_GRACE_PERIOD_SECONDS)
        except _subprocess.TimeoutExpired:
            try:
                if _sys.platform != "win32":
                    _os.killpg(_os.getpgid(proc.pid), _signal.SIGKILL)
                else:
                    proc.kill()
            except (ProcessLookupError, PermissionError):
                pass
            proc.wait()

    def _setup_signal_handlers(self) -> None:
        """Install SIGINT/SIGTERM handlers for graceful shutdown."""

        def handler(signum: int, frame: object) -> None:
            """Forward termination signals to the active agent process.

            Args:
                signum: Signal number received by the process.
                frame: Current stack frame passed by the signal handler.

            Raises:
                KeyboardInterrupt: If no agent process is currently active.
            """
            now = _time.monotonic()
            if self._active_process is not None:
                if signum == _signal.SIGINT and (now - self._last_sigint_time) < 1.0:
                    self._terminate_process_tree(self._active_process)
                    self._interrupted = True
                    return
                self._last_sigint_time = now
                try:
                    if _sys.platform != "win32":
                        _os.killpg(_os.getpgid(self._active_process.pid), signum)
                    else:
                        self._active_process.send_signal(signum)
                except (ProcessLookupError, PermissionError):
                    pass
                self._interrupted = True
            else:
                raise KeyboardInterrupt

        _signal.signal(_signal.SIGINT, handler)
        _signal.signal(_signal.SIGTERM, handler)

    def _not_started_result(self, step_def: _chain.StepDefinition) -> StepResult:
        """Create a NOT_STARTED result for a step that was never executed.

        Args:
            step_def: The step definition for which to create a result.

        Returns:
            A ``StepResult`` with NOT_STARTED status.
        """
        return StepResult(
            name=step_def.name,
            step_type=step_def.step_type,
            agent=step_def.agent,
            status=_types.StepStatus.NOT_STARTED,
            wall_time_seconds=0.0,
            exit_code=None,
            output_path=None,
            telemetry_path=None,
            telemetry=None,
            gate_result=None,
        )

    def _log(self, message: str) -> None:
        """Log a message to stderr if verbose mode is enabled.

        Args:
            message: The message to log.
        """
        if self._verbose:
            _sys.stderr.write(message + "\n")
