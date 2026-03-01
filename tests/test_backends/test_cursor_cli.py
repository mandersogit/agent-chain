"""Tests for the cursor-cli backend."""

import pathlib as _pathlib
import unittest.mock as _mock

import pytest as _pytest

import agent_chain.backends as _backends
import agent_chain.backends.cursor_cli as _cursor_cli
import agent_chain.types as _types

_FIXTURES = _pathlib.Path(__file__).parent.parent / "fixtures"


class TestCursorCliBuildCommand:
    """Tests for CursorCliBackend.build_command()."""

    def test_default_command_structure(self, monkeypatch: _pytest.MonkeyPatch) -> None:
        """Default command has exec mode, stream-json, workspace, and stdin marker."""
        monkeypatch.setenv("AGENT_CHAIN_CURSOR_BIN", "/tmp/cursor-wrapper")
        backend = _cursor_cli.CursorCliBackend()
        cmd = backend.build_command(
            brief_path=_pathlib.Path("/tmp/brief.md"),
            step_output_dir=_pathlib.Path("/tmp/out"),
            working_dir=_pathlib.Path("/tmp/project"),
            config=_types.StepConfig(),
        )
        assert cmd[0] == "/tmp/cursor-wrapper"
        assert "exec" in cmd
        assert "--output-format" in cmd
        assert cmd[cmd.index("--output-format") + 1] == "stream-json"
        assert "--workspace" in cmd
        assert cmd[cmd.index("--workspace") + 1] == "/tmp/project"
        assert cmd[-1] == "-"

    def test_model_flag(self, monkeypatch: _pytest.MonkeyPatch) -> None:
        """model is passed through via --model."""
        monkeypatch.setenv("AGENT_CHAIN_CURSOR_BIN", "/tmp/cursor-wrapper")
        backend = _cursor_cli.CursorCliBackend()
        cmd = backend.build_command(
            brief_path=_pathlib.Path("/tmp/brief.md"),
            step_output_dir=_pathlib.Path("/tmp/out"),
            working_dir=_pathlib.Path("/tmp/project"),
            config=_types.StepConfig(model="gemini-3-flash"),
        )
        idx = cmd.index("--model")
        assert cmd[idx + 1] == "gemini-3-flash"

    def test_force_default_true(self, monkeypatch: _pytest.MonkeyPatch) -> None:
        """Default force behavior does not include --no-force."""
        monkeypatch.setenv("AGENT_CHAIN_CURSOR_BIN", "/tmp/cursor-wrapper")
        backend = _cursor_cli.CursorCliBackend()
        cmd = backend.build_command(
            brief_path=_pathlib.Path("/tmp/brief.md"),
            step_output_dir=_pathlib.Path("/tmp/out"),
            working_dir=_pathlib.Path("/tmp/project"),
            config=_types.StepConfig(),
        )
        assert "--no-force" not in cmd

    def test_force_false_review_mode(self, monkeypatch: _pytest.MonkeyPatch) -> None:
        """force=False produces --no-force."""
        monkeypatch.setenv("AGENT_CHAIN_CURSOR_BIN", "/tmp/cursor-wrapper")
        backend = _cursor_cli.CursorCliBackend()
        cmd = backend.build_command(
            brief_path=_pathlib.Path("/tmp/brief.md"),
            step_output_dir=_pathlib.Path("/tmp/out"),
            working_dir=_pathlib.Path("/tmp/project"),
            config=_types.StepConfig(force=False),
        )
        assert "--no-force" in cmd

    def test_force_defaults_false_for_plan_mode(self, monkeypatch: _pytest.MonkeyPatch) -> None:
        """force defaults to False when mode is plan, avoiding spurious warnings."""
        monkeypatch.setenv("AGENT_CHAIN_CURSOR_BIN", "/tmp/cursor-wrapper")
        backend = _cursor_cli.CursorCliBackend()
        cmd = backend.build_command(
            brief_path=_pathlib.Path("/tmp/brief.md"),
            step_output_dir=_pathlib.Path("/tmp/out"),
            working_dir=_pathlib.Path("/tmp/project"),
            config=_types.StepConfig(mode="plan"),
        )
        assert "--no-force" in cmd
        assert "--force" not in cmd

    def test_force_defaults_false_for_ask_mode(self, monkeypatch: _pytest.MonkeyPatch) -> None:
        """force defaults to False when mode is ask, avoiding spurious warnings."""
        monkeypatch.setenv("AGENT_CHAIN_CURSOR_BIN", "/tmp/cursor-wrapper")
        backend = _cursor_cli.CursorCliBackend()
        cmd = backend.build_command(
            brief_path=_pathlib.Path("/tmp/brief.md"),
            step_output_dir=_pathlib.Path("/tmp/out"),
            working_dir=_pathlib.Path("/tmp/project"),
            config=_types.StepConfig(mode="ask"),
        )
        assert "--no-force" in cmd
        assert "--force" not in cmd

    def test_force_explicit_true_overrides_plan_mode(
        self, monkeypatch: _pytest.MonkeyPatch
    ) -> None:
        """Explicit force=True still applies even with mode=plan."""
        monkeypatch.setenv("AGENT_CHAIN_CURSOR_BIN", "/tmp/cursor-wrapper")
        backend = _cursor_cli.CursorCliBackend()
        cmd = backend.build_command(
            brief_path=_pathlib.Path("/tmp/brief.md"),
            step_output_dir=_pathlib.Path("/tmp/out"),
            working_dir=_pathlib.Path("/tmp/project"),
            config=_types.StepConfig(mode="plan", force=True),
        )
        assert "--force" in cmd
        assert "--no-force" not in cmd

    def test_mode_plan(self, monkeypatch: _pytest.MonkeyPatch) -> None:
        """mode='plan' is passed via --mode plan."""
        monkeypatch.setenv("AGENT_CHAIN_CURSOR_BIN", "/tmp/cursor-wrapper")
        backend = _cursor_cli.CursorCliBackend()
        cmd = backend.build_command(
            brief_path=_pathlib.Path("/tmp/brief.md"),
            step_output_dir=_pathlib.Path("/tmp/out"),
            working_dir=_pathlib.Path("/tmp/project"),
            config=_types.StepConfig(mode="plan"),
        )
        idx = cmd.index("--mode")
        assert cmd[idx + 1] == "plan"

    def test_sandbox_flag(self, monkeypatch: _pytest.MonkeyPatch) -> None:
        """sandbox is passed through via --sandbox."""
        monkeypatch.setenv("AGENT_CHAIN_CURSOR_BIN", "/tmp/cursor-wrapper")
        backend = _cursor_cli.CursorCliBackend()
        cmd = backend.build_command(
            brief_path=_pathlib.Path("/tmp/brief.md"),
            step_output_dir=_pathlib.Path("/tmp/out"),
            working_dir=_pathlib.Path("/tmp/project"),
            config=_types.StepConfig(sandbox="enabled"),
        )
        idx = cmd.index("--sandbox")
        assert cmd[idx + 1] == "enabled"

    def test_max_turns_ignored_with_warning(
        self, monkeypatch: _pytest.MonkeyPatch, capsys: _pytest.CaptureFixture[str]
    ) -> None:
        """max_turns is ignored because cursor-agent does not support it."""
        monkeypatch.setenv("AGENT_CHAIN_CURSOR_BIN", "/tmp/cursor-wrapper")
        backend = _cursor_cli.CursorCliBackend()
        cmd = backend.build_command(
            brief_path=_pathlib.Path("/tmp/brief.md"),
            step_output_dir=_pathlib.Path("/tmp/out"),
            working_dir=_pathlib.Path("/tmp/project"),
            config=_types.StepConfig(max_turns=12),
        )
        assert "--max-turns" not in cmd
        captured = capsys.readouterr()
        assert "max_turns ignored" in captured.err

    def test_timeout_propagation(self, monkeypatch: _pytest.MonkeyPatch) -> None:
        """timeout from config is passed to wrapper command."""
        monkeypatch.setenv("AGENT_CHAIN_CURSOR_BIN", "/tmp/cursor-wrapper")
        backend = _cursor_cli.CursorCliBackend()
        cmd = backend.build_command(
            brief_path=_pathlib.Path("/tmp/brief.md"),
            step_output_dir=_pathlib.Path("/tmp/out"),
            working_dir=_pathlib.Path("/tmp/project"),
            config=_types.StepConfig(timeout=321),
        )
        idx = cmd.index("--timeout")
        assert cmd[idx + 1] == "321"

    def test_extra_flags(self, monkeypatch: _pytest.MonkeyPatch) -> None:
        """extra_flags are forwarded as repeated --extra-flag values."""
        monkeypatch.setenv("AGENT_CHAIN_CURSOR_BIN", "/tmp/cursor-wrapper")
        backend = _cursor_cli.CursorCliBackend()
        cmd = backend.build_command(
            brief_path=_pathlib.Path("/tmp/brief.md"),
            step_output_dir=_pathlib.Path("/tmp/out"),
            working_dir=_pathlib.Path("/tmp/project"),
            config=_types.StepConfig(extra_flags=["--alpha", "--beta 2"]),
        )
        indices = [i for i, arg in enumerate(cmd) if arg == "--extra-flag"]
        assert len(indices) == 2
        assert cmd[indices[0] + 1] == "--alpha"
        assert cmd[indices[1] + 1] == "--beta 2"

    def test_build_command_invalid_field_types_raises_type_error(
        self, monkeypatch: _pytest.MonkeyPatch,
    ) -> None:
        """Invalid config field types raise TypeError."""
        monkeypatch.setenv("AGENT_CHAIN_CURSOR_BIN", "/tmp/cursor-wrapper")
        backend = _cursor_cli.CursorCliBackend()

        with _pytest.raises(TypeError):
            backend.build_command(
                brief_path=_pathlib.Path("/tmp/brief.md"),
                step_output_dir=_pathlib.Path("/tmp/out"),
                working_dir=_pathlib.Path("/tmp/project"),
                config=_types.StepConfig(model=123),  # type: ignore[arg-type]
            )

        # max_turns no longer raises TypeError — it's silently ignored with a warning
        # since cursor-agent doesn't support --max-turns.

        with _pytest.raises(TypeError):
            backend.build_command(
                brief_path=_pathlib.Path("/tmp/brief.md"),
                step_output_dir=_pathlib.Path("/tmp/out"),
                working_dir=_pathlib.Path("/tmp/project"),
                config=_types.StepConfig(force="no"),  # type: ignore[arg-type]
            )

        with _pytest.raises(TypeError):
            backend.build_command(
                brief_path=_pathlib.Path("/tmp/brief.md"),
                step_output_dir=_pathlib.Path("/tmp/out"),
                working_dir=_pathlib.Path("/tmp/project"),
                config=_types.StepConfig(timeout="20"),  # type: ignore[arg-type]
            )

        with _pytest.raises(TypeError):
            backend.build_command(
                brief_path=_pathlib.Path("/tmp/brief.md"),
                step_output_dir=_pathlib.Path("/tmp/out"),
                working_dir=_pathlib.Path("/tmp/project"),
                config=_types.StepConfig(extra_flags="--x"),  # type: ignore[arg-type]
            )

    def test_build_command_invalid_mode_or_sandbox_raises_value_error(
        self, monkeypatch: _pytest.MonkeyPatch
    ) -> None:
        """Invalid mode or sandbox string values raise ValueError."""
        monkeypatch.setenv("AGENT_CHAIN_CURSOR_BIN", "/tmp/cursor-wrapper")
        backend = _cursor_cli.CursorCliBackend()

        with _pytest.raises(ValueError, match="mode must be"):
            backend.build_command(
                brief_path=_pathlib.Path("/tmp/brief.md"),
                step_output_dir=_pathlib.Path("/tmp/out"),
                working_dir=_pathlib.Path("/tmp/project"),
                config=_types.StepConfig(mode="edit"),
            )

        with _pytest.raises(ValueError, match="sandbox must be"):
            backend.build_command(
                brief_path=_pathlib.Path("/tmp/brief.md"),
                step_output_dir=_pathlib.Path("/tmp/out"),
                working_dir=_pathlib.Path("/tmp/project"),
                config=_types.StepConfig(sandbox="full-auto"),
            )


