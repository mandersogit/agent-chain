"""Integration tests for scripts/cursor-wrapper.py."""

import json as _json
import os as _os
import pathlib as _pathlib
import stat as _stat
import subprocess as _subprocess
import sys as _sys
import textwrap as _textwrap

_ROOT = _pathlib.Path(__file__).parent.parent
_WRAPPER = _ROOT / "scripts" / "cursor-wrapper.py"
_VENV_PYTHON = _ROOT / "local.venv" / "bin" / "python"
_PYTHON = _VENV_PYTHON if _VENV_PYTHON.exists() else _pathlib.Path(_sys.executable)


def _write_executable(path: _pathlib.Path, content: str) -> _pathlib.Path:
    path.write_text(content)
    path.chmod(path.stat().st_mode | _stat.S_IXUSR)
    return path


def _fake_agent_script() -> str:
    return _textwrap.dedent(
        f"""\
        #!{_PYTHON}
        import json
        import os
        import pathlib
        import sys
        import time

        args = sys.argv[1:]
        if "--version" in args:
            print("fake-agent 1.0")
            sys.exit(0)
        if "--list-models" in args:
            print("model-a")
            print("model-b")
            sys.exit(0)

        args_file = os.environ.get("FAKE_AGENT_ARGS_FILE")
        if args_file:
            pathlib.Path(args_file).write_text(json.dumps(args))

        cwd_file = os.environ.get("FAKE_AGENT_CWD_FILE")
        if cwd_file:
            pathlib.Path(cwd_file).write_text(os.getcwd())

        behavior = os.environ.get("FAKE_AGENT_BEHAVIOR", "result_hang")
        result_text = os.environ.get("FAKE_AGENT_RESULT", "done")
        if behavior == "silent_hang":
            while True:
                time.sleep(10)
        if behavior == "no_result_exit":
            print(
                json.dumps(
                    {{
                        "type": "system",
                        "subtype": "init",
                        "model": "FakeModel",
                        "session_id": "sess",
                    }}
                )
            )
            sys.stdout.flush()
            sys.exit(0)
        if behavior == "error_result":
            print(json.dumps({{
                "type": "result",
                "subtype": "success",
                "is_error": True,
                "result": "something went wrong",
            }}))
            sys.stdout.flush()
            sys.exit(0)
        if behavior == "failure_result":
            print(json.dumps({{
                "type": "result",
                "subtype": "failure",
                "is_error": False,
                "result": "",
            }}))
            sys.stdout.flush()
            sys.exit(0)

        print(
            json.dumps(
                {{
                    "type": "system",
                    "subtype": "init",
                    "model": "FakeModel",
                    "session_id": "sess",
                }}
            )
        )
        print(json.dumps({{"type": "user", "message": {{"content": "brief"}}}}))
        print(json.dumps({{"type": "thinking", "subtype": "delta", "text": "..."}}))
        print(json.dumps({{"type": "tool_call", "subtype": "started", "call_id": "1"}}))
        print(json.dumps({{"type": "tool_call", "subtype": "completed", "call_id": "1"}}))
        print(json.dumps({{"type": "assistant", "message": {{"content": result_text}}}}))
        print(json.dumps({{
            "type": "result",
            "subtype": "success",
            "duration_ms": 10,
            "duration_api_ms": 5,
            "is_error": False,
            "request_id": "req-1",
            "result": result_text
        }}))
        sys.stdout.flush()
        while True:
            time.sleep(10)
        """
    )


def _run_wrapper(
    args: list[str],
    *,
    env: dict[str, str | None] | None = None,
    stdin: str | None = None,
    cwd: _pathlib.Path | None = None,
) -> _subprocess.CompletedProcess[str]:
    proc_env = _os.environ.copy()
    if env:
        for key, value in env.items():
            if value is None:
                proc_env.pop(key, None)
            else:
                proc_env[key] = value
    return _subprocess.run(
        [str(_PYTHON), str(_WRAPPER), *args],
        input=stdin,
        text=True,
        capture_output=True,
        cwd=cwd or _ROOT,
        env=proc_env,
    )


