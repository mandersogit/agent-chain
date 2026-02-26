"""Tests for the chain runner."""

import pathlib as _pathlib
import textwrap as _textwrap

import agent_chain.chain as _chain
import agent_chain.runner as _runner
import agent_chain.types as _types

_FIXTURES = _pathlib.Path(__file__).parent / "fixtures"


def _write_chain(tmp_path: _pathlib.Path, toml: str) -> _pathlib.Path:
    f = tmp_path / "chain.toml"
    f.write_text(toml)
    return f


class TestRunnerDryRun:
    """Tests for ChainRunner dry-run mode."""

    def test_dry_run_returns_success_for_all_steps(self, tmp_path: _pathlib.Path) -> None:
        """Dry run produces SUCCESS for all steps without launching processes."""
        chain = _chain.load(_FIXTURES / "minimal_chain.toml")
        output_dir = tmp_path / "output"
        runner = _runner.ChainRunner(
            chain_def=chain,
            output_dir=output_dir,
            working_dir=tmp_path,
            dry_run=True,
        )
        results = runner.run()
        assert len(results) == 1
        assert results[0].status == _types.StepStatus.SUCCESS

    def test_dry_run_does_not_create_report(self, tmp_path: _pathlib.Path) -> None:
        """Dry run does not create report.json or DONE sentinel."""
        chain = _chain.load(_FIXTURES / "minimal_chain.toml")
        output_dir = tmp_path / "output"
        runner = _runner.ChainRunner(
            chain_def=chain,
            output_dir=output_dir,
            working_dir=tmp_path,
            dry_run=True,
        )
        runner.run()
        assert not (output_dir / "report.json").exists()
        assert not (output_dir / "DONE").exists()

    def test_dry_run_full_chain(self, tmp_path: _pathlib.Path) -> None:
        """Dry run of full pipeline produces SUCCESS for all 5 steps."""
        chain = _chain.load(_FIXTURES / "full_chain.toml")
        output_dir = tmp_path / "output"
        runner = _runner.ChainRunner(
            chain_def=chain,
            output_dir=output_dir,
            working_dir=tmp_path,
            dry_run=True,
        )
        results = runner.run()
        assert len(results) == 5
        assert all(r.status == _types.StepStatus.SUCCESS for r in results)