class TestCursorCliParseTelemetry:
    """Tests for CursorCliBackend.parse_telemetry()."""

    def test_parse_fixture_file(self, monkeypatch: _pytest.MonkeyPatch) -> None:
        """Fixture NDJSON parses counts/model/duration correctly."""
        monkeypatch.setenv("AGENT_CHAIN_CURSOR_BIN", "/tmp/cursor-wrapper")
        backend = _cursor_cli.CursorCliBackend()
        record = backend.parse_telemetry(_FIXTURES / "cursor_stream.jsonl", 99.0)
        assert record["num_turns"] == 1
        assert record["num_tool_calls"] == 1
        assert record["num_thinking_events"] == 0
        assert record["wall_time_seconds"] == 8.731
        assert record["model"] == "Gemini 3 Flash"
        assert record["backend"] == "cursor-cli"
        assert record["tokens_available"] is False

    def test_parse_empty_file(
        self, tmp_path: _pathlib.Path, monkeypatch: _pytest.MonkeyPatch
    ) -> None:
        """Empty telemetry file falls back to provided wall time."""
        monkeypatch.setenv("AGENT_CHAIN_CURSOR_BIN", "/tmp/cursor-wrapper")
        telemetry = tmp_path / "output.jsonl"
        telemetry.write_text("")
        backend = _cursor_cli.CursorCliBackend()
        record = backend.parse_telemetry(telemetry, 12.5)
        assert record["num_turns"] == 0
        assert record["num_tool_calls"] == 0
        assert record["wall_time_seconds"] == 12.5

    def test_parse_missing_file(
        self, tmp_path: _pathlib.Path, monkeypatch: _pytest.MonkeyPatch
    ) -> None:
        """Missing telemetry file produces zero activity counts."""
        monkeypatch.setenv("AGENT_CHAIN_CURSOR_BIN", "/tmp/cursor-wrapper")
        backend = _cursor_cli.CursorCliBackend()
        record = backend.parse_telemetry(tmp_path / "missing.jsonl", 10.0)
        assert record["num_turns"] == 0
        assert record["num_tool_calls"] == 0
        assert record["wall_time_seconds"] == 10.0

    def test_parse_malformed_json(
        self, tmp_path: _pathlib.Path, monkeypatch: _pytest.MonkeyPatch
    ) -> None:
        """Malformed NDJSON lines are ignored without crashing."""
        monkeypatch.setenv("AGENT_CHAIN_CURSOR_BIN", "/tmp/cursor-wrapper")
        telemetry = tmp_path / "output.jsonl"
        telemetry.write_text("{\"type\":\"assistant\"}\nnot-json\n{\"type\":\"result\",\"duration_ms\":1000}\n")
        backend = _cursor_cli.CursorCliBackend()
        record = backend.parse_telemetry(telemetry, 3.0)
        assert record["num_turns"] == 1
        assert record["wall_time_seconds"] == 1.0

    def test_duration_ms_used_for_wall_time(
        self, tmp_path: _pathlib.Path, monkeypatch: _pytest.MonkeyPatch
    ) -> None:
        """duration_ms from result overrides passed wall_time_seconds."""
        monkeypatch.setenv("AGENT_CHAIN_CURSOR_BIN", "/tmp/cursor-wrapper")
        telemetry = tmp_path / "output.jsonl"
        telemetry.write_text('{"type":"result","duration_ms":2500}\n')
        backend = _cursor_cli.CursorCliBackend()
        record = backend.parse_telemetry(telemetry, 999.0)
        assert record["wall_time_seconds"] == 2.5

    def test_api_time_from_result(
        self, tmp_path: _pathlib.Path, monkeypatch: _pytest.MonkeyPatch
    ) -> None:
        """duration_api_ms from result populates api_time_seconds."""
        monkeypatch.setenv("AGENT_CHAIN_CURSOR_BIN", "/tmp/cursor-wrapper")
        telemetry = tmp_path / "output.jsonl"
        telemetry.write_text('{"type":"result","duration_api_ms":900}\n')
        backend = _cursor_cli.CursorCliBackend()
        record = backend.parse_telemetry(telemetry, 10.0)
        assert record["api_time_seconds"] == 0.9