def test_exec_uses_positional_prompt(tmp_path: _pathlib.Path) -> None:
    fake = _write_executable(tmp_path / "fake-agent.py", _fake_agent_script())
    args_file = tmp_path / "args.json"
    result = _run_wrapper(
        ["exec", "--output-format", "text", "hello world"],
        env={
            "CURSOR_WRAPPER_AGENT_BIN": f"{_PYTHON} {fake}",
            "FAKE_AGENT_ARGS_FILE": str(args_file),
        },
    )
    assert result.returncode == 0
    assert result.stdout.strip() == "done"
    args = _json.loads(args_file.read_text())
    assert args[-1] == "hello world"


def test_exec_reads_prompt_from_stdin_dash(tmp_path: _pathlib.Path) -> None:
    fake = _write_executable(tmp_path / "fake-agent.py", _fake_agent_script())
    args_file = tmp_path / "args.json"
    result = _run_wrapper(
        ["exec", "--output-format", "text", "-"],
        stdin="from stdin",
        env={
            "CURSOR_WRAPPER_AGENT_BIN": f"{_PYTHON} {fake}",
            "FAKE_AGENT_ARGS_FILE": str(args_file),
        },
    )
    assert result.returncode == 0
    args = _json.loads(args_file.read_text())
    assert args[-1] == "from stdin"


def test_exec_empty_stdin_prompt_fails(tmp_path: _pathlib.Path) -> None:
    fake = _write_executable(tmp_path / "fake-agent.py", _fake_agent_script())
    result = _run_wrapper(
        ["exec", "-"],
        stdin="",
        env={"CURSOR_WRAPPER_AGENT_BIN": f"{_PYTHON} {fake}"},
    )
    assert result.returncode == 1
    assert "Prompt from stdin is empty" in result.stderr


def test_output_format_stream_json_passthrough(tmp_path: _pathlib.Path) -> None:
    fake = _write_executable(tmp_path / "fake-agent.py", _fake_agent_script())
    result = _run_wrapper(
        ["exec", "brief"],
        env={"CURSOR_WRAPPER_AGENT_BIN": f"{_PYTHON} {fake}"},
    )
    assert result.returncode == 0
    lines = [line for line in result.stdout.splitlines() if line.strip()]
    assert len(lines) >= 2
    assert _json.loads(lines[0])["type"] == "system"
    assert _json.loads(lines[-1])["type"] == "result"


def test_output_format_json_summary(tmp_path: _pathlib.Path) -> None:
    fake = _write_executable(tmp_path / "fake-agent.py", _fake_agent_script())
    result = _run_wrapper(
        ["exec", "--output-format", "json", "brief"],
        env={"CURSOR_WRAPPER_AGENT_BIN": f"{_PYTHON} {fake}"},
    )
    assert result.returncode == 0
    payload = _json.loads(result.stdout)
    assert payload["result"] == "done"
    assert payload["num_turns"] == 1
    assert payload["num_tool_calls"] == 1
    assert payload["num_thinking_events"] == 1
    assert payload["input_tokens"] == 0
    assert payload["output_tokens"] == 0


def test_output_format_text_extracts_result(tmp_path: _pathlib.Path) -> None:
    fake = _write_executable(tmp_path / "fake-agent.py", _fake_agent_script())
    result = _run_wrapper(
        ["exec", "--output-format", "text", "brief"],
        env={
            "CURSOR_WRAPPER_AGENT_BIN": f"{_PYTHON} {fake}",
            "FAKE_AGENT_RESULT": "final answer",
        },
    )
    assert result.returncode == 0
    assert result.stdout.strip() == "final answer"


def test_timeout_exit_code_124(tmp_path: _pathlib.Path) -> None:
    fake = _write_executable(tmp_path / "fake-agent.py", _fake_agent_script())
    result = _run_wrapper(
        ["exec", "--timeout", "1", "brief"],
        env={
            "CURSOR_WRAPPER_AGENT_BIN": f"{_PYTHON} {fake}",
            "FAKE_AGENT_BEHAVIOR": "silent_hang",
        },
    )
    assert result.returncode == 124
    assert "timeout" in result.stderr