class TestRunnerVerifyStep:
    """Tests for running verify steps (noop agent + gate)."""

    def test_verify_step_gate_passes(self, tmp_path: _pathlib.Path) -> None:
        """Verify step with passing gate command produces SUCCESS."""
        toml = _textwrap.dedent("""\
            [chain]
            name = "verify-test"
            [[steps]]
            name = "check"
            type = "verify"
            agent = "none"
            [steps.gate]
            command = "true"
        """)
        chain = _chain.load(_write_chain(tmp_path, toml))
        output_dir = tmp_path / "output"
        runner = _runner.ChainRunner(
            chain_def=chain,
            output_dir=output_dir,
            working_dir=tmp_path,
        )
        results = runner.run()
        assert len(results) == 1
        assert results[0].status == _types.StepStatus.SUCCESS
        assert results[0].gate_result is not None
        assert results[0].gate_result["passed"] is True

    def test_verify_step_gate_fails_aborts(self, tmp_path: _pathlib.Path) -> None:
        """Verify step with failing gate command and default on_failure='abort' aborts."""
        toml = _textwrap.dedent("""\
            [chain]
            name = "gate-fail"
            [[steps]]
            name = "check"
            type = "verify"
            agent = "none"
            [steps.gate]
            command = "false"
            [[steps]]
            name = "next"
            type = "verify"
            agent = "none"
            [steps.gate]
            command = "true"
        """)
        chain = _chain.load(_write_chain(tmp_path, toml))
        output_dir = tmp_path / "output"
        runner = _runner.ChainRunner(
            chain_def=chain,
            output_dir=output_dir,
            working_dir=tmp_path,
        )
        results = runner.run()
        assert results[0].status == _types.StepStatus.GATE_FAILED
        assert results[1].status == _types.StepStatus.NOT_STARTED

    def test_verify_step_gate_warn_continues(self, tmp_path: _pathlib.Path) -> None:
        """Gate failure with on_failure='warn' continues to next step."""
        toml = _textwrap.dedent("""\
            [chain]
            name = "gate-warn"
            [[steps]]
            name = "check"
            type = "verify"
            agent = "none"
            [steps.gate]
            command = "false"
            on_failure = "warn"
            [[steps]]
            name = "next"
            type = "verify"
            agent = "none"
            [steps.gate]
            command = "true"
        """)
        chain = _chain.load(_write_chain(tmp_path, toml))
        output_dir = tmp_path / "output"
        runner = _runner.ChainRunner(
            chain_def=chain,
            output_dir=output_dir,
            working_dir=tmp_path,
            verbose=True,
        )
        results = runner.run()
        assert results[0].status == _types.StepStatus.GATE_FAILED
        assert results[1].status == _types.StepStatus.SUCCESS

    def test_verify_step_gate_skip_continues(self, tmp_path: _pathlib.Path) -> None:
        """Gate failure with on_failure='skip' continues to next step."""
        toml = _textwrap.dedent("""\
            [chain]
            name = "gate-skip"
            [[steps]]
            name = "check"
            type = "verify"
            agent = "none"
            [steps.gate]
            command = "false"
            on_failure = "skip"
            [[steps]]
            name = "next"
            type = "verify"
            agent = "none"
            [steps.gate]
            command = "true"
        """)
        chain = _chain.load(_write_chain(tmp_path, toml))
        output_dir = tmp_path / "output"
        runner = _runner.ChainRunner(
            chain_def=chain,
            output_dir=output_dir,
            working_dir=tmp_path,
        )
        results = runner.run()
        assert results[0].status == _types.StepStatus.GATE_FAILED
        assert results[1].status == _types.StepStatus.SUCCESS


class TestRunnerEdgeCases:
    """Edge cases for chain runner execution."""

    def test_empty_chain_completes_gracefully(self, tmp_path: _pathlib.Path) -> None:
        """Runner handles an empty chain definition without crashing."""
        chain = _chain.ChainDefinition(
            name="empty",
            description="",
            default_timeout=1800,
            working_dir=None,
            variables={},
            steps=[],
            source_path=tmp_path / "empty.toml",
        )
        output_dir = tmp_path / "output"
        runner = _runner.ChainRunner(
            chain_def=chain,
            output_dir=output_dir,
            working_dir=tmp_path,
        )
        results = runner.run()
        assert results == []
        assert (output_dir / "report.json").exists()
        assert (output_dir / "DONE").read_text().strip() == "success"

    def test_all_warn_gate_failures_complete_with_warnings(
        self, tmp_path: _pathlib.Path
    ) -> None:
        """All gate failures with on_failure='warn' run all steps and end with warnings."""
        toml = _textwrap.dedent("""\
            [chain]
            name = "all-warn-failures"
            [[steps]]
            name = "check-1"
            type = "verify"
            agent = "none"
            [steps.gate]
            command = "false"
            on_failure = "warn"
            [[steps]]
            name = "check-2"
            type = "verify"
            agent = "none"
            [steps.gate]
            command = "false"
            on_failure = "warn"
            [[steps]]
            name = "check-3"
            type = "verify"
            agent = "none"
            [steps.gate]
            command = "false"
            on_failure = "warn"
        """)
        chain = _chain.load(_write_chain(tmp_path, toml))
        output_dir = tmp_path / "output"
        runner = _runner.ChainRunner(
            chain_def=chain,
            output_dir=output_dir,
            working_dir=tmp_path,
        )
        results = runner.run()
        assert len(results) == 3
        assert all(r.status == _types.StepStatus.GATE_FAILED for r in results)
        assert all(r.gate_result is not None and not r.gate_result["passed"] for r in results)
        assert (output_dir / "DONE").read_text().strip() == "success_warnings"

    def test_missing_brief_file_sets_config_error(self, tmp_path: _pathlib.Path) -> None:
        """A missing brief file path marks the step as CONFIG_ERROR."""
        toml = _textwrap.dedent("""\
            [chain]
            name = "missing-brief"
            [[steps]]
            name = "impl"
            type = "implement"
            agent = "codex-cli"
            [steps.brief]
            source = "file"
            path = "does-not-exist.md"
        """)
        chain = _chain.load(_write_chain(tmp_path, toml))
        output_dir = tmp_path / "output"
        runner = _runner.ChainRunner(
            chain_def=chain,
            output_dir=output_dir,
            working_dir=tmp_path,
        )
        results = runner.run()
        assert len(results) == 1
        assert results[0].status == _types.StepStatus.CONFIG_ERROR

    def test_first_step_abort_gate_failure_marks_remaining_not_started(
        self, tmp_path: _pathlib.Path
    ) -> None:
        """First-step gate abort leaves all later steps NOT_STARTED."""
        toml = _textwrap.dedent("""\
            [chain]
            name = "abort-first-gate"
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
            command = "true"
            [[steps]]
            name = "third"
            type = "verify"
            agent = "none"
            [steps.gate]
            command = "true"
        """)
        chain = _chain.load(_write_chain(tmp_path, toml))
        output_dir = tmp_path / "output"
        runner = _runner.ChainRunner(
            chain_def=chain,
            output_dir=output_dir,
            working_dir=tmp_path,
        )
        results = runner.run()
        assert len(results) == 3
        assert results[0].status == _types.StepStatus.GATE_FAILED
        assert results[1].status == _types.StepStatus.NOT_STARTED
        assert results[2].status == _types.StepStatus.NOT_STARTED


