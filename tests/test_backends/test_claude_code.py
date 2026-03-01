"""Tests for the Claude Code backend."""

import pathlib as _pathlib

import agent_chain.backends.claude_code as _claude_code
import agent_chain.types as _types

_FIXTURES = _pathlib.Path(__file__).parent.parent / "fixtures"


class TestClaudeCodeBuildCommand:
    """Tests for ClaudeCodeBackend.build_command()."""

    def test_default_model_sonnet(self) -> None:
        """Default model is sonnet."""
        backend = _claude_code.ClaudeCodeBackend()
        cmd = backend.build_command(
            brief_path=_pathlib.Path("/tmp/brief.md"),
            step_output_dir=_pathlib.Path("/tmp/out"),
            working_dir=_pathlib.Path("/tmp/project"),
            config=_types.StepConfig(),
        )
        idx = cmd.index("--model")
        assert cmd[idx + 1] == "sonnet"

    def test_opus_model(self) -> None:
        """model='opus' produces --model opus."""
        backend = _claude_code.ClaudeCodeBackend()
        config = _types.StepConfig(model="opus")
        cmd = backend.build_command(
            brief_path=_pathlib.Path("/tmp/brief.md"),
            step_output_dir=_pathlib.Path("/tmp/out"),
            working_dir=_pathlib.Path("/tmp/project"),
            config=config,
        )
        idx = cmd.index("--model")
        assert cmd[idx + 1] == "opus"

    def test_plan_permission_mode(self) -> None:
        """permission_mode='plan' produces --permission-mode plan."""
        backend = _claude_code.ClaudeCodeBackend()
        config = _types.StepConfig(permission_mode="plan")
        cmd = backend.build_command(
            brief_path=_pathlib.Path("/tmp/brief.md"),
            step_output_dir=_pathlib.Path("/tmp/out"),
            working_dir=_pathlib.Path("/tmp/project"),
            config=config,
        )
        assert "--permission-mode" in cmd
        idx = cmd.index("--permission-mode")
        assert cmd[idx + 1] == "plan"
        assert "--dangerously-skip-permissions" not in cmd

    def test_dangerously_skip_default(self) -> None:
        """Default permission mode produces --dangerously-skip-permissions."""
        backend = _claude_code.ClaudeCodeBackend()
        cmd = backend.build_command(
            brief_path=_pathlib.Path("/tmp/brief.md"),
            step_output_dir=_pathlib.Path("/tmp/out"),
            working_dir=_pathlib.Path("/tmp/project"),
            config=_types.StepConfig(),
        )
        assert "--dangerously-skip-permissions" in cmd

    def test_max_turns_omitted_by_default(self) -> None:
        """--max-turns is omitted when max_turns is not explicitly configured."""
        backend = _claude_code.ClaudeCodeBackend()
        cmd = backend.build_command(
            brief_path=_pathlib.Path("/tmp/brief.md"),
            step_output_dir=_pathlib.Path("/tmp/out"),
            working_dir=_pathlib.Path("/tmp/project"),
            config=_types.StepConfig(),
        )
        assert "--max-turns" not in cmd

    def test_max_turns_explicit(self) -> None:
        """Explicit max_turns is passed via --max-turns."""
        backend = _claude_code.ClaudeCodeBackend()
        config = _types.StepConfig(max_turns=80)
        cmd = backend.build_command(
            brief_path=_pathlib.Path("/tmp/brief.md"),
            step_output_dir=_pathlib.Path("/tmp/out"),
            working_dir=_pathlib.Path("/tmp/project"),
            config=config,
        )
        idx = cmd.index("--max-turns")
        assert cmd[idx + 1] == "80"

    def test_effort_flag(self) -> None:
        """effort is passed via --effort."""
        backend = _claude_code.ClaudeCodeBackend()
        config = _types.StepConfig(effort="low")
        cmd = backend.build_command(
            brief_path=_pathlib.Path("/tmp/brief.md"),
            step_output_dir=_pathlib.Path("/tmp/out"),
            working_dir=_pathlib.Path("/tmp/project"),
            config=config,
        )
        idx = cmd.index("--effort")
        assert cmd[idx + 1] == "low"

    def test_pipe_mode_flag(self) -> None:
        """-p flag is always present for non-interactive mode."""
        backend = _claude_code.ClaudeCodeBackend()
        cmd = backend.build_command(
            brief_path=_pathlib.Path("/tmp/brief.md"),
            step_output_dir=_pathlib.Path("/tmp/out"),
            working_dir=_pathlib.Path("/tmp/project"),
            config=_types.StepConfig(),
        )
        assert "-p" in cmd

    def test_output_format_json(self) -> None:
        """--output-format json is always present."""
        backend = _claude_code.ClaudeCodeBackend()
        cmd = backend.build_command(
            brief_path=_pathlib.Path("/tmp/brief.md"),
            step_output_dir=_pathlib.Path("/tmp/out"),
            working_dir=_pathlib.Path("/tmp/project"),
            config=_types.StepConfig(),
        )
        assert "--output-format" in cmd
        idx = cmd.index("--output-format")
        assert cmd[idx + 1] == "json"

    def test_extra_flags(self) -> None:
        """Extra flags are appended to the command."""
        backend = _claude_code.ClaudeCodeBackend()
        config = _types.StepConfig(extra_flags=["--continue", "--verbose"])
        cmd = backend.build_command(
            brief_path=_pathlib.Path("/tmp/brief.md"),
            step_output_dir=_pathlib.Path("/tmp/out"),
            working_dir=_pathlib.Path("/tmp/project"),
            config=config,
        )
        assert "--continue" in cmd
        assert "--verbose" in cmd