def test_no_result_event_returns_exit_code_1(tmp_path: _pathlib.Path) -> None:
    fake = _write_executable(tmp_path / "fake-agent.py", _fake_agent_script())
    result = _run_wrapper(
        ["exec", "brief"],
        env={
            "CURSOR_WRAPPER_AGENT_BIN": f"{_PYTHON} {fake}",
            "FAKE_AGENT_BEHAVIOR": "no_result_exit",
        },
    )
    assert result.returncode == 1
    assert "no result event received" in result.stderr


def test_binary_discovery_cursor_agent_on_path(tmp_path: _pathlib.Path) -> None:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    _write_executable(bin_dir / "cursor-agent", _fake_agent_script())
    env = {
        "PATH": str(bin_dir),
        "CURSOR_WRAPPER_AGENT_BIN": None,
    }
    result = _run_wrapper(["exec", "--output-format", "text", "brief"], env=env)
    assert result.returncode == 0
    assert result.stdout.strip() == "done"


def test_binary_discovery_cursor_subcommand_on_path(tmp_path: _pathlib.Path) -> None:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    cursor_script = _textwrap.dedent(
        f"""\
        #!{_PYTHON}
        import json
        import sys
        import time
        args = sys.argv[1:]
        if args == ["agent", "--version"]:
            print("cursor-agent-via-subcommand 1.0")
            sys.exit(0)
        if args and args[0] == "agent":
            print(
                json.dumps(
                    {{
                        "type": "result",
                        "subtype": "success",
                        "is_error": False,
                        "result": "ok",
                    }}
                )
            )
            sys.stdout.flush()
            while True:
                time.sleep(10)
        sys.exit(2)
        """
    )
    _write_executable(bin_dir / "cursor", cursor_script)
    result = _run_wrapper(
        ["exec", "--output-format", "text", "brief"],
        env={
            "PATH": str(bin_dir),
            "CURSOR_WRAPPER_AGENT_BIN": None,
        },
    )
    assert result.returncode == 0
    assert result.stdout.strip() == "ok"


def test_command_construction_forwards_flags(tmp_path: _pathlib.Path) -> None:
    fake = _write_executable(tmp_path / "fake-agent.py", _fake_agent_script())
    args_file = tmp_path / "args.json"
    cwd_file = tmp_path / "cwd.txt"
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    result = _run_wrapper(
        [
            "exec",
            "--model",
            "opus-4.6",
            "--mode",
            "plan",
            "--no-force",
            "--sandbox",
            "enabled",
            "--workspace",
            str(workspace),
            "--max-turns",
            "3",
            "--extra-flag",
            "--alpha 1",
            "--extra-flag",
            "--beta",
            "--output-format",
            "text",
            "brief",
        ],
        env={
            "CURSOR_WRAPPER_AGENT_BIN": f"{_PYTHON} {fake}",
            "FAKE_AGENT_ARGS_FILE": str(args_file),
            "FAKE_AGENT_CWD_FILE": str(cwd_file),
        },
    )
    assert result.returncode == 0
    args = _json.loads(args_file.read_text())
    assert "--model" in args and "opus-4.6" in args
    assert "--mode" in args and "plan" in args
    assert "--no-force" in args
    assert "--sandbox" in args and "enabled" in args
    assert "--workspace" in args and str(workspace) in args
    assert "--max-turns" not in args  # cursor-agent doesn't support --max-turns
    assert "max-turns ignored" in result.stderr
    assert "--alpha" in args and "1" in args
    assert "--beta" in args
    # Verify subprocess was spawned with workspace as CWD
    recorded_cwd = cwd_file.read_text()
    assert _pathlib.Path(recorded_cwd) == workspace


def test_config_validation_warnings(tmp_path: _pathlib.Path) -> None:
    fake = _write_executable(tmp_path / "fake-agent.py", _fake_agent_script())
    result1 = _run_wrapper(
        ["exec", "--mode", "plan", "--force", "--output-format", "text", "brief"],
        env={"CURSOR_WRAPPER_AGENT_BIN": f"{_PYTHON} {fake}"},
    )
    result2 = _run_wrapper(
        ["exec", "--no-force", "--output-format", "text", "brief"],
        env={"CURSOR_WRAPPER_AGENT_BIN": f"{_PYTHON} {fake}"},
    )
    assert result1.returncode == 0
    assert "--force has no effect" in result1.stderr
    assert result2.returncode == 0
    assert "--no-force without --mode may hang" in result2.stderr