class TestCursorCliMetadata:
    """Tests for CursorCliBackend metadata and registry entry."""

    def test_name(self, monkeypatch: _pytest.MonkeyPatch) -> None:
        """Backend name is cursor-cli."""
        monkeypatch.setenv("AGENT_CHAIN_CURSOR_BIN", "/tmp/cursor-wrapper")
        backend = _cursor_cli.CursorCliBackend()
        assert backend.name() == "cursor-cli"

    def test_output_file_name(self, monkeypatch: _pytest.MonkeyPatch) -> None:
        """Output file name is output.jsonl."""
        monkeypatch.setenv("AGENT_CHAIN_CURSOR_BIN", "/tmp/cursor-wrapper")
        backend = _cursor_cli.CursorCliBackend()
        assert backend.output_file_name(_types.StepConfig()) == "output.jsonl"

    def test_telemetry_file_name(self, monkeypatch: _pytest.MonkeyPatch) -> None:
        """Telemetry file name is output.jsonl."""
        monkeypatch.setenv("AGENT_CHAIN_CURSOR_BIN", "/tmp/cursor-wrapper")
        backend = _cursor_cli.CursorCliBackend()
        assert backend.telemetry_file_name() == "output.jsonl"

    def test_registry_entry(self) -> None:
        """cursor-cli is in backend registry and instantiates correctly."""
        backend = _backends.get_backend("cursor-cli")
        assert isinstance(backend, _cursor_cli.CursorCliBackend)


