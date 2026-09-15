# Contributing

Thanks for helping improve Rapid7 InsightConnect MCP.

The project is intentionally small and security-sensitive. Changes should keep the local-first, least-privilege design understandable to users as well as correct in code.

## Development setup

Requirements:

- Python 3.11+
- Git
- [uv](https://docs.astral.sh/uv/)

Clone the repository and install the locked development environment:

```sh
git clone https://github.com/sonadztux/rapid7-insightconnect-mcp.git
cd rapid7-insightconnect-mcp
uv sync --frozen
```

Run the same checks used by CI:

```sh
uv run ruff format --check .
uv run ruff check .
uv run mypy
uv run pytest -q
uv run pip-audit
uv build
```

The tests are designed to run without a real Rapid7 account. HTTP interactions are mocked and setup tests use temporary credential directories.

## Release preparation

Version 0.2.0 changes terminal onboarding: `configure` saves credentials, `setup` is a deprecated CLI alias, and `doctor` is offline unless `--online` is supplied. MCP registration remains the harness's responsibility.

Before an approved release:

1. Run formatting, lint (including complexity and security rules), types, deterministic tests, and dependency audit.
2. Run `uv build`; inspect both wheel and sdist for unexpected files or credentials. The sdist uses an explicit allowlist.
3. Smoke-test the wheel's installed executable with `--help`, `--version`, and offline `doctor` in an isolated configuration directory.
4. Obtain authorization for commits, branch push, PR, tagging, and PyPI publication. Do not treat local builds as publication.
5. After package ownership/authentication is configured by the maintainer, publish the reviewed 0.2.0 artifacts using the approved release process. Never put publishing tokens in the repository.
6. Verify `uvx rapid7-insightconnect-mcp --version` from the published package, then remove the README's pre-publication caveat.

`.github/workflows/release.yml` publishes on a pushed `v*` tag. It reruns the checks, builds, and uploads through a PyPI Trusted Publisher, so no publishing token is stored. It stays inert until the maintainer configures the PyPI Trusted Publisher and the `pypi` environment, and pushing a tag remains an authorized maintainer action.

## Pull requests

Keep pull requests focused. Explain:

- what user problem or bug the change addresses;
- the behavior before and after the change;
- security or compatibility implications;
- tests added or updated;
- documentation changes needed for user-visible behavior.

For bug fixes, prefer a regression test that fails before the fix and passes afterward.

## Security-sensitive changes

Take extra care when changing:

- `config.py` or credential precedence;
- `storage.py` or filesystem permissions/path handling;
- `setup_form.py` or the loopback setup flow;
- `client.py` or HTTP destinations, redirects, timeouts, limits, and redaction;
- write gating in `server.py`.

Security-sensitive behavior should fail closed. Avoid silently falling back to a less restrictive configuration.

Never add tests that depend on a real API key or live Rapid7 tenant.

See [SECURITY.md](SECURITY.md) for vulnerability reporting guidance.

## API surface

The MCP tool surface is intentionally narrower than the full Rapid7 API. New tools should have a clear assistant-facing use case and should not simply expose unrestricted raw REST access.

For mutations:

- keep writes disabled by default;
- require local write enablement;
- require explicit per-call confirmation;
- do not automatically retry requests with an uncertain outcome.

When adding or changing Rapid7 routes, update the API contract tests and the README tool/API tables.

## Documentation

User-facing instructions should describe the current behavior exactly, especially around credentials, write permissions, setup, and failure modes.

Prefer examples a first-time MCP user can copy safely. Never put real credentials, tokenized setup URLs, local usernames, or machine-specific private paths in committed examples.