def test_no_force_with_ask_mode_warns_about_trust_prompts(tmp_path: _pathlib.Path) -> None:
    fake = _write_executable(tmp_path / "fake-agent.py", _fake_agent_script())
    result = _run_wrapper(
        ["exec", "--no-force", "--mode", "ask", "--output-format", "text", "brief"],
        env={"CURSOR_WRAPPER_AGENT_BIN": f"{_PYTHON} {fake}"},
    )
    assert result.returncode == 0
    assert "workspace trust prompts" in result.stderr


def test_verbose_mode_logs_progress(tmp_path: _pathlib.Path) -> None:
    fake = _write_executable(tmp_path / "fake-agent.py", _fake_agent_script())
    result = _run_wrapper(
        ["exec", "--verbose", "--output-format", "text", "brief"],
        env={"CURSOR_WRAPPER_AGENT_BIN": f"{_PYTHON} {fake}"},
    )
    assert result.returncode == 0
    assert "cursor-wrapper: using" in result.stderr
    assert "cursor-wrapper: [" in result.stderr
    assert "cursor-wrapper: done in" in result.stderr


def test_output_flag_writes_stream_json_to_file(tmp_path: _pathlib.Path) -> None:
    fake = _write_executable(tmp_path / "fake-agent.py", _fake_agent_script())
    out_file = tmp_path / "out.ndjson"
    result = _run_wrapper(
        ["exec", "--output", str(out_file), "brief"],
        env={"CURSOR_WRAPPER_AGENT_BIN": f"{_PYTHON} {fake}"},
    )
    assert result.returncode == 0
    assert result.stdout == ""
    lines = [line for line in out_file.read_text().splitlines() if line.strip()]
    assert len(lines) >= 2
    assert _json.loads(lines[0])["type"] == "system"
    assert _json.loads(lines[-1])["type"] == "result"


def test_output_flag_json_writes_summary_to_file(tmp_path: _pathlib.Path) -> None:
    fake = _write_executable(tmp_path / "fake-agent.py", _fake_agent_script())
    out_file = tmp_path / "summary.json"
    result = _run_wrapper(
        ["exec", "--output-format", "json", "--output", str(out_file), "brief"],
        env={"CURSOR_WRAPPER_AGENT_BIN": f"{_PYTHON} {fake}"},
    )
    assert result.returncode == 0
    assert result.stdout == ""
    payload = _json.loads(out_file.read_text())
    assert payload["result"] == "done"
    assert payload["num_turns"] == 1
    assert payload["num_tool_calls"] == 1


def test_version_command_prints_both_versions(tmp_path: _pathlib.Path) -> None:
    fake = _write_executable(tmp_path / "fake-agent.py", _fake_agent_script())
    result = _run_wrapper(
        ["version"],
        env={"CURSOR_WRAPPER_AGENT_BIN": f"{_PYTHON} {fake}"},
    )
    assert result.returncode == 0
    assert "cursor-wrapper" in result.stdout
    assert "fake-agent 1.0" in result.stdout


def test_models_command_lists_models(tmp_path: _pathlib.Path) -> None:
    fake = _write_executable(tmp_path / "fake-agent.py", _fake_agent_script())
    result = _run_wrapper(
        ["models"],
        env={"CURSOR_WRAPPER_AGENT_BIN": f"{_PYTHON} {fake}"},
    )
    assert result.returncode == 0
    assert "model-a" in result.stdout
    assert "model-b" in result.stdout


# ── C1: cursor subcommand must use the resolved absolute path ────────────────