class TestCursorCliDiscovery:
    """Tests for _find_command_prefix() fallback chain."""

    def test_env_var_override(self, monkeypatch: _pytest.MonkeyPatch) -> None:
        """Environment variable takes priority over PATH and fallback."""
        monkeypatch.setenv("AGENT_CHAIN_CURSOR_BIN", "/opt/custom/cursor-wrapper")
        result = _cursor_cli._find_command_prefix()
        assert result == ["/opt/custom/cursor-wrapper"]

    def test_path_lookup_when_no_env_var(self, monkeypatch: _pytest.MonkeyPatch) -> None:
        """Falls back to PATH lookup when env var is unset."""
        monkeypatch.delenv("AGENT_CHAIN_CURSOR_BIN", raising=False)
        patch_which = _mock.patch.object(
            _cursor_cli._shutil, "which", return_value="/usr/bin/cursor-wrapper"
        )
        with patch_which:
            result = _cursor_cli._find_command_prefix()
        assert result == ["/usr/bin/cursor-wrapper"]

    def test_repo_local_fallback_when_not_on_path(self, monkeypatch: _pytest.MonkeyPatch) -> None:
        """Falls back to sys.executable + repo script when not found on PATH."""
        monkeypatch.delenv("AGENT_CHAIN_CURSOR_BIN", raising=False)
        with (
            _mock.patch.object(_cursor_cli._shutil, "which", return_value=None),
            _mock.patch.object(_cursor_cli._sys, "executable", "/usr/bin/python3.11"),
        ):
            result = _cursor_cli._find_command_prefix()
        assert result[0] == "/usr/bin/python3.11"
        assert result[1].endswith("scripts/cursor-wrapper.py")
