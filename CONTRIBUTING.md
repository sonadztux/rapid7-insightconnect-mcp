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
uv sync --frozen --extra dev
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
