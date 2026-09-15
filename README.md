# Rapid7 InsightConnect MCP

[![CI](https://github.com/sonadztux/rapid7-insightconnect-mcp/actions/workflows/ci.yml/badge.svg)](https://github.com/sonadztux/rapid7-insightconnect-mcp/actions/workflows/ci.yml)

Use Rapid7 InsightConnect (Automation) from an MCP-compatible AI assistant. Find workflows, inspect jobs, read global artifacts, export snippets, and, only when you explicitly enable writes, run workflows or cancel jobs.

- **Local by design.** Your MCP client starts the server over stdio. There is no hosted service.
- **Read-only by default.** Workflow execution and job cancellation stay disabled until you turn them on.
- **API keys stay out of chat.** The recommended setup flow collects the key on a one-time local browser page.
- **Mutations need two gates.** Writes must be enabled locally and each execute/cancel call must include `confirm=true` after user approval.

**Get started:** [Install](#1-install) → [Add the server](#2-add-the-server-to-your-mcp-client) → [Connect Rapid7](#3-connect-your-rapid7-account) → [Try it](#4-try-it)

More: [Supported tools](#supported-tools) · [Desktop apps and WSL](#desktop-apps-and-wsl) · [Troubleshooting](#troubleshooting) · [Security model](#security-model) · [Development](#development)

## Requirements

- **Python 3.11+** and **[uv](https://docs.astral.sh/uv/getting-started/installation/)**
- An MCP client such as Claude Code, Codex, Hermes Agent, OpenCode, or Claude Desktop
- A Rapid7 API key and your organization's region

Give the Rapid7 key only the permissions you need. See [Rapid7 API keys](https://docs.rapid7.com/insight/api-overview/).

You do not need the API key to install. Until credentials are configured, the server still starts and exposes the `setup` tool, but it makes no Rapid7 requests.

> The shell examples below use Bash/Zsh on Linux, macOS, or WSL. Never paste a real Rapid7 API key into an assistant conversation or commit it to Git.

## 1. Install

Install [uv](https://docs.astral.sh/uv/getting-started/installation/). The release executable contract is:

```sh
uvx rapid7-insightconnect-mcp --help
```

**Release status:** version 0.2.0 is prepared here, not published by this change. Plain `uvx` requires an approved PyPI release. Until then, use a reviewed, pinned Git revision:

```sh
uvx --from 'git+https://github.com/sonadztux/rapid7-insightconnect-mcp.git@<COMMIT_SHA>' rapid7-insightconnect-mcp --help
```

Use the same `--from` prefix for registration, configure, and doctor before publication. A source checkout remains an option for [development](#development), not the normal installation interface.

## 2. Add the server to your MCP client

Your harness owns MCP registration and lifecycle. This server never detects clients, edits their settings, or generates client configuration. After publication:

### Claude Code

```sh
claude mcp add --transport stdio rapid7-insightconnect -- \
  uvx rapid7-insightconnect-mcp
```

### Codex

```sh
codex mcp add rapid7-insightconnect -- \
  uvx rapid7-insightconnect-mcp
```

### Other MCP clients

Use your client's native MCP command or settings:

```text
Command: uvx
Arguments: rapid7-insightconnect-mcp
```

Do not include Rapid7 credentials in registration. Enable the server and open a new session. Normally the harness starts it; running without arguments starts stdio, not an interactive wizard.

## 3. Connect your Rapid7 account

### Recommended: use the `setup` tool

1. Ask your assistant: **"Connect my Rapid7 InsightConnect account."**
2. Approve opening the local setup page when your MCP client asks.
3. Pick your region: `us`, `us2`, `us3`, `eu`, `ca`, `au`, or `ap`.
4. Paste the API key into the local page.
5. For a first test, leave **Allow workflow execution and cancellation** unchecked.
6. Click **Save**, return to the assistant, and wait for **"Ready. Region …"**.

The tools become available immediately in that server process. Other already-running copies may need a restart to load the saved settings.

**"Ready" means the settings were saved. It does not mean Rapid7 has accepted the key.** Your first read request is the real authentication check.

The setup page:

- binds only to `127.0.0.1` on an ephemeral port;
- uses a one-time token in the URL;
- sends the key directly to the local MCP server, not through the chat or MCP tool arguments;
- expires after five minutes, including time spent approving and filling the page.

Do not share the setup URL.

### Where credentials are stored

The local setup tool stores credentials at:

```text
~/.config/rapid7-insightconnect-mcp/credentials.json
```

If `XDG_CONFIG_HOME` is an absolute path, the file is stored under that directory instead. Relative values are ignored.

The credential directory is created with mode `0700` and the file with mode `0600`. The loader also rejects unsafe ownership, permissions, and symlinked paths because the stored file controls both the key and the write policy.

The key is **plain text protected by filesystem permissions**, not encrypted at rest.

### Fallback: terminal configuration

If the client cannot open the local page:

```sh
uvx rapid7-insightconnect-mcp configure
```

Enter the key at the hidden prompt, select your region, and leave writes disabled. Verification defaults to yes and makes one read-only workflows request. Failed verification leaves existing credentials unchanged. Declining verification saves unverified settings. Then restart already-running MCP sessions.

`setup` remains a deprecated CLI alias for `configure`; the MCP `setup` tool is unchanged. Neither CLI command generates harness configuration.

### Advanced: environment variables

Managed/CI environments may supply `R7_API_KEY`, `R7_REGION`, and optional `R7_ALLOW_WRITES` through their own secure mechanisms. Do not put keys in chat or command history.

- Presence of any of these three variables selects environment configuration.
- Both key and region are required; writes must be exactly `true` or `false`.
- Invalid or partial environment settings never fall back to stored credentials.
- Remove all three overrides to use saved settings. Restart affected sessions.

## 4. Try it

Start read-only:

> Use rapid7-insightconnect to list at most 5 workflows. Don't run anything.

Other useful prompts:

- "Show the latest 5 InsightConnect jobs."
- "List global artifacts whose name contains `blocklist`."
- "Read workflow `<workflow UUID>` and explain its trigger."
- "Export the published version of snippet `<snippet UUID>`."

Reading the result:

- A Rapid7 JSON response means the connection worked. An empty list can be normal.
- **"Credentials are not configured"** means the MCP server is reachable but setup is incomplete.
- **HTTP 401** usually means the key or region is wrong.
- **HTTP 403** usually means the key lacks permission.

To run workflows or cancel jobs, run setup again and enable writes. Even then, the assistant must send `confirm=true` for each mutation and should obtain your approval first.

Cancelling a job does not undo actions that already ran.

## Supported tools

| Tool | What it does |
| --- | --- |
| `setup` | Opens the one-time local setup page. |
| `list_workflows` / `get_workflow` | Find workflows or read one by UUID. |
| `execute_workflow` | Run an active API-triggered workflow without input. Requires writes enabled and `confirm=true`. |
| `list_jobs` / `get_job` | List jobs or read one by UUID. |
| `cancel_job` | Ask Rapid7 to cancel a job. Requires writes enabled and `confirm=true`. |
| `list_global_artifacts` / `get_global_artifact` | Find global artifacts or read one by UUID. |
| `list_artifact_entries` | Read the first page of an artifact's entries. |
| `export_snippet` | Export a snippet by UUID, published version by default. |

List tools return up to 30 items per call and use `offset` for paging where supported.

Resources:

- `insightconnect://server/config`
- `insightconnect://workflows/{workflow_id}`
- `insightconnect://jobs/{job_id}`
- `insightconnect://artifacts/{artifact_id}`

The config resource never contains the API key. It reports `setup_required` and `recommended_next_action` (`setup` or `list_workflows`).

## Desktop apps and WSL

Use the application's native MCP settings. Ensure `uvx` is on its launch PATH; desktop apps may not inherit your terminal PATH. Native Windows apps cannot execute Linux paths directly: configure the harness to launch inside WSL, with configuration and diagnostics under the same WSL user. Never expose the setup page publicly to work around localhost access; use `configure` instead.

## Troubleshooting

Start with local diagnostics; this makes no Rapid7 requests:

```sh
uvx rapid7-insightconnect-mcp doctor
```

For an explicit read-only authentication/connectivity check:

```sh
uvx rapid7-insightconnect-mcp doctor --online
```

Doctor reports runtime version, configuration source, region, write policy, secure storage validation, environment overrides, and connectivity status. Exit `0` means no failing checks (warnings can remain), `1` means attention needed, and invalid CLI arguments return `2`.

- Not configured: call `setup`, or run `configure` and restart.
- Saved settings ignored: remove all three credential-related environment overrides.
- Unsafe storage: check regular file ownership, private permissions and trusted parent directories; doctor does not repair files.
- HTTP 401: check key and region. HTTP 403: check Rapid7 permissions.
- Connection failure or timeout: check connectivity; no retry is made.
- Missing server: inspect registration/approval in your harness, not Rapid7 settings.
- Writes disabled: enable only when execution/cancellation is needed; per-call approval remains required.

## Configuration reference

| Variable | Purpose |
| --- | --- |
| `R7_API_KEY` | Rapid7 API key. Required with `R7_REGION` when environment configuration is selected. |
| `R7_REGION` | Rapid7 region. Required with `R7_API_KEY` when environment configuration is selected. |
| `R7_ALLOW_WRITES` | `true` or `false`; defaults to `false` for a complete env configuration. |
| `R7_SETUP_TIMEOUT` | Setup-page window in seconds. Default `300`. |
| `XDG_CONFIG_HOME` | Overrides the credential configuration directory when set to an absolute path. |

`.env` files are not loaded.

If environment or stored settings are missing/invalid, the server starts unconfigured so the `setup` tool remains available.

## Security model

- Rapid7 responses are treated as untrusted data, not instructions.
- The configured API key is masked if it appears in a response.
- Fields with credential-like names such as `password`, `secret`, `apiKey`, and `Authorization` are redacted before reaching the model. This is a safety net, not a guarantee. A secret stored in an ordinary field can still reach your assistant.
- Requests only go to the fixed Rapid7 regional API host over HTTPS.
- Redirects are disabled.
- Proxy environment settings are not used.
- Requests are not retried automatically.
- Request and response bodies are capped at 2 MiB.
- Mutation timeouts can have an unknown outcome. Check job state before retrying.
- Stored credentials are plaintext protected by strict POSIX ownership/permission checks.
- Keep your MCP client's own tool-approval controls enabled and use a least-privilege Rapid7 key.

See [SECURITY.md](SECURITY.md) for vulnerability reporting guidance.

### Intentional limits

Not supported yet:

- workflow input payloads;
- reading all pages of artifact entries;
- listing snippets;
- `me1` and `aps2` regions, because the available Rapid7 API documentation does not describe the required details.

Import, overwrite, artifact deletion, bulk changes, and unrestricted raw REST access are deliberately omitted.

## Development

```sh
uv sync --frozen
uv run ruff format --check .
uv run ruff check .
uv run mypy
uv run pytest -q
uv run pip-audit
uv build
```

The tests run offline. Rapid7 HTTP calls are mocked and setup tests use temporary credential directories.

See [CONTRIBUTING.md](CONTRIBUTING.md) before opening a pull request.

### Project layout

```text
insightconnect_mcp/
  cli.py            stdio, configure, doctor, version and help
  server.py         MCP tools and resources
  client.py         bounded Rapid7 HTTP client and response redaction
  config.py         settings, regions, and env precedence
  runtime.py        active client/settings lifecycle
  storage.py        owner-only credential persistence
  setup_form.py     one-time local setup page
  setup_wizard.py   terminal configuration entry point
  onboarding.py     shared verification, persistence and summaries
  diagnostics.py    structured offline and opt-in online checks
tests/
  data/insightconnect-api-v1.yaml   Rapid7 OpenAPI snapshot used for route checks
```

### API routes

| Tool | Rapid7 route |
| --- | --- |
| `list_workflows` | `GET /connect/v2/workflows` |
| `get_workflow` | `GET /connect/v2/workflows/{workflowId}` |
| `execute_workflow` | `POST /connect/v1/execute/async/workflows/{workflowId}` |
| `list_jobs` | `GET /connect/v1/jobs` |
| `get_job` | `GET /connect/v1/jobs/{jobId}` |
| `cancel_job` | `POST /connect/v1/jobs/{jobId}/events/cancel` |
| `list_global_artifacts` | `GET /connect/v1/globalArtifacts` |
| `get_global_artifact` | `GET /connect/v1/globalArtifacts/{globalArtifactId}` |
| `list_artifact_entries` | `GET /connect/v1/globalArtifacts/{globalArtifactId}/entities` |
| `export_snippet` | `GET /connect/v2/snippets/{snippetId}/export` |

Requests authenticate with `X-Api-Key` against `https://{region}.api.insight.rapid7.com`. The server preserves Rapid7 response structure while redacting the configured API key and values under credential-shaped field names.

Rapid7 sources: [REST API overview](https://docs.rapid7.com/insightconnect/insightconnect-rest-api/) · [OpenAPI spec](https://docs.rapid7.com/_api/insightconnect-api-v1.yaml)