class TestClaudeCodeParseTelemetry:
    """Tests for ClaudeCodeBackend.parse_telemetry()."""

    def test_parse_sample_raw_json(self) -> None:
        """Parses fixture raw.json correctly."""
        backend = _claude_code.ClaudeCodeBackend()
        record = backend.parse_telemetry(_FIXTURES / "claude_raw.json", 999.0)

        # fresh = 150, cache_write = 250000, cache_read = 3000000
        # cached = 250000 + 3000000 = 3250000
        # total = 150 + 3250000 = 3250150
        assert record["fresh_input_tokens"] == 150
        assert record["cached_input_tokens"] == 3250000
        assert record["total_input_tokens"] == 3250150
        assert record["output_tokens"] == 25000
        assert record["num_turns"] == 35
        # duration_ms = 120350 -> 120.35s (uses file value, not wall_time arg)
        assert record["wall_time_seconds"] == 120.35
        assert record["shadow_cost_usd"] == 2.99

    def test_parse_nonexistent_file(self, tmp_path: _pathlib.Path) -> None:
        """Non-existent file produces zero counts and tokens_available=False."""
        backend = _claude_code.ClaudeCodeBackend()
        record = backend.parse_telemetry(tmp_path / "missing.json", 60.0)
        assert record["total_input_tokens"] == 0
        assert record["num_turns"] == 0
        assert record["wall_time_seconds"] == 60.0
        assert record["tokens_available"] is False

    def test_parse_no_duration_ms_uses_wall_time(self, tmp_path: _pathlib.Path) -> None:
        """When duration_ms is absent, falls back to wall_time_seconds arg."""
        import json as _json

        data = {
            "usage": {"input_tokens": 100, "output_tokens": 200},
            "num_turns": 5,
        }
        f = tmp_path / "raw.json"
        f.write_text(_json.dumps(data))
        backend = _claude_code.ClaudeCodeBackend()
        record = backend.parse_telemetry(f, 42.5)
        assert record["wall_time_seconds"] == 42.5

    def test_parse_missing_usage_fields(self, tmp_path: _pathlib.Path) -> None:
        """Missing usage sub-fields default to zero."""
        import json as _json

        data = {"usage": {}, "num_turns": 1, "duration_ms": 5000}
        f = tmp_path / "raw.json"
        f.write_text(_json.dumps(data))
        backend = _claude_code.ClaudeCodeBackend()
        record = backend.parse_telemetry(f, 10.0)
        assert record["fresh_input_tokens"] == 0
        assert record["cached_input_tokens"] == 0
        assert record["output_tokens"] == 0


class TestClaudeCodeFileNames:
    """Tests for ClaudeCodeBackend output/telemetry file names."""

    def test_output_file_name(self) -> None:
        """Output file is always raw.json for Claude Code."""
        backend = _claude_code.ClaudeCodeBackend()
        assert backend.output_file_name(_types.StepConfig()) == "raw.json"

    def test_telemetry_file_name(self) -> None:
        """Telemetry file is always raw.json for Claude Code."""
        backend = _claude_code.ClaudeCodeBackend()
        assert backend.telemetry_file_name() == "raw.json"
