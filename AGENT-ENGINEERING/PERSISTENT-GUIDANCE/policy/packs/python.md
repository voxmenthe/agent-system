# Python conventions

## Applies when

Load this pack before editing or reviewing Python source, `pyproject.toml`, `uv.lock`, Python test configuration, packaging metadata, or Python tooling and commands.

## Does not apply when

Do not load it merely because a repository contains Python when the current task does not inspect, execute, or change Python artifacts.

## Non-negotiable rules

- Follow the repository formatter and lint configuration; otherwise use PEP 8 and assume auto-formatting.
- Use `uv` unless the repository explicitly standardizes another workflow: `uv python` for interpreters, `uv run` for commands/scripts, `uv add` for dependencies, and `uv sync` for `pyproject.toml` environments.
- Type hints are required on public APIs and data-shape boundaries. Use `Optional[T]` only when `None` is reachable. `Any` means genuinely unconstrained, not postponed typing.
- Prefer dataclasses, typed dictionaries, protocols, enums, or discriminated unions over deeply nested optional unions and untyped dictionaries when shape is the contract.
- Comprehensions build values; loops express control flow. Never use a comprehension for side effects or logic that needs `break`/`continue`.

## Procedure

1. Inspect `pyproject.toml`, lock files, supported Python versions, formatter/linter/type-checker settings, and existing test commands before choosing syntax or tools.
2. Preserve the project’s import and typing conventions. Avoid adding compatibility shims for unsupported versions.
3. Keep `try/except` around only the operation that can raise. Catch concrete exceptions and retain useful causal context.
4. For multiline comprehensions, put one clause per line. One nesting level is acceptable; two usually deserves a named inner computation.
5. Trivial standard-library `import x` statements may share a line only when the repository allows it; `from x import y, z` stays grouped normally under the formatter.
6. Use module-private `_names` for internal helpers and `SCREAMING_SNAKE_CASE` for module constants. Encode policy in constant names; add a one-line comment only when the value records a non-obvious decision.
7. Avoid `getattr(x, "field", default)` or `.get()` when construction guarantees the field. Validate external input once, then rely on the typed internal model.
8. Add dependencies only for clear value. Prefer standard library solutions when they remain simple and correct.
9. Run the smallest relevant `uv run` tests and configured formatting, lint, and type checks. Do not invent commands when the repository documents them.

## Done criteria

- Code matches the configured Python version, formatter, lint, packaging, and type-checking rules.
- Public and boundary data shapes are typed without fictitious optionality or `Any` escape hatches.
- Errors are specific, invariants are trusted after validation, and control flow is not hidden in comprehensions.
- Dependency and lockfile changes are intentional, minimal, and reproducible with the repository workflow.
- Relevant tests and checks ran through the documented environment.
