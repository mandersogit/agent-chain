"""Tests for chain loading and validation."""

import pathlib as _pathlib
import textwrap as _textwrap

import pytest as _pytest

import agent_chain.backends as _backends
import agent_chain.chain as _chain

_FIXTURES = _pathlib.Path(__file__).parent / "fixtures"


class TestChainLoad:
    """Tests for chain TOML loading."""

    def test_load_minimal_chain(self) -> None:
        """Minimal chain with one verify step loads without error."""
        chain = _chain.load(_FIXTURES / "minimal_chain.toml")
        assert chain.name == "minimal"
        assert len(chain.steps) == 1
        assert chain.steps[0].name == "check"
        assert chain.steps[0].step_type == "verify"
        assert chain.steps[0].agent == "none"

    def test_load_full_chain(self) -> None:
        """Full 5-step pipeline loads all steps with correct types."""
        chain = _chain.load(_FIXTURES / "full_chain.toml")
        assert chain.name == "full-pipeline"
        assert len(chain.steps) == 5
        assert chain.steps[0].step_type == "implement"
        assert chain.steps[1].step_type == "review"
        assert chain.steps[2].step_type == "review"
        assert chain.steps[3].step_type == "fix"
        assert chain.steps[4].step_type == "verify"

    def test_load_preserves_variables(self) -> None:
        """Variables from [vars] table are preserved in the chain definition."""
        chain = _chain.load(_FIXTURES / "full_chain.toml")
        assert chain.variables["project_root"] == "/tmp/test-project"
        assert "task_dir" in chain.variables
        assert "schema_dir" in chain.variables

    def test_load_preserves_agent_config(self) -> None:
        """Agent config from [steps.agent_config] is preserved."""
        chain = _chain.load(_FIXTURES / "full_chain.toml")
        impl = chain.steps[0]
        assert impl.agent_config.get("sandbox") == "full-auto"
        assert impl.agent_config.get("reasoning_effort") == "high"

    def test_load_preserves_gate_config(self) -> None:
        """Gate config from [steps.gate] is preserved."""
        chain = _chain.load(_FIXTURES / "full_chain.toml")
        review = chain.steps[1]
        assert review.gate is not None
        assert review.gate.get("on_failure") == "warn"

    def test_load_default_timeout(self) -> None:
        """Default timeout defaults to 1800 if not specified."""
        chain = _chain.load(_FIXTURES / "minimal_chain.toml")
        assert chain.default_timeout == 1800

    def test_load_missing_chain_table_raises(self, tmp_path: _pathlib.Path) -> None:
        """Loading TOML without [chain] table raises ValidationError."""
        f = tmp_path / "bad.toml"
        f.write_text("[[steps]]\nname = 'x'\ntype = 'verify'\nagent = 'none'\n")
        with _pytest.raises(_chain.ValidationError, match="Missing \\[chain\\] table"):
            _chain.load(f)

    def test_load_missing_chain_name_raises(self, tmp_path: _pathlib.Path) -> None:
        """Loading TOML without chain name raises ValidationError."""
        f = tmp_path / "bad.toml"
        f.write_text("[chain]\n[[steps]]\nname = 'x'\ntype = 'verify'\nagent = 'none'\n")
        with _pytest.raises(_chain.ValidationError, match="non-empty 'name'"):
            _chain.load(f)

    def test_load_no_steps_raises(self, tmp_path: _pathlib.Path) -> None:
        """Loading TOML without steps raises ValidationError."""
        f = tmp_path / "bad.toml"
        f.write_text('[chain]\nname = "test"\n')
        with _pytest.raises(_chain.ValidationError, match="at least one"):
            _chain.load(f)

    def test_load_duplicate_step_names_raises(self, tmp_path: _pathlib.Path) -> None:
        """Duplicate step names raise ValidationError."""
        toml = _textwrap.dedent("""\
            [chain]
            name = "dup"
            [[steps]]
            name = "step1"
            type = "verify"
            agent = "none"
            [steps.gate]
            command = "true"
            [[steps]]
            name = "step1"
            type = "verify"
            agent = "none"
            [steps.gate]
            command = "true"
        """)
        f = tmp_path / "dup.toml"
        f.write_text(toml)
        with _pytest.raises(_chain.ValidationError, match="Duplicate step name"):
            _chain.load(f)

    def test_load_invalid_step_type_raises(self, tmp_path: _pathlib.Path) -> None:
        """Invalid step type raises ValidationError."""
        toml = _textwrap.dedent("""\
            [chain]
            name = "bad-type"
            [[steps]]
            name = "s1"
            type = "invalid_type"
            agent = "none"
        """)
        f = tmp_path / "bad_type.toml"
        f.write_text(toml)
        with _pytest.raises(_chain.ValidationError, match="'type' must be one of"):
            _chain.load(f)

    def test_load_invalid_toml_syntax_raises(self, tmp_path: _pathlib.Path) -> None:
        """Invalid TOML syntax raises ValidationError."""
        f = tmp_path / "bad.toml"
        f.write_text("this is not valid toml {{{{")
        with _pytest.raises(_chain.ValidationError, match="Invalid TOML"):
            _chain.load(f)


