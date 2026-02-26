"""Tests for the codex-cli backend."""

import pathlib as _pathlib

import agent_chain.backends.codex_cli as _codex_cli
import agent_chain.types as _types

_FIXTURES = _pathlib.Path(__file__).parent.parent / "fixtures"


class TestCodexBuildCommand:
    """Tests for CodexCliBackend.build_command()."""

    def test_full_auto_default(self) -> None:
        """Default sandbox mode is full-auto."""
        backend = _codex_cli.CodexCliBackend()
        cmd = backend.build_command(
            brief_path=_pathlib.Path("/tmp/brief.md"),
            step_output_dir=_pathlib.Path("/tmp/out"),
            working_dir=_pathlib.Path("/tmp/project"),
            config=_types.StepConfig(),
        )
        assert "--full-auto" in cmd
        assert "--sandbox" not in cmd

    def test_read_only_sandbox(self) -> None:
        """sandbox='read-only' produces --sandbox read-only flags."""
        backend = _codex_cli.CodexCliBackend()
        config = _types.StepConfig(sandbox="read-only")
        cmd = backend.build_command(
            brief_path=_pathlib.Path("/tmp/brief.md"),
            step_output_dir=_pathlib.Path("/tmp/out"),
            working_dir=_pathlib.Path("/tmp/project"),
            config=config,
        )
        assert "--sandbox" in cmd
        idx = cmd.index("--sandbox")
        assert cmd[idx + 1] == "read-only"
        assert "--full-auto" not in cmd

    def test_reasoning_effort(self) -> None:
        """reasoning_effort is passed via -c flag."""
        backend = _codex_cli.CodexCliBackend()
        config = _types.StepConfig(reasoning_effort="high")
        cmd = backend.build_command(
            brief_path=_pathlib.Path("/tmp/brief.md"),
            step_output_dir=_pathlib.Path("/tmp/out"),
            working_dir=_pathlib.Path("/tmp/project"),
            config=config,
        )
        assert "-c" in cmd
        idx = cmd.index("-c")
        assert cmd[idx + 1] == "model_reasoning_effort=high"

    def test_output_schema_flag(self) -> None:
        """output_schema produces --output-schema flag."""
        backend = _codex_cli.CodexCliBackend()
        config = _types.StepConfig(output_schema="/tmp/schema.json")
        cmd = backend.build_command(
            brief_path=_pathlib.Path("/tmp/brief.md"),
            step_output_dir=_pathlib.Path("/tmp/out"),
            working_dir=_pathlib.Path("/tmp/project"),
            config=config,
        )
        assert "--output-schema" in cmd
        idx = cmd.index("--output-schema")
        assert cmd[idx + 1] == "/tmp/schema.json"

    def test_extra_flags_appended(self) -> None:
        """extra_flags are appended to the command."""
        backend = _codex_cli.CodexCliBackend()
        config = _types.StepConfig(extra_flags=["--verbose", "--debug"])
        cmd = backend.build_command(
            brief_path=_pathlib.Path("/tmp/brief.md"),
            step_output_dir=_pathlib.Path("/tmp/out"),
            working_dir=_pathlib.Path("/tmp/project"),
            config=config,
        )
        assert "--verbose" in cmd
        assert "--debug" in cmd

    def test_working_dir_passed(self) -> None:
        """Working directory is passed via -C flag."""
        backend = _codex_cli.CodexCliBackend()
        cmd = backend.build_command(
            brief_path=_pathlib.Path("/tmp/brief.md"),
            step_output_dir=_pathlib.Path("/tmp/out"),
            working_dir=_pathlib.Path("/home/user/project"),
            config=_types.StepConfig(),
        )
        assert "-C" in cmd
        idx = cmd.index("-C")
        assert cmd[idx + 1] == "/home/user/project"

    def test_stdin_marker(self) -> None:
        """Command ends with '-' for stdin input."""
        backend = _codex_cli.CodexCliBackend()
        cmd = backend.build_command(
            brief_path=_pathlib.Path("/tmp/brief.md"),
            step_output_dir=_pathlib.Path("/tmp/out"),
            working_dir=_pathlib.Path("/tmp/project"),
            config=_types.StepConfig(),
        )
        assert cmd[-1] == "-"

    def test_json_flag_present(self) -> None:
        """--json flag is always present."""
        backend = _codex_cli.CodexCliBackend()
        cmd = backend.build_command(
            brief_path=_pathlib.Path("/tmp/brief.md"),
            step_output_dir=_pathlib.Path("/tmp/out"),
            working_dir=_pathlib.Path("/tmp/project"),
            config=_types.StepConfig(),
        )
        assert "--json" in cmd


class TestCodexParseTelemetry:
    """Tests for CodexCliBackend.parse_telemetry()."""

    def test_parse_sample_events(self) -> None:
        """Parses fixture events.jsonl correctly."""
        backend = _codex_cli.CodexCliBackend()
        record = backend.parse_telemetry(_FIXTURES / "codex_events.jsonl", 100.0)

        # 3 turn.completed events:
        # input: 5000+8000+4000 = 17000
        # cached: 3000+6000+2500 = 11500
        # output: 1500+2000+1000 = 4500
        # fresh = 17000 - 11500 = 5500
        assert record["total_input_tokens"] == 17000
        assert record["cached_input_tokens"] == 11500
        assert record["fresh_input_tokens"] == 5500
        assert record["output_tokens"] == 4500
        assert record["num_turns"] == 3
        assert record["wall_time_seconds"] == 100.0
        assert record["shadow_cost_usd"] is None

    def test_parse_empty_file(self, tmp_path: _pathlib.Path) -> None:
        """Empty telemetry file produces zero counts."""
        empty = tmp_path / "empty.jsonl"
        empty.write_text("")
        backend = _codex_cli.CodexCliBackend()
        record = backend.parse_telemetry(empty, 50.0)
        assert record["total_input_tokens"] == 0
        assert record["num_turns"] == 0
        assert record["wall_time_seconds"] == 50.0

    def test_parse_nonexistent_file(self, tmp_path: _pathlib.Path) -> None:
        """Non-existent telemetry file produces zero counts."""
        backend = _codex_cli.CodexCliBackend()
        record = backend.parse_telemetry(tmp_path / "missing.jsonl", 30.0)
        assert record["num_turns"] == 0
        assert record["wall_time_seconds"] == 30.0


class TestCodexFileNames:
    """Tests for CodexCliBackend output/telemetry file names."""

    def test_output_file_with_schema(self) -> None:
        """output_file_name returns output.json when output_schema is set."""
        backend = _codex_cli.CodexCliBackend()
        config = _types.StepConfig(output_schema="/tmp/schema.json")
        assert backend.output_file_name(config) == "output.json"

    def test_output_file_without_schema(self) -> None:
        """output_file_name returns output.md when no output_schema."""
        backend = _codex_cli.CodexCliBackend()
        assert backend.output_file_name(_types.StepConfig()) == "output.md"

    def test_telemetry_file_name(self) -> None:
        """telemetry_file_name is always events.jsonl."""
        backend = _codex_cli.CodexCliBackend()
        assert backend.telemetry_file_name() == "events.jsonl"
