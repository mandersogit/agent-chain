"""Tests for centralized timeout defaults and semantics."""

import pathlib as _pathlib
import textwrap as _textwrap

import pytest as _pytest

import agent_chain.chain as _chain
import agent_chain.cli as _cli
import agent_chain.runner as _runner
import agent_chain.types as _types

_FIXTURES = _pathlib.Path(__file__).parent / "fixtures"


def _write_chain(tmp_path: _pathlib.Path, toml: str) -> _pathlib.Path:
    path = tmp_path / "chain.toml"
    path.write_text(_textwrap.dedent(toml))
    return path


def test_default_step_timeout_is_21600() -> None:
    """The shared step timeout default is six hours."""
    assert _types.DEFAULT_STEP_TIMEOUT == 21600


def test_cli_default_uses_constant() -> None:
    """CLI run command timeout option default references the shared constant."""
    timeout_param = next(param for param in _cli.run.params if param.name == "timeout")
    assert timeout_param.default == _types.DEFAULT_STEP_TIMEOUT


def test_chain_default_uses_constant() -> None:
    """Chain loader fallback timeout matches the shared constant."""
    chain = _chain.load(_FIXTURES / "minimal_chain.toml")
    assert chain.default_timeout == _types.DEFAULT_STEP_TIMEOUT


def test_timeout_zero_means_no_limit(
    tmp_path: _pathlib.Path,
    monkeypatch: _pytest.MonkeyPatch,
) -> None:
    """Step timeout=0 resolves to no subprocess wait limit (timeout=None)."""

    observed_wait_timeouts: list[int | None] = []

    class FakePopen:
        """Minimal fake Popen that records wait timeout."""

        def __init__(self, *_args: object, **_kwargs: object) -> None:
            self.pid = 12345
            self.returncode = 0

        def wait(self, timeout: int | None = None) -> int:
            observed_wait_timeouts.append(timeout)
            self.returncode = 0
            return 0

    monkeypatch.setattr(_runner._subprocess, "Popen", FakePopen)

    toml = """
    [chain]
    name = "timeout-zero"

    [[steps]]
    name = "impl"
    type = "implement"
    agent = "codex-cli"
    [steps.brief]
    source = "inline"
    text = "hello"
    [steps.agent_config]
    timeout = 0
    """
    chain = _chain.load(_write_chain(tmp_path, toml))
    chain_runner = _runner.ChainRunner(
        chain_def=chain,
        output_dir=tmp_path / "output",
        working_dir=tmp_path,
    )

    assert chain_runner._resolve_timeout(chain.steps[0]) == 0

    results = chain_runner.run()
    assert results[0].status == _types.StepStatus.SUCCESS
    assert observed_wait_timeouts == [None]


def test_timeout_zero_not_treated_as_falsy(tmp_path: _pathlib.Path) -> None:
    """A configured timeout of 0 is preserved instead of falling back."""
    chain = _chain.ChainDefinition(
        name="timeout-falsy",
        description="",
        default_timeout=0,
        working_dir=None,
        variables={},
        steps=[
            _chain.StepDefinition(
                name="impl",
                step_type="implement",
                agent="codex-cli",
                brief={"source": "inline", "text": "x"},
                agent_config={},
                gate=None,
            )
        ],
        source_path=tmp_path / "chain.toml",
    )
    chain_runner = _runner.ChainRunner(
        chain_def=chain,
        output_dir=tmp_path / "output",
        working_dir=tmp_path,
        global_timeout=_types.DEFAULT_STEP_TIMEOUT,
    )
    assert chain_runner._resolve_timeout(chain.steps[0]) == 0


def test_exit_code_124_is_timeout(
    tmp_path: _pathlib.Path, monkeypatch: _pytest.MonkeyPatch
) -> None:
    """Subprocess exit code 124 is classified as TIMEOUT."""

    class FakePopen:
        """Minimal fake Popen that exits with code 124."""

        def __init__(self, *_args: object, **_kwargs: object) -> None:
            self.pid = 12346
            self.returncode = 124

        def wait(self, timeout: int | None = None) -> int:
            del timeout
            self.returncode = 124
            return 124

    monkeypatch.setattr(_runner._subprocess, "Popen", FakePopen)

    toml = """
    [chain]
    name = "code-124"

    [[steps]]
    name = "impl"
    type = "implement"
    agent = "codex-cli"
    [steps.brief]
    source = "inline"
    text = "hello"
    """
    chain = _chain.load(_write_chain(tmp_path, toml))
    chain_runner = _runner.ChainRunner(
        chain_def=chain,
        output_dir=tmp_path / "output",
        working_dir=tmp_path,
    )
    results = chain_runner.run()
    assert results[0].status == _types.StepStatus.TIMEOUT