class TestRunnerWithRealSubprocess:
    """Tests with real subprocess for agent steps (using echo as a mock agent)."""

    def test_successful_step_with_echo_agent(self, tmp_path: _pathlib.Path) -> None:
        """Step using a real subprocess (echo) completes successfully."""
        toml = _textwrap.dedent("""\
            [chain]
            name = "echo-test"
            [[steps]]
            name = "step1"
            type = "implement"
            agent = "codex-cli"
            [steps.brief]
            source = "inline"
            text = "hello"
        """)
        chain = _chain.load(_write_chain(tmp_path, toml))

        import os as _os
        _os.environ["AGENT_CHAIN_CODEX_BIN"] = "/bin/echo"
        try:
            output_dir = tmp_path / "output"
            runner = _runner.ChainRunner(
                chain_def=chain,
                output_dir=output_dir,
                working_dir=tmp_path,
            )
            results = runner.run()
            assert results[0].status == _types.StepStatus.SUCCESS
            assert results[0].exit_code == 0
        finally:
            del _os.environ["AGENT_CHAIN_CODEX_BIN"]

    def test_failed_step_aborts_chain(self, tmp_path: _pathlib.Path) -> None:
        """Step with non-zero exit aborts the chain, remaining steps NOT_STARTED."""
        toml = _textwrap.dedent("""\
            [chain]
            name = "fail-test"
            [[steps]]
            name = "failing"
            type = "implement"
            agent = "codex-cli"
            [steps.brief]
            source = "inline"
            text = "fail"
            [[steps]]
            name = "next"
            type = "verify"
            agent = "none"
            [steps.gate]
            command = "true"
        """)
        chain = _chain.load(_write_chain(tmp_path, toml))

        import os as _os
        _os.environ["AGENT_CHAIN_CODEX_BIN"] = "/bin/false"
        try:
            output_dir = tmp_path / "output"
            runner = _runner.ChainRunner(
                chain_def=chain,
                output_dir=output_dir,
                working_dir=tmp_path,
            )
            results = runner.run()
            assert results[0].status == _types.StepStatus.FAILED
            assert results[1].status == _types.StepStatus.NOT_STARTED
        finally:
            del _os.environ["AGENT_CHAIN_CODEX_BIN"]

    def test_timeout_kills_subprocess(self, tmp_path: _pathlib.Path) -> None:
        """Step exceeding timeout is terminated and marked TIMEOUT."""
        # Create a script that ignores its arguments and sleeps
        script = tmp_path / "slow-agent"
        script.write_text("#!/bin/sh\nsleep 300\n")
        script.chmod(0o755)

        toml = _textwrap.dedent("""\
            [chain]
            name = "timeout-test"
            [[steps]]
            name = "slow"
            type = "implement"
            agent = "codex-cli"
            [steps.brief]
            source = "inline"
            text = "slow"
            [steps.agent_config]
            timeout = 1
        """)
        chain = _chain.load(_write_chain(tmp_path, toml))

        import os as _os
        _os.environ["AGENT_CHAIN_CODEX_BIN"] = str(script)
        try:
            output_dir = tmp_path / "output"
            runner = _runner.ChainRunner(
                chain_def=chain,
                output_dir=output_dir,
                working_dir=tmp_path,
            )
            results = runner.run()
            assert results[0].status == _types.StepStatus.TIMEOUT
        finally:
            del _os.environ["AGENT_CHAIN_CODEX_BIN"]


