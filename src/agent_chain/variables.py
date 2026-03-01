"""Template variable resolution for chain definitions."""

import re as _re
import shlex as _shlex

_VAR_PATTERN = _re.compile(r"\{\{(\s*[\w.-]+\s*)\}\}")
_BACKSLASH_SENTINEL = "\x00BACKSLASH\x00"
_LBRACE_SENTINEL = "\x00LBRACE\x00"
_RBRACE_SENTINEL = "\x00RBRACE\x00"


def _mask_escaped_braces(template: str) -> str:
    """Protect escaped braces from variable resolution.

    Escaped backslashes (``\\\\``) are masked first so that
    ``\\\\{{var}}`` resolves to a literal backslash followed by the
    variable value, rather than being misinterpreted as an escaped brace.

    Args:
        template: Template text that may contain escaped brace sequences.

    Returns:
        Template with ``\\\\``, ``\\{{``, and ``\\}}`` replaced with sentinels.
    """
    result = template.replace("\\\\", _BACKSLASH_SENTINEL)
    result = result.replace(r"\{{", _LBRACE_SENTINEL)
    result = result.replace(r"\}}", _RBRACE_SENTINEL)
    return result


def _unmask_escaped_braces(text: str) -> str:
    """Restore sentinels into literal sequences.

    Args:
        text: Text containing escape sentinels.

    Returns:
        Text where sentinels are converted back to their literal characters.
    """
    result = text.replace(_LBRACE_SENTINEL, "{{")
    result = result.replace(_RBRACE_SENTINEL, "}}")
    result = result.replace(_BACKSLASH_SENTINEL, "\\")
    return result


def _extract_from_masked(masked_template: str) -> list[str]:
    """Extract variable names from a masked template.

    Args:
        masked_template: Template after escaped braces have been masked.

    Returns:
        List of variable names found in the template.
    """
    return [m.group(1).strip() for m in _VAR_PATTERN.finditer(masked_template)]


def resolve(template: str, variables: dict[str, str]) -> str:
    """Resolve ``{{var_name}}`` placeholders in *template*.

    Args:
        template: String potentially containing ``{{var}}`` placeholders.
        variables: Mapping of variable names to their string values.

    Returns:
        The template with all placeholders replaced.

    Raises:
        KeyError: If a referenced variable is not in *variables*.
    """

    def _replace(match: _re.Match[str]) -> str:
        name = match.group(1).strip()
        if name not in variables:
            raise KeyError(f"Undefined variable: {{{{{name}}}}}")
        return variables[name]

    masked = _mask_escaped_braces(template)
    resolved = _VAR_PATTERN.sub(_replace, masked)
    return _unmask_escaped_braces(resolved)


def extract_variable_names(template: str) -> list[str]:
    """Return all ``{{var_name}}`` references found in *template*.

    Args:
        template: String potentially containing ``{{var}}`` placeholders.

    Returns:
        List of variable names found in the template.
    """
    masked = _mask_escaped_braces(template)
    return _extract_from_masked(masked)


def check_undefined(
    template: str,
    variables: dict[str, str],
) -> list[str]:
    """Return names referenced in *template* but missing from *variables*.

    Args:
        template: String potentially containing ``{{var}}`` placeholders.
        variables: Mapping of defined variable names.

    Returns:
        List of variable names referenced but not defined.
    """
    masked = _mask_escaped_braces(template)
    return [name for name in _extract_from_masked(masked) if name not in variables]


def resolve_shell_safe(template: str, variables: dict[str, str]) -> str:
    """Resolve ``{{var_name}}`` placeholders with shell escaping for each value.

    Each variable value is quoted to be safe for shell execution.

    Args:
        template: String potentially containing ``{{var}}`` placeholders.
        variables: Mapping of variable names to their string values.

    Returns:
        The template with all placeholders replaced and values shell-quoted.

    Raises:
        KeyError: If a referenced variable is not in *variables*.
    """

    def _replace(match: _re.Match[str]) -> str:
        name = match.group(1).strip()
        if name not in variables:
            raise KeyError(f"Undefined variable: {{{{{name}}}}}")
        return _shlex.quote(variables[name])

    masked = _mask_escaped_braces(template)
    resolved = _VAR_PATTERN.sub(_replace, masked)
    return _unmask_escaped_braces(resolved)
