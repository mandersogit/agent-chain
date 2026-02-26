"""Tests for the agent-chain CLI."""

import json as _json
import pathlib as _pathlib

import click.testing as _click_testing

import agent_chain as _agent_chain
import agent_chain.cli as _cli

_FIXTURES = _pathlib.Path(__file__).parent / "fixtures"


class TestCLISmoke:
    """CLI smoke tests."""

    def test_version_flag(self) -> None:
        """--version prints the current version string."""
        runner = _click_testing.CliRunner()
        result = runner.invoke(_cli.main, ["--version"])
        assert result.exit_code == 0
        assert _agent_chain.__version__ in result.output

    def test_help_flag(self) -> None:
        """--help prints usage information."""
        runner = _click_testing.CliRunner()
        result = runner.invoke(_cli.main, ["--help"])
        assert result.exit_code == 0
        assert "Multi-agent chain orchestration CLI" in result.output

    def test_run_help(self) -> None:
        """run --help prints usage for the run subcommand."""
        runner = _click_testing.CliRunner()
        result = runner.invoke(_cli.main, ["run", "--help"])
        assert result.exit_code == 0
        assert "CHAIN_FILE" in result.output

    def test_validate_help(self) -> None:
        """validate --help prints usage for the validate subcommand."""
        runner = _click_testing.CliRunner()
        result = runner.invoke(_cli.main, ["validate", "--help"])
        assert result.exit_code == 0
        assert "CHAIN_FILE" in result.output

    def test_report_help(self) -> None:
        """report --help prints usage for the report subcommand."""
        runner = _click_testing.CliRunner()
        result = runner.invoke(_cli.main, ["report", "--help"])
        assert result.exit_code == 0
        assert "OUTPUT_DIR" in result.output


class TestValidateCommand:
    """Tests for the validate subcommand."""

    def test_validate_valid_chain(self) -> None:
        """validate with a valid chain file exits 0 and reports success."""
        runner = _click_testing.CliRunner()
        result = runner.invoke(_cli.main, ["validate", str(_FIXTURES / "minimal_chain.toml")])
        assert result.exit_code == 0
        assert "Valid" in result.output

    def test_validate_invalid_toml(self, tmp_path: _pathlib.Path) -> None:
        """validate with invalid TOML exits non-zero."""
        bad_file = tmp_path / "bad.toml"
        bad_file.write_text("not valid toml {{{{")
        runner = _click_testing.CliRunner()
        result = runner.invoke(_cli.main, ["validate", str(bad_file)])
        assert result.exit_code != 0

    def test_validate_missing_fields(self, tmp_path: _pathlib.Path) -> None:
        """validate with missing required fields exits non-zero."""
        bad_file = tmp_path / "bad.toml"
        bad_file.write_text("[chain]\nname = 'test'\n")
        runner = _click_testing.CliRunner()
        result = runner.invoke(_cli.main, ["validate", str(bad_file)])
        assert result.exit_code != 0

    def test_validate_with_var(self, tmp_path: _pathlib.Path) -> None:
        """validate --var provides variables for template validation."""
        f = tmp_path / "chain.toml"
        f.write_text(
            '[chain]\nname = "test"\n'
            '[[steps]]\nname = "s1"\ntype = "implement"\nagent = "codex-cli"\n'
            '[steps.brief]\nsource = "inline"\ntext = "Use {{my_var}}"\n'
        )
        runner = _click_testing.CliRunner()
        result = runner.invoke(_cli.main, ["validate", str(f), "--var", "my_var=value"])
        assert result.exit_code == 0

    def test_validate_strict_fails_on_warnings(self) -> None:
        """validate --strict exits non-zero on warnings."""
        runner = _click_testing.CliRunner()
        # full_chain has steps without gates -> warnings
        result = runner.invoke(
            _cli.main,
            ["validate", "--strict", str(_FIXTURES / "full_chain.toml")],
        )
        assert result.exit_code != 0


class TestRunCommand:
    """Tests for the run subcommand."""

    def test_run_dry_run(self) -> None:
        """run --dry-run exits 0 without launching agents."""
        runner = _click_testing.CliRunner()
        result = runner.invoke(
            _cli.main,
            ["run", "--dry-run", str(_FIXTURES / "minimal_chain.toml")],
        )
        assert result.exit_code == 0

    def test_run_minimal_chain(self, tmp_path: _pathlib.Path) -> None:
        """run with minimal chain creates report output."""
        runner = _click_testing.CliRunner()
        output_dir = str(tmp_path / "output")
        result = runner.invoke(
            _cli.main,
            [
                "run",
                "-o", output_dir,
                str(_FIXTURES / "minimal_chain.toml"),
            ],
        )
        assert result.exit_code == 0
        assert (tmp_path / "output" / "report.json").exists()
        assert (tmp_path / "output" / "DONE").exists()


class TestReportCommand:
    """Tests for the report subcommand."""

    def test_report_on_completed_chain(self, tmp_path: _pathlib.Path) -> None:
        """report reads report.json and renders it."""
        # First run a chain to generate a report
        cli_runner = _click_testing.CliRunner()
        output_dir = str(tmp_path / "output")
        cli_runner.invoke(
            _cli.main,
            ["run", "-o", output_dir, str(_FIXTURES / "minimal_chain.toml")],
        )
        assert (tmp_path / "output" / "report.json").exists()

        result = cli_runner.invoke(_cli.main, ["report", output_dir])
        assert result.exit_code == 0
        assert "minimal" in result.output

    def test_report_json_format(self, tmp_path: _pathlib.Path) -> None:
        """report --format json outputs valid JSON."""
        cli_runner = _click_testing.CliRunner()
        output_dir = str(tmp_path / "output")
        cli_runner.invoke(
            _cli.main,
            ["run", "-o", output_dir, str(_FIXTURES / "minimal_chain.toml")],
        )

        result = cli_runner.invoke(
            _cli.main, ["report", "--format", "json", output_dir]
        )
        assert result.exit_code == 0
        data = _json.loads(result.output)
        assert data["schema_version"] == 1

    def test_report_missing_report_json(self, tmp_path: _pathlib.Path) -> None:
        """report exits non-zero if report.json doesn't exist."""
        cli_runner = _click_testing.CliRunner()
        result = cli_runner.invoke(_cli.main, ["report", str(tmp_path)])
        assert result.exit_code != 0