class TestChainValidate:
    """Tests for chain validation."""

    def test_validate_minimal_chain_passes(self) -> None:
        """Minimal valid chain passes validation."""
        chain = _chain.load(_FIXTURES / "minimal_chain.toml")
        result = _chain.validate(chain, known_backends=_backends.known_backend_names())
        assert result.ok

    def test_validate_full_chain_passes(self) -> None:
        """Full pipeline passes validation with all variables provided."""
        chain = _chain.load(_FIXTURES / "full_chain.toml")
        result = _chain.validate(chain, known_backends=_backends.known_backend_names())
        assert result.ok

    def test_validate_unknown_backend_errors(self, tmp_path: _pathlib.Path) -> None:
        """Unknown agent backend produces a validation error."""
        toml = _textwrap.dedent("""\
            [chain]
            name = "bad-agent"
            [[steps]]
            name = "s1"
            type = "implement"
            agent = "nonexistent-agent"
            [steps.brief]
            source = "inline"
            text = "hello"
        """)
        f = tmp_path / "bad_agent.toml"
        f.write_text(toml)
        chain = _chain.load(f)
        result = _chain.validate(chain, known_backends=_backends.known_backend_names())
        assert not result.ok
        assert any("unknown agent backend" in e for e in result.errors)

    def test_validate_verify_without_gate_errors(self, tmp_path: _pathlib.Path) -> None:
        """Verify step without a gate produces a validation error."""
        toml = _textwrap.dedent("""\
            [chain]
            name = "no-gate"
            [[steps]]
            name = "check"
            type = "verify"
            agent = "none"
        """)
        f = tmp_path / "no_gate.toml"
        f.write_text(toml)
        chain = _chain.load(f)
        result = _chain.validate(chain, known_backends=_backends.known_backend_names())
        assert not result.ok
        assert any("must have a gate" in e for e in result.errors)

    def test_validate_verify_with_wrong_agent_errors(self, tmp_path: _pathlib.Path) -> None:
        """Verify step with agent != 'none' produces a validation error."""
        toml = _textwrap.dedent("""\
            [chain]
            name = "bad-verify"
            [[steps]]
            name = "check"
            type = "verify"
            agent = "codex-cli"
            [steps.gate]
            command = "true"
        """)
        f = tmp_path / "bad_verify.toml"
        f.write_text(toml)
        chain = _chain.load(f)
        result = _chain.validate(chain, known_backends=_backends.known_backend_names())
        assert not result.ok
        assert any("agent='none'" in e for e in result.errors)

    def test_validate_missing_brief_errors(self, tmp_path: _pathlib.Path) -> None:
        """Non-verify step without a brief produces a validation error."""
        toml = _textwrap.dedent("""\
            [chain]
            name = "no-brief"
            [[steps]]
            name = "impl"
            type = "implement"
            agent = "codex-cli"
        """)
        f = tmp_path / "no_brief.toml"
        f.write_text(toml)
        chain = _chain.load(f)
        result = _chain.validate(chain, known_backends=_backends.known_backend_names())
        assert not result.ok
        assert any("must have a brief" in e for e in result.errors)

    def test_validate_undefined_variable_in_brief_errors(self, tmp_path: _pathlib.Path) -> None:
        """Undefined variable in brief text produces a validation error."""
        toml = _textwrap.dedent("""\
            [chain]
            name = "bad-var"
            [[steps]]
            name = "impl"
            type = "implement"
            agent = "codex-cli"
            [steps.brief]
            source = "inline"
            text = "Use {{undefined_var}} here"
        """)
        f = tmp_path / "bad_var.toml"
        f.write_text(toml)
        chain = _chain.load(f)
        result = _chain.validate(chain, known_backends=_backends.known_backend_names())
        assert not result.ok
        assert any("undefined_var" in e for e in result.errors)

    def test_validate_cli_vars_override(self, tmp_path: _pathlib.Path) -> None:
        """CLI vars resolve otherwise-undefined variables."""
        toml = _textwrap.dedent("""\
            [chain]
            name = "cli-var"
            [[steps]]
            name = "impl"
            type = "implement"
            agent = "codex-cli"
            [steps.brief]
            source = "inline"
            text = "Use {{my_var}} here"
        """)
        f = tmp_path / "cli_var.toml"
        f.write_text(toml)
        chain = _chain.load(f)
        result = _chain.validate(
            chain, {"my_var": "value"}, known_backends=_backends.known_backend_names()
        )
        assert result.ok

    def test_validate_invalid_on_failure_errors(self, tmp_path: _pathlib.Path) -> None:
        """Invalid gate on_failure value produces a validation error."""
        toml = _textwrap.dedent("""\
            [chain]
            name = "bad-gate"
            [[steps]]
            name = "check"
            type = "verify"
            agent = "none"
            [steps.gate]
            command = "true"
            on_failure = "explode"
        """)
        f = tmp_path / "bad_gate.toml"
        f.write_text(toml)
        chain = _chain.load(f)
        result = _chain.validate(chain, known_backends=_backends.known_backend_names())
        assert not result.ok
        assert any("on_failure" in e for e in result.errors)

    def test_validate_warns_on_missing_gate(self) -> None:
        """Non-custom, non-verify step without gate produces a warning."""
        chain = _chain.load(_FIXTURES / "full_chain.toml")
        result = _chain.validate(chain, known_backends=_backends.known_backend_names())
        assert any("no verification gate" in w for w in result.warnings)
