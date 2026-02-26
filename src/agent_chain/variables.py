"""Template variable resolution for chain definitions."""

import re as _re
import shlex as _shlex

_VAR_PATTERN = _re.compile(r"\{\{(\s*[\w.]+\s*)\}\}")


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

    return _VAR_PATTERN.sub(_replace, template)


def extract_variable_names(template: str) -> list[str]:
    """Return all ``{{var_name}}`` references found in *template*.

    Args:
        template: String potentially containing ``{{var}}`` placeholders.

    Returns:
        List of variable names found in the template.
    """
    return [m.group(1).strip() for m in _VAR_PATTERN.finditer(template)]


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
    return [name for name in extract_variable_names(template) if name not in variables]


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

    return _VAR_PATTERN.sub(_replace, template)
