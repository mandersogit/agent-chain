"""Edge-case tests for the chain runner."""

import json
import pathlib
import textwrap

import pytest

import agent_chain.chain as chain
import agent_chain.runner as runner
import agent_chain.types as types


@pytest.fixture
def write_chain(tmp_path: pathlib.Path) -> callable:
    """Write TOML chain content into the test temp directory."""

    def _write(toml: str) -> pathlib.Path:
        path = tmp_path / "chain.toml"
        path.write_text(textwrap.dedent(toml))
        return path

    return _write


@pytest.fixture
def output_dir(tmp_path: pathlib.Path) -> pathlib.Path:
    """Output directory used by ChainRunner for test artifacts."""
    return tmp_path / "output"


@pytest.fixture
def make_runner(
    tmp_path: pathlib.Path,
    output_dir: pathlib.Path,
    write_chain: callable,
) -> callable:
    """Build a runner from inline TOML."""

    def _make(toml: str, **kwargs: object) -> runner.ChainRunner:
        chain_def = chain.load(write_chain(toml))
        return runner.ChainRunner(
            chain_def=chain_def,
            output_dir=output_dir,
            working_dir=tmp_path,
            **kwargs,
        )

    return _make


def test_empty_chain_all_verify_gates_pass_runs_to_completion(
    make_runner: callable,
    output_dir: pathlib.Path,
) -> None:
    """A verify-only chain with passing gates completes successfully."""
    chain_runner = make_runner(
        """
        [chain]
        name = "empty-chain"

        [[steps]]
        name = "check-1"
        type = "verify"
        agent = "none"
        [steps.gate]
        command = "true"

        [[steps]]
        name = "check-2"
        type = "verify"
        agent = "none"
        [steps.gate]
        command = "true"
        """
    )

    results = chain_runner.run()

    assert [result.name for result in results] == ["check-1", "check-2"]
    assert [result.status for result in results] == [
        types.StepStatus.SUCCESS,
        types.StepStatus.SUCCESS,
    ]
    assert all(result.gate_result is not None for result in results)
    assert all(result.gate_result["passed"] is True for result in results if result.gate_result)
    assert (output_dir / "DONE").read_text().strip() == "success"


def test_all_gates_failing_first_step_abort_marks_remaining_not_started(
    make_runner: callable,
    output_dir: pathlib.Path,
) -> None:
    """An aborting gate failure on the first step stops all later steps."""
    chain_runner = make_runner(
        """
        [chain]
        name = "all-gates-failing"

        [[steps]]
        name = "first"
        type = "verify"
        agent = "none"
        [steps.gate]
        command = "false"
        on_failure = "abort"

        [[steps]]
        name = "second"
        type = "verify"
        agent = "none"
        [steps.gate]
        command = "false"

        [[steps]]
        name = "third"
        type = "verify"
        agent = "none"
        [steps.gate]
        command = "false"
        """
    )

    results = chain_runner.run()

    assert len(results) == 3
    assert results[0].status == types.StepStatus.GATE_FAILED
    assert results[0].gate_result is not None
    assert results[0].gate_result["on_failure"] == "abort"
    assert results[0].gate_result["passed"] is False
    assert [results[1].status, results[2].status] == [
        types.StepStatus.NOT_STARTED,
        types.StepStatus.NOT_STARTED,
    ]
    assert results[1].gate_result is None
    assert results[2].gate_result is None
    assert (output_dir / "DONE").read_text().strip() == "gate_failed"


def test_gate_warn_mode_first_step_fails_continues_to_next_step(
    make_runner: callable,
    output_dir: pathlib.Path,
) -> None:
    """A warning gate failure still allows subsequent steps to run."""
    chain_runner = make_runner(
        """
        [chain]
        name = "warn-mode"

        [[steps]]
        name = "warn-step"
        type = "verify"
        agent = "none"
        [steps.gate]
        command = "false"
        on_failure = "warn"

        [[steps]]
        name = "next-step"
        type = "verify"
        agent = "none"
        [steps.gate]
        command = "true"
        """
    )

    results = chain_runner.run()

    assert len(results) == 2
    assert results[0].status == types.StepStatus.GATE_FAILED
    assert results[0].gate_result is not None
    assert results[0].gate_result["on_failure"] == "warn"
    assert results[1].status == types.StepStatus.SUCCESS
    assert results[1].gate_result is not None
    assert results[1].gate_result["passed"] is True
    assert (output_dir / "DONE").read_text().strip() == "success_warnings"


def test_missing_brief_file_step_path_not_found_returns_config_error(
    make_runner: callable,
    output_dir: pathlib.Path,
) -> None:
    """A missing brief file path marks the step as CONFIG_ERROR."""
    chain_runner = make_runner(
        """
        [chain]
        name = "missing-brief"

        [[steps]]
        name = "impl"
        type = "implement"
        agent = "codex-cli"
        [steps.brief]
        source = "file"
        path = "brief-does-not-exist.md"
        """
    )

    results = chain_runner.run()

    assert len(results) == 1
    assert results[0].status == types.StepStatus.CONFIG_ERROR
    assert results[0].exit_code is None
    assert results[0].output_path is None
    assert results[0].telemetry_path is None
    assert results[0].gate_result is None
    assert (output_dir / "DONE").read_text().strip() == "failed"

    report = json.loads((output_dir / "report.json").read_text())
    assert report["chain"]["status"] == "failed"
    assert report["steps"][0]["status"] == "config_error"


def test_variable_resolution_templates_in_brief_and_gate_are_substituted(
    make_runner: callable,
    output_dir: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Template variables are resolved in both brief text and gate command."""

    class FakePopen:
        """Successful no-op process used to avoid launching a real agent."""

        def __init__(self, *_args: object, **_kwargs: object) -> None:
            self.pid = 12345
            self.returncode = 0

        def wait(self, timeout: int | None = None) -> int:
            del timeout
            self.returncode = 0
            return 0

        def terminate(self) -> None:
            self.returncode = -15

        def kill(self) -> None:
            self.returncode = -9

        def send_signal(self, _signum: int) -> None:
            self.returncode = -2

    class FakeCompletedProcess:
        """Minimal completed-process shape for mocked gate execution."""

        def __init__(self, returncode: int) -> None:
            self.returncode = returncode

    def fake_run(_command: str, **_kwargs: object) -> FakeCompletedProcess:
        return FakeCompletedProcess(returncode=0)

    monkeypatch.setattr(runner._subprocess, "Popen", FakePopen)
    monkeypatch.setattr(runner._subprocess, "run", fake_run)

    chain_runner = make_runner(
        """
        [chain]
        name = "tpl"

        [vars]
        target = "W"

        [[steps]]
        name = "s1"
        type = "implement"
        agent = "codex-cli"

        [steps.brief]
        source = "inline"
        text = "Hello {{target}} from {{chain.name}} in {{step.name}}."

        [steps.gate]
        command = "test '{{target}}/{{chain.name}}/{{step.name}}' = 'W/tpl/s1'"
        """
    )

    results = chain_runner.run()

    assert len(results) == 1
    assert results[0].status == types.StepStatus.SUCCESS
    assert results[0].gate_result is not None
    assert results[0].gate_result["passed"] is True
    assert results[0].gate_result["command"] == "test 'W/tpl/s1' = 'W/tpl/s1'"

    brief_path = output_dir / "steps" / "s1" / "brief.md"
    assert brief_path.exists()
    assert brief_path.read_text() == "Hello W from tpl in s1."
