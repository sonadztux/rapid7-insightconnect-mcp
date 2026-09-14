# Rapid7 InsightConnect MCP

[![CI](https://github.com/sonadztux/rapid7-insightconnect-mcp/actions/workflows/ci.yml/badge.svg)](https://github.com/sonadztux/rapid7-insightconnect-mcp/actions/workflows/ci.yml)

Use Rapid7 InsightConnect (Automation) from an MCP-compatible AI assistant. Discover workflows, inspect jobs, read global artifacts, export snippets, and, only when you explicitly enable writes, execute workflows or cancel jobs.

- **Harness-agnostic.** Your MCP client owns registration and lifecycle; this project only needs to be launched as a local stdio MCP server.
- **Local by design.** There is no hosted middle service.
- **Read-only by default.** Execution and cancellation remain disabled until you explicitly enable them.
- **API keys stay out of chat.** The normal setup flow collects the key through a one-time local browser page.
- **Mutations need two gates.** Writes must be enabled locally and each execute/cancel call still requires `confirm=true` after user approval.

## Mental model

```text
Your MCP client / AI harness
        │
        │ starts over stdio
        ▼
rapid7-insightconnect-mcp
        │
        │ HTTPS + Rapid7 API key
        ▼
Rapid7 InsightConnect
```

**Your harness owns MCP registration. This project owns Rapid7 setup, credentials, tools, safety, and diagnostics.**

## Quick start

You need:

- an MCP-capable client such as Claude Code, Codex, Hermes Agent, or OpenCode;
- [`uv`](https://docs.astral.sh/uv/) with Python 3.11+ available in a POSIX environment (Linux, macOS, or WSL on Windows);
- a Rapid7 API key and your organization's Rapid7 region.

Do not put the Rapid7 API key in the MCP registration command or in an assistant conversation.

### 1. Add the MCP through your harness

The executable contract is always:

```sh
uvx rapid7-insightconnect-mcp
```

Your harness decides how that command is registered.

#### Claude Code

```sh
claude mcp add --transport stdio --scope user rapid7-insightconnect -- \
  uvx rapid7-insightconnect-mcp
```

Check it with:

```sh
claude mcp get rapid7-insightconnect
```

You can use `--scope project` instead if you only want the server in one project.

#### Codex

```sh
codex mcp add rapid7-insightconnect -- \
  uvx rapid7-insightconnect-mcp
```

Check it with:

```sh
codex mcp list
```

#### Hermes Agent

```sh
hermes mcp add rapid7-insightconnect --command uvx \
  --args rapid7-insightconnect-mcp
```

Then:

```sh
hermes mcp test rapid7-insightconnect
```

#### OpenCode

```sh
opencode mcp add rapid7-insightconnect -- \
  uvx rapid7-insightconnect-mcp
```

Then:

```sh
opencode mcp list
```

#### Any other local MCP client

Configure one local/stdio server with:

```text
Command: uvx
Arguments: rapid7-insightconnect-mcp
```

The implementation does not detect or modify your harness configuration.

### 2. Connect Rapid7 from inside the harness

Open a new session and ask:

> **Connect my Rapid7 InsightConnect account.**

The MCP server instructs the model to call its `setup` tool when Rapid7 is not configured. Your client should offer to open a one-time local setup page.

On that page:

1. choose your Rapid7 region: `us`, `us2`, `us3`, `eu`, `ca`, `au`, or `ap`;
2. paste the Rapid7 API key;
3. leave **Allow workflow execution and cancellation** unchecked for your first session;
4. save the configuration.

The API key is submitted directly to the local MCP process. It is not passed as an MCP tool argument and should never appear in the conversation.

After setup succeeds, the server reports the selected region and whether writes are enabled, then recommends a read-only check.

### 3. Verify access read-only

Ask:

> **Use Rapid7 InsightConnect to list at most 5 workflows. Do not run anything.**

A Rapid7 JSON response, including an empty list, means the connection worked. HTTP `401` usually means the API key or region is wrong. HTTP `403` usually means the key lacks the required Rapid7 permissions.

### 4. Diagnose problems with one command

Run local diagnostics without contacting Rapid7:

```sh
uvx rapid7-insightconnect-mcp doctor
```

The doctor reports the package version, selected configuration source, region, write policy, and whether stored credential security validation passed.

To add one explicit read-only Rapid7 connectivity/authentication check:

```sh
uvx rapid7-insightconnect-mcp doctor --online
```

`doctor --online` never executes a workflow or cancels a job.

## If your MCP client cannot open the setup page

Use the harness-agnostic terminal fallback:

```sh
uvx rapid7-insightconnect-mcp configure
```

The terminal flow:

- asks for region and write policy;
- reads the API key with hidden input;
- performs one read-only Rapid7 verification by default;
- saves the credential through the same hardened local credential store used by the MCP `setup` tool.

If verification fails, the new credential is **not** persisted, so an existing valid stored credential is not overwritten by a bad replacement.

After configuration, restart any already-running MCP client/session so a fresh MCP process loads the saved settings.

For compatibility, the old CLI command:

```sh
rapid7-insightconnect-mcp setup
```

currently forwards to `configure`. The MCP **tool** remains named `setup`.

## Credential storage

The local setup flow stores credentials at:

```text
~/.config/rapid7-insightconnect-mcp/credentials.json
```

If `XDG_CONFIG_HOME` is an absolute path, the file is stored underneath that directory instead. Relative values are ignored.

The storage layer creates the credential directory with mode `0700` and the credential file with mode `0600`. Loading also rejects unsafe ownership, unsafe writable ancestry, unexpected file types, and symlinked paths because the file contains both the API key and the local write policy.

The API key is **plain text protected by filesystem permissions**, not encrypted at rest.

## Advanced configuration: environment variables

Environment variables are supported for CI, managed environments, or MCP clients whose own secret-storage workflow you prefer. They are not required for normal onboarding.

| Variable | Purpose |
| --- | --- |
| `R7_API_KEY` | Rapid7 API key. Required with `R7_REGION` when environment configuration is selected. |
| `R7_REGION` | Rapid7 region. Required with `R7_API_KEY` when environment configuration is selected. |
| `R7_ALLOW_WRITES` | `true` or `false`; defaults to `false` for a complete environment configuration. |
| `R7_SETUP_TIMEOUT` | Local setup-page window in seconds. Default `300`. |
| `XDG_CONFIG_HOME` | Overrides the credential configuration directory when absolute. |

Configuration is deliberately fail-closed:

- if **any** of `R7_API_KEY`, `R7_REGION`, or `R7_ALLOW_WRITES` is present, environment configuration is selected;
- both `R7_API_KEY` and `R7_REGION` must then be present and non-empty;
- incomplete environment configuration does **not** fall back to a stored credential;
- `R7_ALLOW_WRITES`, when supplied, must be exactly `true` or `false`.

`.env` files are not loaded.

## Supported tools

| Tool | What it does |
| --- | --- |
| `setup` | Opens the one-time local Rapid7 setup page. |
| `list_workflows` / `get_workflow` | Find workflows or read one by UUID. |
| `execute_workflow` | Execute an active API-triggered workflow without input. Requires writes enabled and `confirm=true`. |
| `list_jobs` / `get_job` | List jobs or read one by UUID. |
| `cancel_job` | Request job cancellation. Requires writes enabled and `confirm=true`. |
| `list_global_artifacts` / `get_global_artifact` | Find global artifacts or read one by UUID. |
| `list_artifact_entries` | Read artifact entities. Upstream documentation does not currently define pagination parameters for this route. |
| `export_snippet` | Export a snippet by UUID, published version by default. |

List tools return bounded pages of at most 30 items per call where the upstream API supports paging.

### Resources

- `insightconnect://server/config`
- `insightconnect://workflows/{workflow_id}`
- `insightconnect://jobs/{job_id}`
- `insightconnect://artifacts/{artifact_id}`

The server config resource is non-secret. It includes whether setup is required and a recommended next action, but never contains the API key.

## Writes and mutation safety

Read-only behavior is the default.

To execute a workflow or cancel a job, two independent gates must both pass:

1. writes must be enabled in the local Rapid7 configuration;
2. the individual MCP mutation call must include `confirm=true` after explicit user approval.

The server instructions also tell the model not to automatically retry a mutation after an uncertain outcome. A timeout can occur after Rapid7 has already accepted a request, so automatic retries could duplicate an external action.

Cancelling a job does not undo actions that already ran.

## Security model

Important boundaries:

- Rapid7 responses are untrusted data, not instructions to the model.
- The server only connects to fixed HTTPS hosts derived from the supported Rapid7 region enum.
- HTTP redirects are disabled.
- Environment proxy inheritance is disabled (`trust_env=False`).
- Request and response bodies are bounded.
- API paths are validated before requests are sent.
- Upstream failures are converted to sanitized errors.
- Credential-shaped fields and occurrences of the configured API key are redacted from Rapid7 JSON before results reach the model.
- The browser setup listener binds only to loopback, uses a one-time token, validates request framing, and expires.
- Stored credentials use strict owner-only filesystem checks.
- There is no raw REST passthrough tool.
- Destructive/bulk import-style capabilities are intentionally not exposed.

Responses preserve Rapid7 response structure where possible, with credential-like values redacted.

See [SECURITY.md](SECURITY.md) for vulnerability reporting and security-sensitive contribution guidance.

## Troubleshooting

| Problem | What to do |
| --- | --- |
| MCP server does not appear | Use your harness's MCP list/status command and open a fresh session after registration. |
| `uvx` cannot find the package | Confirm `uv` is installed and that `rapid7-insightconnect-mcp` is available from PyPI. |
| Rapid7 is not connected | Ask the assistant to connect Rapid7 so it calls the MCP `setup` tool, or run `uvx rapid7-insightconnect-mcp configure`. |
| Setup page cannot open | Run `uvx rapid7-insightconnect-mcp configure`, then restart the MCP session. |
| Saved settings seem ignored | Run `doctor`. Remove all credential-related `R7_*` variables if you intend to use the stored credential. |
| Partial environment configuration | Set both `R7_API_KEY` and `R7_REGION`, or remove all credential-related `R7_*` variables. |
| HTTP 401 | Check the API key and Rapid7 region. |
| HTTP 403 | Check the API key's Rapid7 permissions. |
| `Writes are disabled` | Reconfigure and explicitly enable workflow execution/cancellation only when needed. |
| Unsure what is wrong | Run `uvx rapid7-insightconnect-mcp doctor`; add `--online` only when you want a read-only network/auth check. |

## Desktop apps, PATH, and Windows

Desktop applications do not always inherit your interactive shell's `PATH`. If a desktop MCP client cannot find `uvx`, use the absolute path returned by:

```sh
command -v uvx
```

as the configured command, with:

```text
rapid7-insightconnect-mcp
```

as its argument.

The hardened credential-storage implementation currently targets POSIX systems. On Windows, run the MCP server inside WSL rather than running it as a native Windows process. A native Windows harness can launch the WSL command through `wsl.exe`; the credential file then belongs to the Linux user inside WSL.

Do not expose the local setup listener on a public interface to work around desktop/WSL localhost differences.

## Install from source for development

End users should prefer `uvx`. Contributors can clone the repository:

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

Start the development checkout as an MCP server with:

```sh
uv run rapid7-insightconnect-mcp
```

Or exercise its user-facing CLI:

```sh
uv run rapid7-insightconnect-mcp --help
uv run rapid7-insightconnect-mcp configure
uv run rapid7-insightconnect-mcp doctor
```

See [CONTRIBUTING.md](CONTRIBUTING.md) for contribution expectations.

## Release model

GitHub is the source and contribution surface. PyPI is the executable distribution surface. MCP registration remains owned by each harness.

Releases are published from GitHub Releases through OIDC trusted publishing; the repository does not need to store a PyPI API token. Maintainer setup and release steps are documented in [RELEASING.md](RELEASING.md).