class TestRunnerReportGeneration:
    """Tests for report generation by the runner."""

    def test_report_and_sentinel_created(self, tmp_path: _pathlib.Path) -> None:
        """Successful chain run creates report.json and DONE sentinel."""
        chain = _chain.load(_FIXTURES / "minimal_chain.toml")
        output_dir = tmp_path / "output"
        runner = _runner.ChainRunner(
            chain_def=chain,
            output_dir=output_dir,
            working_dir=tmp_path,
        )
        runner.run()
        assert (output_dir / "report.json").exists()
        assert (output_dir / "DONE").exists()
        assert (output_dir / "DONE").read_text().strip() == "success"

    def test_failed_chain_creates_partial_report(self, tmp_path: _pathlib.Path) -> None:
        """Failed chain still writes report.json and DONE with failure status."""
        toml = _textwrap.dedent("""\
            [chain]
            name = "fail-report"
            [[steps]]
            name = "check"
            type = "verify"
            agent = "none"
            [steps.gate]
            command = "false"
        """)
        chain = _chain.load(_write_chain(tmp_path, toml))
        output_dir = tmp_path / "output"
        runner = _runner.ChainRunner(
            chain_def=chain,
            output_dir=output_dir,
            working_dir=tmp_path,
        )
        runner.run()
        assert (output_dir / "report.json").exists()
        assert (output_dir / "DONE").exists()
        done_status = (output_dir / "DONE").read_text().strip()
        assert done_status in ("gate_failed", "failed")


class TestRunnerVariables:
    """Tests for variable resolution in the runner."""

    def test_builtin_variables_available(self, tmp_path: _pathlib.Path) -> None:
        """Built-in variables (chain.name, step.name, etc.) are available."""
        toml = _textwrap.dedent("""\
            [chain]
            name = "var-test"
            [[steps]]
            name = "check"
            type = "verify"
            agent = "none"
            [steps.gate]
            command = "echo {{chain.name}} {{step.name}}"
        """)
        chain = _chain.load(_write_chain(tmp_path, toml))
        output_dir = tmp_path / "output"
        runner = _runner.ChainRunner(
            chain_def=chain,
            output_dir=output_dir,
            working_dir=tmp_path,
        )
        results = runner.run()
        assert results[0].status == _types.StepStatus.SUCCESS

    def test_cli_vars_override_chain_vars(self, tmp_path: _pathlib.Path) -> None:
        """CLI --var values override [vars] table values."""
        toml = _textwrap.dedent("""\
            [chain]
            name = "override-test"
            [vars]
            greeting = "hello"
            [[steps]]
            name = "check"
            type = "verify"
            agent = "none"
            [steps.gate]
            command = "test '{{greeting}}' = 'overridden'"
        """)
        chain = _chain.load(_write_chain(tmp_path, toml))
        output_dir = tmp_path / "output"
        runner = _runner.ChainRunner(
            chain_def=chain,
            output_dir=output_dir,
            working_dir=tmp_path,
            cli_vars={"greeting": "overridden"},
        )
        results = runner.run()
        assert results[0].status == _types.StepStatus.SUCCESS
