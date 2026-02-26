"""Tests for template variable resolution."""

import pytest as _pytest

import agent_chain.variables as _variables


class TestResolve:
    """Tests for variable resolution."""

    def test_resolve_simple_variable(self) -> None:
        """Simple {{var}} is replaced with its value."""
        result = _variables.resolve("Hello {{name}}", {"name": "world"})
        assert result == "Hello world"

    def test_resolve_multiple_variables(self) -> None:
        """Multiple distinct variables are all resolved."""
        result = _variables.resolve(
            "{{greeting}} {{name}}!", {"greeting": "Hi", "name": "there"}
        )
        assert result == "Hi there!"

    def test_resolve_dotted_variable(self) -> None:
        """Dotted variable names like chain.name are resolved."""
        result = _variables.resolve(
            "Chain: {{chain.name}}", {"chain.name": "test-chain"}
        )
        assert result == "Chain: test-chain"

    def test_resolve_whitespace_tolerance(self) -> None:
        """Whitespace inside braces is tolerated."""
        result = _variables.resolve("{{ name }}", {"name": "padded"})
        assert result == "padded"

    def test_resolve_undefined_raises(self) -> None:
        """Undefined variable raises KeyError."""
        with _pytest.raises(KeyError, match="missing"):
            _variables.resolve("{{missing}}", {})

    def test_resolve_no_variables(self) -> None:
        """String with no variables is returned unchanged."""
        result = _variables.resolve("no vars here", {})
        assert result == "no vars here"

    def test_resolve_repeated_variable(self) -> None:
        """Same variable appearing twice is resolved in both places."""
        result = _variables.resolve("{{x}} and {{x}}", {"x": "val"})
        assert result == "val and val"

    def test_resolve_empty_string(self) -> None:
        """Empty string template returns empty string."""
        result = _variables.resolve("", {})
        assert result == ""

    def test_resolve_variable_at_boundaries(self) -> None:
        """Variable at start and end of string resolves correctly."""
        result = _variables.resolve("{{a}}{{b}}", {"a": "1", "b": "2"})
        assert result == "12"


class TestExtractVariableNames:
    """Tests for variable name extraction."""

    def test_extract_no_variables(self) -> None:
        """Template with no variables returns empty list."""
        assert _variables.extract_variable_names("no vars") == []

    def test_extract_single_variable(self) -> None:
        """Template with one variable returns it."""
        assert _variables.extract_variable_names("{{foo}}") == ["foo"]

    def test_extract_dotted_variable(self) -> None:
        """Dotted variable names are extracted correctly."""
        names = _variables.extract_variable_names("{{chain.name}} {{step.name}}")
        assert names == ["chain.name", "step.name"]

    def test_extract_strips_whitespace(self) -> None:
        """Whitespace inside braces is stripped from extracted names."""
        names = _variables.extract_variable_names("{{ padded }}")
        assert names == ["padded"]


class TestCheckUndefined:
    """Tests for undefined variable detection."""

    def test_all_defined_returns_empty(self) -> None:
        """No undefined variables returns empty list."""
        result = _variables.check_undefined("{{a}} {{b}}", {"a": "1", "b": "2"})
        assert result == []

    def test_one_undefined_returns_it(self) -> None:
        """One undefined variable is returned."""
        result = _variables.check_undefined("{{a}} {{b}}", {"a": "1"})
        assert result == ["b"]

    def test_all_undefined_returns_all(self) -> None:
        """All undefined variables are returned."""
        result = _variables.check_undefined("{{x}} {{y}}", {})
        assert result == ["x", "y"]

    def test_builtin_vars_not_flagged_when_provided(self) -> None:
        """Built-in variables are not flagged when present in the dict."""
        result = _variables.check_undefined(
            "{{chain.name}}", {"chain.name": "test"}
        )
        assert result == []
