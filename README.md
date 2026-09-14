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

- **Python 3.11+**, **Git**, and **[uv](https://docs.astral.sh/uv/getting-started/installation/)**
- An MCP client such as Claude Code, Codex, Hermes Agent, OpenCode, or Claude Desktop
- A Rapid7 API key and your organization's region

Give the Rapid7 key only the permissions you need. See [Rapid7 API keys](https://docs.rapid7.com/insight/api-overview/).

You do not need the API key to install. Until credentials are configured, the server still starts and exposes the `setup` tool, but it makes no Rapid7 requests.

> The shell examples below use Bash/Zsh on Linux, macOS, or WSL. Never paste a real Rapid7 API key into an assistant conversation or commit it to Git.

## 1. Install

Clone the repository and install the locked dependencies:

```sh
git clone https://github.com/sonadztux/rapid7-insightconnect-mcp.git
cd rapid7-insightconnect-mcp
uv sync --frozen --no-dev

MCP_BIN="$(pwd)/.venv/bin/rapid7-insightconnect-mcp"
"$MCP_BIN" --help
```

You should see usage text mentioning `setup`. You do **not** normally start the MCP server yourself. Your MCP client launches it when needed.

Keep the checkout where it is. MCP clients configured with the launcher path will need to be updated if you move the folder.

<details>
<summary><strong>Alternative: run directly from Git with <code>uvx</code></strong></summary>

`uvx` can download, cache, and launch the server without a clone. Pin a commit for reproducible installs:

```sh
MCP_SOURCE="git+https://github.com/sonadztux/rapid7-insightconnect-mcp.git@<COMMIT_SHA>"
UVX_BIN="$(command -v uvx)"
"$UVX_BIN" --from "$MCP_SOURCE" rapid7-insightconnect-mcp --help
```

Then register that command with your MCP client. For example:

```sh
# Claude Code
claude mcp add --transport stdio --scope project rapid7-insightconnect -- \
  "$UVX_BIN" --from "$MCP_SOURCE" rapid7-insightconnect-mcp

# Codex
codex mcp add rapid7-insightconnect -- \
  "$UVX_BIN" --from "$MCP_SOURCE" rapid7-insightconnect-mcp

# Hermes Agent (--args must come last)
hermes mcp add rapid7-insightconnect --command "$UVX_BIN" \
  --args --from "$MCP_SOURCE" rapid7-insightconnect-mcp
```

For OpenCode or a desktop app, use the absolute `uvx` path as the command and `--from <MCP_SOURCE> rapid7-insightconnect-mcp` as its arguments.

Notes:

- This route needs network access the first time.
- It does not use the repository's `uv.lock`, so dependency resolution can differ from the clone install.
- The package is not currently published on PyPI, so plain `uvx rapid7-insightconnect-mcp` does not work yet.

Then continue with [Connect your Rapid7 account](#3-connect-your-rapid7-account).

</details>

## 2. Add the server to your MCP client

These examples use `MCP_BIN` from the install step. In a new terminal, run this again from the repository root:

```sh
MCP_BIN="$(pwd)/.venv/bin/rapid7-insightconnect-mcp"
```

Registration only needs the launcher path. **Do not put your Rapid7 API key in these commands.**

### Claude Code

```sh
claude mcp add --transport stdio --scope project rapid7-insightconnect -- "$MCP_BIN"
claude mcp get rapid7-insightconnect
claude
```

- `--scope project` stores the entry in that project's `.mcp.json`.
- Use `--scope user` instead if you want the server available across projects.
- In Claude Code, use `/mcp` to check the connection and approve the server if prompted.

See the [Claude Code MCP docs](https://code.claude.com/docs/en/mcp).

### Codex

```sh
codex mcp add rapid7-insightconnect -- "$MCP_BIN"
codex mcp list
codex
```

In Codex, use `/mcp` to check the server. `codex mcp login` is not needed because this server authenticates to Rapid7 with an API key, not OAuth.

See the [Codex MCP docs](https://developers.openai.com/codex/mcp/).

### Hermes Agent

```sh
hermes mcp add rapid7-insightconnect --command "$MCP_BIN"
hermes mcp list
hermes
```

If Hermes asks `Enable all 11 tools? [Y/n/select]`, choose `Y` or select the tools you want. Start a new Hermes session afterwards. If Hermes reports **"No inference provider configured"**, run `hermes model` first.

See the [Hermes docs](https://hermes-agent.nousresearch.com/docs/).

### OpenCode

Add this `mcp` entry to `opencode.json`, replacing the path with the output of `echo "$MCP_BIN"`:

```json
{
  "$schema": "https://opencode.ai/config.json",
  "mcp": {
    "rapid7-insightconnect": {
      "type": "local",
      "command": ["/absolute/path/to/rapid7-insightconnect-mcp/.venv/bin/rapid7-insightconnect-mcp"],
      "enabled": true
    }
  }
}
```

Then check it:

```sh
opencode mcp list
opencode
```

OpenCode may prefix tool names, for example `rapid7-insightconnect_list_workflows`. See [OpenCode MCP servers](https://opencode.ai/docs/mcp-servers/).

## 3. Connect your Rapid7 account

### Recommended: use the `setup` tool

1. Ask your assistant: **"Run the setup tool from rapid7-insightconnect."**
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

### Alternative: environment variables

Use environment variables when your MCP client cannot open the local setup page or when you prefer the client's own secret storage.

```sh
read -r -s -p 'Rapid7 API key: ' R7_API_KEY; printf '\n'
export R7_API_KEY
export R7_REGION=eu
export R7_ALLOW_WRITES=false

claude    # or: codex, hermes, opencode
```

Configuration fails closed:

- if **any** of `R7_API_KEY`, `R7_REGION`, or `R7_ALLOW_WRITES` is present, environment configuration is selected;
- both `R7_API_KEY` and `R7_REGION` are required;
- incomplete environment configuration does **not** silently fall back to saved credentials;
- `R7_ALLOW_WRITES` must be exactly `true` or `false` when set.

Desktop apps launched from an icon often do not inherit your shell environment. Use the app's MCP/environment settings instead.

For a guided terminal walkthrough, run:

```sh
"$MCP_BIN" setup
```

That wizard can verify the key with one read-only Rapid7 request and prints a configuration example. It deliberately does **not** save the credential.

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

The config resource never contains the API key.

## Desktop apps and WSL

Desktop applications and similarly named CLI tools do not necessarily share MCP configuration. The application must be able to execute the server launcher on the machine where the app runs.

### Claude Desktop

Open **Settings → Developer → Edit Config** and add:

```json
{
  "mcpServers": {
    "rapid7-insightconnect": {
      "command": "/absolute/path/to/rapid7-insightconnect-mcp/.venv/bin/rapid7-insightconnect-mcp",
      "args": []
    }
  }
}
```

Quit Claude Desktop completely and reopen it.

### Codex desktop app

Register the server with the Codex CLI under the same user account, or add this to `~/.codex/config.toml`:

```toml
[mcp_servers.rapid7-insightconnect]
command = "/absolute/path/to/rapid7-insightconnect-mcp/.venv/bin/rapid7-insightconnect-mcp"
args = []
```

Then enable the server in the app's MCP settings and open a new session.

### Hermes Desktop

Complete the Hermes registration first, then start the desktop app from your project folder:

```sh
hermes desktop --cwd "$PWD"
```

### OpenCode Desktop

Open the project containing your `opencode.json` MCP entry, restart the backend, and check for `rapid7-insightconnect` in the MCP tool list.

### Windows app with the server in WSL

A native Windows app cannot execute a Linux path directly. If the app accepts an arbitrary command, launch the server through `wsl.exe`:

```json
{
  "mcpServers": {
    "rapid7-insightconnect": {
      "command": "wsl.exe",
      "args": [
        "--distribution", "<DISTRO_NAME>",
        "--exec", "/absolute/linux/path/to/rapid7-insightconnect-mcp/.venv/bin/rapid7-insightconnect-mcp"
      ]
    }
  }
}
```

Run `wsl --list --quiet` in PowerShell to find the distribution name. Saved credentials belong to the WSL user. Do not expose the setup page on a public interface to work around localhost issues.

## Troubleshooting

| Problem | What to try |
| --- | --- |
| `command not found`, or the server will not start | Use the absolute launcher path and run `"$MCP_BIN" --help` to verify the install. |
| Server does not appear in the client | Check the client's MCP list, approve/enable the server, then open a new session. |
| Tool call denied | Approve the tool in the MCP client. Do not disable all permission checks. |
| "Credentials are not configured" | Run the `setup` tool, or configure `R7_API_KEY` and `R7_REGION`. |
| Saved settings seem ignored | Remove **all** `R7_API_KEY`, `R7_REGION`, and `R7_ALLOW_WRITES` values from the MCP server environment if you want stored credentials to be used. |
| Environment configuration fails | If any credential-related `R7_*` variable is present, set both `R7_API_KEY` and `R7_REGION`; `R7_ALLOW_WRITES` must be `true` or `false`. |
| Setup times out or the client cannot open the page | Call setup again or use environment variables/client secret storage instead. |
| HTTP 401 or 403 | Check the API key, region, and Rapid7 permissions. |
| "Writes are disabled" | Run setup with writes enabled, or set a complete environment configuration with `R7_ALLOW_WRITES=true`. |
| Hermes: "No inference provider configured" | Run `hermes model`. The AI model and Rapid7 credentials are configured separately. |

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
  cli.py            command line: serve over stdio, or run the setup wizard
  server.py         MCP tools and resources
  client.py         bounded Rapid7 HTTP client and response redaction
  config.py         settings, regions, and env precedence
  runtime.py        active client/settings lifecycle
  storage.py        owner-only credential persistence
  setup_form.py     one-time local setup page
  setup_wizard.py   terminal onboarding walkthrough
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
