# Rapid7 InsightConnect MCP

[![CI](https://github.com/sonadztux/rapid7-insightconnect-mcp/actions/workflows/ci.yml/badge.svg)](https://github.com/sonadztux/rapid7-insightconnect-mcp/actions/workflows/ci.yml)

Use Rapid7 InsightConnect from an MCP-compatible AI assistant to find workflows, inspect jobs and artifacts, export snippets, and optionally run or cancel workflows.

> **Unofficial community project.** This project is independently developed and is not an official Rapid7 product. It is not provided, maintained, endorsed, or supported by Rapid7. References to Rapid7 and InsightConnect are used only to describe compatibility with Rapid7 InsightConnect.

- **Harness-agnostic:** your AI client owns MCP registration; this project only provides the MCP server.
- **Local by design:** there is no hosted middle service.
- **Read-only by default:** execution and cancellation stay disabled until you explicitly enable them.
- **API keys stay out of chat:** setup collects the key through a one-time local browser page.

## Quick start

You need an MCP-capable client, [`uv`](https://docs.astral.sh/uv/) with Python 3.11+, and a Rapid7 API key.

First, verify that the published package runs:

```sh
uvx rapid7-insightconnect-mcp --version
```

Do not run `uvx rapid7-insightconnect-mcp` directly in a terminal. The bare command starts the stdio MCP server and is meant to be launched by your MCP client, not used as an interactive setup command.

### 1. Add it to your AI client

**Claude Code**

```sh
claude mcp add --transport stdio --scope user rapid7-insightconnect -- \
  uvx rapid7-insightconnect-mcp
```

**Codex**

```sh
codex mcp add rapid7-insightconnect -- \
  uvx rapid7-insightconnect-mcp
```

For other local MCP clients, register a stdio server with:

```text
Command: uvx
Arguments: rapid7-insightconnect-mcp
```

The implementation does not detect or modify your AI client's configuration.

### 2. Connect Rapid7

Open a new AI session and ask:

> **Connect my Rapid7 InsightConnect account.**

The MCP should call its `setup` tool and open a one-time local page. Choose your Rapid7 region, paste the API key, and leave writes disabled for your first session.

The API key goes directly to the local MCP process, not through the conversation.

### 3. Test it read-only

Ask:

> **Use Rapid7 InsightConnect to list at most 5 workflows. Do not run anything.**

If you get a Rapid7 response, including an empty list, the connection is working.

## If setup does not open

Run the terminal fallback:

```sh
uvx rapid7-insightconnect-mcp configure
```

It securely prompts for the API key, verifies it with one read-only request by default, and saves it locally. A failed verification does not overwrite an existing valid credential.

Then restart the MCP session.

## Diagnose problems

Run local checks without contacting Rapid7:

```sh
uvx rapid7-insightconnect-mcp doctor
```

Add one explicit read-only API/authentication check with:

```sh
uvx rapid7-insightconnect-mcp doctor --online
```

Common failures:

| Problem | What to do |
| --- | --- |
| MCP does not appear | Check your client's MCP list/status and open a fresh session. |
| Setup page does not open | Run `uvx rapid7-insightconnect-mcp configure`. |
| HTTP 401 | Check the API key and Rapid7 region. |
| HTTP 403 | Check the API key's Rapid7 permissions. |
| Saved settings seem ignored | Run `doctor`; remove partial `R7_*` environment overrides if you want stored credentials. |
| Writes are disabled | Reconfigure and explicitly enable them only when needed. |

## What it can do

| Capability | MCP tools |
| --- | --- |
| Configure Rapid7 | `setup` |
| Find and inspect workflows | `list_workflows`, `get_workflow` |
| Run workflows | `execute_workflow` |
| Inspect and cancel jobs | `list_jobs`, `get_job`, `cancel_job` |
| Read global artifacts | `list_global_artifacts`, `get_global_artifact`, `list_artifact_entries` |
| Export snippets | `export_snippet` |

Workflow execution and job cancellation require **both** local write enablement and `confirm=true` on the individual MCP call after user approval.

The server does not automatically retry mutations after an uncertain outcome.

## Credentials and safety

Stored credentials live at:

```text
~/.config/rapid7-insightconnect-mcp/credentials.json
```

They are plain text protected by owner-only filesystem permissions. The loader rejects unsafe ownership, writable ancestry, unexpected file types, and symlinked credential paths.

Other security boundaries include:

- fixed Rapid7 regional HTTPS hosts;
- redirects and environment proxy inheritance disabled;
- bounded request and response bodies;
- validated API paths;
- sanitized upstream errors;
- credential-shaped response fields redacted before they reach the model;
- a loopback-only, tokenized, expiring setup page;
- no raw REST passthrough tool.

See [SECURITY.md](SECURITY.md) for the full security model and vulnerability reporting.

## Advanced configuration

Environment variables are supported for CI and managed deployments:

| Variable | Purpose |
| --- | --- |
| `R7_API_KEY` | Rapid7 API key |
| `R7_REGION` | `us`, `us2`, `us3`, `eu`, `ca`, `au`, or `ap` |
| `R7_ALLOW_WRITES` | `true` or `false` |
| `R7_SETUP_TIMEOUT` | Local setup-page timeout in seconds; default `300` |
| `XDG_CONFIG_HOME` | Alternate absolute config directory |

Configuration fails closed: if any credential-related `R7_*` variable is present, environment configuration is selected and both `R7_API_KEY` and `R7_REGION` are required. Incomplete environment configuration does not fall back to stored credentials.

`.env` files are not loaded.

## Platform notes

The hardened credential store currently targets POSIX systems: Linux, macOS, and WSL on Windows.

Desktop apps may not inherit your shell `PATH`. If they cannot find `uvx`, use the absolute path from:

```sh
command -v uvx
```

On Windows, run the MCP inside WSL rather than as a native Windows process.

## Development

End users should prefer `uvx`. Contributors can install from source:

```sh
git clone https://github.com/sonadztux/rapid7-insightconnect-mcp.git
cd rapid7-insightconnect-mcp
uv sync --frozen
```

Run the same checks as CI:

```sh
uv run ruff format --check .
uv run ruff check .
uv run mypy
uv run pytest -q
uv run pip-audit
uv build
```

See [CONTRIBUTING.md](CONTRIBUTING.md) for contribution guidance and [RELEASING.md](RELEASING.md) for the PyPI release process.

## License

Licensed under the [MIT License](LICENSE.md).