def test_binary_discovery_cursor_subcommand_records_absolute_argv0(tmp_path: _pathlib.Path) -> None:
    """cursor subcommand discovery must forward the absolute path, not the bare name."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    argv0_file = tmp_path / "argv0.txt"
    cursor_script = _textwrap.dedent(
        f"""\
        #!{_PYTHON}
        import json, pathlib, sys, time
        args = sys.argv[1:]
        if args == ["agent", "--version"]:
            print("cursor-via-subcommand 1.0")
            sys.exit(0)
        if args and args[0] == "agent":
            pathlib.Path(r"{argv0_file}").write_text(sys.argv[0])
            ev = {{"type": "result", "subtype": "success", "is_error": False, "result": "ok"}}
            print(json.dumps(ev))
            sys.stdout.flush()
            while True:
                time.sleep(10)
        sys.exit(2)
        """
    )
    _write_executable(bin_dir / "cursor", cursor_script)
    result = _run_wrapper(
        ["exec", "--output-format", "text", "brief"],
        env={
            "PATH": str(bin_dir),
            "CURSOR_WRAPPER_AGENT_BIN": None,
        },
    )
    assert result.returncode == 0
    # argv[0] received by the subprocess must be an absolute path, not "cursor"
    recorded_argv0 = argv0_file.read_text()
    assert _pathlib.Path(recorded_argv0).is_absolute(), (
        f"cursor subcommand was invoked with bare name '{recorded_argv0}' "
        "instead of the resolved absolute path"
    )


# ── C2: '--' separator before prompt ─────────────────────────────────────────


def test_build_command_inserts_double_dash_before_prompt(tmp_path: _pathlib.Path) -> None:
    """'--' must appear immediately before the prompt in the subprocess argv."""
    fake = _write_executable(tmp_path / "fake-agent.py", _fake_agent_script())
    args_file = tmp_path / "args.json"
    result = _run_wrapper(
        ["exec", "--output-format", "text", "my task"],
        env={
            "CURSOR_WRAPPER_AGENT_BIN": f"{_PYTHON} {fake}",
            "FAKE_AGENT_ARGS_FILE": str(args_file),
        },
    )
    assert result.returncode == 0
    args = _json.loads(args_file.read_text())
    assert "--" in args
    double_dash_idx = args.index("--")
    assert args[double_dash_idx + 1] == "my task"


def test_exec_prompt_starting_with_dashes_not_treated_as_flag(tmp_path: _pathlib.Path) -> None:
    """A prompt that starts with '--' must reach the agent as a literal argument."""
    fake = _write_executable(tmp_path / "fake-agent.py", _fake_agent_script())
    args_file = tmp_path / "args.json"
    # Pass via stdin to avoid Click itself misinterpreting the leading '--'
    result = _run_wrapper(
        ["exec", "--output-format", "text", "-"],
        stdin="--do-the-thing",
        env={
            "CURSOR_WRAPPER_AGENT_BIN": f"{_PYTHON} {fake}",
            "FAKE_AGENT_ARGS_FILE": str(args_file),
        },
    )
    assert result.returncode == 0
    args = _json.loads(args_file.read_text())
    assert args[-1] == "--do-the-thing"
    assert "--" in args
    assert args[args.index("--") + 1] == "--do-the-thing"


# ── _result_exit_code coverage ───────────────────────────────────────────────


def test_result_event_is_error_true_returns_exit_code_1(tmp_path: _pathlib.Path) -> None:
    fake = _write_executable(tmp_path / "fake-agent.py", _fake_agent_script())
    result = _run_wrapper(
        ["exec", "brief"],
        env={
            "CURSOR_WRAPPER_AGENT_BIN": f"{_PYTHON} {fake}",
            "FAKE_AGENT_BEHAVIOR": "error_result",
        },
    )
    assert result.returncode == 1


def test_result_event_subtype_failure_returns_exit_code_1(tmp_path: _pathlib.Path) -> None:
    fake = _write_executable(tmp_path / "fake-agent.py", _fake_agent_script())
    result = _run_wrapper(
        ["exec", "brief"],
        env={
            "CURSOR_WRAPPER_AGENT_BIN": f"{_PYTHON} {fake}",
            "FAKE_AGENT_BEHAVIOR": "failure_result",
        },
    )
    assert result.returncode == 1
