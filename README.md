# Rapid7 InsightConnect MCP

Use Rapid7 InsightConnect / Automation from your AI assistant: find workflows, inspect jobs, read global artifacts, export snippets, and optionally execute workflows or cancel jobs.

Runs locally in Python over **MCP stdio**. No hosted MCP service is required. Workflow execution and cancellation are **disabled by default**.

**Start here:** [Install](#1-install-the-server) → [Add to your harness](#2-add-to-your-harness) → [Connect Rapid7](#3-connect-your-rapid7-account) → [Try it](#4-try-your-first-request).

Also: [Desktop apps and WSL](#desktop-apps-and-wsl) · [Troubleshooting](#troubleshooting) · [Tools](#available-tools) · [Development](#development).

## Before you start

You need:

- **Python 3.11+**, **Git**, and **[uv](https://docs.astral.sh/uv/getting-started/installation/)**. Follow the linked uv installer for your operating system if it is not installed.
- An installed MCP-capable harness, such as Claude Code, Codex, Hermes Agent, or OpenCode. Configure its model/provider first; the Rapid7 key does not authenticate your AI provider.
- A Rapid7 API key and your organization's region. Use the minimum permissions you need. See [Rapid7 API authentication](https://docs.rapid7.com/insight/api-overview/).

You can install and connect the MCP server **before you have a Rapid7 key**. It will offer setup instead of making API requests.

> The shell examples below use Bash/Zsh on Linux, macOS, or WSL. Run them in your own terminal, not through an assistant tool when entering secrets. Native Windows desktop apps need the [WSL launcher instructions](#windows-desktop-app-with-the-server-in-wsl).

## 1. Install the server

### Recommended: clone and install

```sh
git clone https://github.com/sonadztux/rapid7-insightconnect-mcp.git
cd rapid7-insightconnect-mcp

uv sync --frozen --no-dev

# Keep this terminal open for the harness commands below.
MCP_BIN="$(pwd)/.venv/bin/rapid7-insightconnect-mcp"
"$MCP_BIN" --help
```

Already have the source folder? Skip `git clone`, enter that folder, and run from `uv sync` onward.

**Expected result:** help output mentioning `setup` and serving MCP over stdio. You do not need to start a server manually and leave it running: your harness launches it when needed.

`--frozen` uses the committed dependency lockfile; `--no-dev` skips development tools. Keep this folder in place after registration—the harness will point to its executable. If you move it, register the new path.

> The package is not published on PyPI. Do not use a bare `uvx rapid7-insightconnect-mcp` as a substitute for installing this source.

### Alternative: add directly from Git with uvx

A harness can use `uvx` to install/cache and launch the server without a manual clone or virtual environment. Pin an immutable commit SHA:

```sh
MCP_SOURCE="git+https://github.com/sonadztux/rapid7-insightconnect-mcp.git@<COMMIT_SHA>"
UVX_BIN="$(command -v uvx)"

# Prewarm the cache and check installation before adding it to a harness.
"$UVX_BIN" --from "$MCP_SOURCE" rapid7-insightconnect-mcp --help
```

For example, register it with **one** of these commands:

```sh
# Claude Code — this project
claude mcp add --transport stdio --scope project rapid7-insightconnect -- \
  "$UVX_BIN" --from "$MCP_SOURCE" rapid7-insightconnect-mcp

# Codex
codex mcp add rapid7-insightconnect -- \
  "$UVX_BIN" --from "$MCP_SOURCE" rapid7-insightconnect-mcp

# Hermes Agent — --args must be the last option
hermes mcp add rapid7-insightconnect --command "$UVX_BIN" \
  --args --from "$MCP_SOURCE" rapid7-insightconnect-mcp
```

For **OpenCode**, merge this entry into the project's `opencode.json`. Replace both placeholders with the values prepared above:

```json
{
  "mcp": {
    "rapid7-insightconnect": {
      "type": "local",
      "command": ["<ABSOLUTE_UVX_PATH>", "--from", "<MCP_SOURCE>", "rapid7-insightconnect-mcp"],
      "enabled": true
    }
  }
}
```

For a desktop config using separate fields, use the absolute `uvx` path as `command` and `["--from", "<MCP_SOURCE>", "rapid7-insightconnect-mcp"]` as `args`.

This route needs network access for the first installation and resolves dependencies from package metadata; it does **not** use this project's `uv.lock`. Choose the clone route for a locked installation. Private repositories also require Git access. If you prewarm successfully, continue at [Connect Rapid7](#3-connect-your-rapid7-account); do not also register the clone version under the same name.

## 2. Add to your harness

The examples in this section use `MCP_BIN` from the clone installation above. If you opened another terminal, enter the cloned folder and run:

```sh
MCP_BIN="$(pwd)/.venv/bin/rapid7-insightconnect-mcp"
```

Choose your harness. **No Rapid7 credentials belong in these registration commands.**

### Claude Code

From the project where you want to use the server:

```sh
claude mcp add --transport stdio --scope project rapid7-insightconnect -- "$MCP_BIN"
claude mcp get rapid7-insightconnect
claude
```

- `--scope project` writes an entry to that project's `.mcp.json`. It contains a launcher path, not your Rapid7 key. Review before sharing; paths differ between machines.
- Prefer a personal registration across projects? Use `--scope user` instead; this changes your Claude Code user configuration.
- In the interactive session, open `/mcp` to check connection status and approve the project server if prompted.

Then send: **“Run the setup tool from rapid7-insightconnect.”**

[Claude Code MCP documentation](https://code.claude.com/docs/en/mcp).

### Codex

```sh
codex mcp add rapid7-insightconnect -- "$MCP_BIN"
codex mcp list
codex
```

This registers the server in Codex's user configuration. In the interactive session, use `/mcp` to inspect available servers/tools, then send: **“Run the setup tool from rapid7-insightconnect.”**

Do not use `codex mcp login` for this server. That command is for MCP OAuth flows; this server uses a Rapid7 API key entered through setup or the environment.

[Codex MCP documentation](https://developers.openai.com/codex/mcp/).

### Hermes Agent

```sh
hermes mcp add rapid7-insightconnect --command "$MCP_BIN"
hermes mcp list
hermes
```

The add command connects and discovers **11 tools**. At `Enable all 11 tools? [Y/n/select]`, choose `Y` or select the tools you want. Then start a new Hermes session and send: **“Run the setup tool from rapid7-insightconnect.”**

This changes the active Hermes profile's configuration. If Hermes reports **“No inference provider configured”**, run `hermes model` first. MCP discovery can succeed without a model, but model-driven tool calls cannot.

If you supply launcher arguments, put `--args` last. Otherwise Hermes may pass options such as `--env` to the MCP executable by mistake.

[Hermes documentation](https://hermes-agent.nousresearch.com/docs/).

### OpenCode

OpenCode uses a project configuration file. Create or edit `opencode.json` in the project where you will run it; **merge** the following `mcp` entry with existing settings rather than replacing the file:

```json
{
  "$schema": "https://opencode.ai/config.json",
  "mcp": {
    "rapid7-insightconnect": {
      "type": "local",
      "command": ["/absolute/path/rapid7-insightconnect-mcp/.venv/bin/rapid7-insightconnect-mcp"],
      "enabled": true
    }
  }
}
```

Replace the example path with the output of `printf '%s\n' "$MCP_BIN"`.

```sh
opencode mcp list
opencode
```

Look for `rapid7-insightconnect` connected, then send: **“Run the setup tool from rapid7-insightconnect.”** OpenCode may display tool names with a prefix, such as `rapid7-insightconnect_list_workflows`.

For a personal configuration across projects, use OpenCode's global `opencode.json` instead of the project file. See [OpenCode MCP servers](https://opencode.ai/docs/mcp-servers/) and [configuration](https://opencode.ai/docs/config/).

## 3. Connect your Rapid7 account

### Preferred: setup from your assistant

1. Ask: **“Run the setup tool from rapid7-insightconnect. Do not ask me for my API key in chat.”**
2. If your harness supports **MCP URL elicitation**, approve opening the temporary local setup page.
3. Choose your region: `us`, `us2`, `us3`, `eu`, `ca`, `au`, or `ap`.
4. Enter your API key in the page's password field. Leave **Allow workflow execution and cancellation** unchecked for your first test.
5. Click **Save**, return to the assistant, and wait for **“Ready. Region …”**.

The current server process uses the new settings immediately. Other already-running MCP instances need to restart to load the saved settings.

**“Ready” means settings were saved and loaded, not that Rapid7 accepted the key.** The browser setup currently makes no verification request. The first read-only tool call checks access in practice.

The browser flow saves plaintext credentials to:

```text
~/.config/rapid7-insightconnect-mcp/credentials.json
```

If `XDG_CONFIG_HOME` is set, it uses `$XDG_CONFIG_HOME/rapid7-insightconnect-mcp/credentials.json`. On Linux/WSL, the directory is `0700` and file is `0600`. Processes running as your user can still read it. Harnesses using the same user and config location share this saved account; this is not a multi-account profile manager.

The setup page uses loopback HTTP on `127.0.0.1`, not a hosted site. Its URL carries a temporary token; do not share it. The credential goes through the local form, not an MCP tool argument. Keep the tool call running while you fill in the page. Browser/URL elicitation support and tool timeouts vary by harness.

### If the harness cannot open setup

The terminal command provides a guided walkthrough and optional read-only verification:

```sh
# Clone installation:
"$MCP_BIN" setup

# Or, if you registered the Git/uvx version:
"$UVX_BIN" --from "$MCP_SOURCE" rapid7-insightconnect-mcp setup
```

**Current limitation:** the terminal wizard prints a config example but does **not** save credentials or configure your harness. Restarting after that wizard alone will not finish setup. Use your harness's secret/environment settings, or start a CLI harness from a terminal with credentials entered privately:

```sh
# Bash example. Run yourself in an interactive terminal; do not paste the key into chat.
read -r -s -p 'Rapid7 API key: ' R7_API_KEY; printf '\n'
export R7_API_KEY
export R7_REGION=eu
export R7_ALLOW_WRITES=false

# Start ONE harness from this same terminal:
claude
# or: codex
# or: hermes
# or: opencode
```

Use your actual region. The key is not part of the command text, but is inherited through the process environment. A CLI harness must pass these variables to its MCP child. Desktop apps launched from an icon may not inherit them; use the app's supported environment/secret configuration instead. Never replace a placeholder with a real key in a tracked file.

## 4. Try your first request

Start with a read-only request:

> Use rapid7-insightconnect to list at most 5 workflows. Do not execute anything.

Then try:

- “Show the latest 5 InsightConnect jobs.”
- “List global artifacts whose name contains `blocklist`.”
- “Read workflow `<workflow UUID>` and explain its trigger.”
- “Get the current details for job `<job UUID>`.”
- “Export the published version of snippet `<snippet UUID>`.”

A successful list returns Rapid7 JSON; an empty list may be valid. **“Credentials are not configured”** confirms a tool call reached the server, but is not a successful Rapid7 request. HTTP `401` usually means the key is invalid or for the wrong region; `403` usually means insufficient permissions.

Only enable writes when needed. An unchecked setup form disables execution/cancellation. If enabled, each mutation also requires `confirm=true` after you approve the specific action. Cancellation does not undo actions already performed.

## Desktop apps and WSL

An installed desktop app and a CLI with a similar name do not necessarily share configuration or runtime. The MCP executable must be reachable **from the machine/environment running the app's MCP client**.

### Claude Desktop versus Claude Code

Claude Desktop uses its own local-server config, separate from Claude Code's `.mcp.json`:

1. Open Claude Desktop's **Settings → Developer → Edit Config**.
2. Merge this entry into `claude_desktop_config.json`, substituting your absolute executable path.
3. Fully quit and reopen Claude Desktop, then check its local MCP server status.

```json
{
  "mcpServers": {
    "rapid7-insightconnect": {
      "command": "/absolute/path/rapid7-insightconnect-mcp/.venv/bin/rapid7-insightconnect-mcp",
      "args": []
    }
  }
}
```

That path works only when the app can execute it directly—for a Windows app with a WSL installation, use the wrapper below. A hosted connector URL is not a replacement for this stdio configuration. See the [official local-server guide](https://modelcontextprotocol.io/docs/develop/connect-local-servers).

### Codex desktop interface

1. Add the server using the [Codex CLI command](#codex) on the **same host/user profile** used by the desktop app, or add the entry below to that host's Codex configuration.
2. Open the app's MCP settings, check that the server is enabled, and restart its connection or open a new session.
3. Request `setup`, then try the read-only workflow list.

```toml
[mcp_servers.rapid7-insightconnect]
command = "/absolute/path/rapid7-insightconnect-mcp/.venv/bin/rapid7-insightconnect-mcp"
args = []
```

The standard user file is `~/.codex/config.toml`. Menu names vary with app version/branding: the current [OpenAI MCP guide](https://developers.openai.com/codex/mcp/) describes **Settings → MCP servers → Add server**, then **STDIO**, for its documented desktop interface. Do not assume every Codex-branded build has that exact menu. A WSL CLI registration does not automatically configure a native Windows app.

### Hermes Desktop

1. Complete [Hermes registration](#hermes-agent) for the profile/backend the desktop app will use.
2. Launch the desktop interface from your project:

   ```sh
   hermes desktop --cwd "$PWD"
   ```

3. Open a new chat and ask for the Rapid7 `setup` tool. If it is absent, check the desktop's active backend/profile rather than adding secrets to chat.

`gui` is an alias for `desktop` in the installed CLI. This launcher may install/build desktop dependencies; desktop availability depends on your Hermes build/platform. See [Hermes installation](https://hermes-agent.nousresearch.com/docs/getting-started/installation).

### OpenCode Desktop

1. Open the project containing the [OpenCode `opencode.json` entry](#opencode) in the desktop app.
2. Reconnect/restart the backend and check whether `rapid7-insightconnect` appears among its MCP tools.
3. Request `setup`, then the read-only workflow list.

If the server is missing, check the config location used by that desktop backend in the [OpenCode configuration guide](https://opencode.ai/docs/config/). Do not assume a separate or remote backend reads your WSL project's configuration or can execute its paths.

If URL elicitation is unavailable in a desktop app, use the [environment fallback](#if-the-harness-cannot-open-setup).

### Windows desktop app with the server in WSL

A native Windows app cannot directly execute `/…/.venv/bin/rapid7-insightconnect-mcp`. If it supports an arbitrary stdio command, launch through `wsl.exe` instead:

```json
{
  "mcpServers": {
    "rapid7-insightconnect": {
      "command": "wsl.exe",
      "args": [
        "--distribution", "<DISTRO_NAME>",
        "--exec", "/absolute/linux/path/rapid7-insightconnect-mcp/.venv/bin/rapid7-insightconnect-mcp"
      ]
    }
  }
}
```

Find the distribution name with `wsl --list --quiet` in PowerShell. Use the Linux executable path from your WSL install. The wrapper is a command/args pattern; adapt it to the harness's schema (OpenCode uses a single command array).

Credentials belong to the WSL user running that command. Browser setup also depends on Windows being able to reach WSL's localhost port. Never expose the form on a public address to work around connectivity.

## Troubleshooting

| What you see | What to check |
| --- | --- |
| `command not found` / server cannot start | Use the absolute launcher path. Retry your installation route's `--help` command (`MCP_BIN` or `UVX_BIN --from …`). For desktop + WSL, check the wrapper above. |
| Server absent from the harness | Check its MCP list/status, enable/trust the project entry, then restart or open a new session. |
| Tool call denied | Approve that tool/server in your harness. Do not disable all permission checks just to test a read operation. |
| Credentials not configured | Run the in-harness `setup` tool, or configure environment injection. CLI `setup` alone does not save. |
| Saved settings seem ignored | Remove old `R7_API_KEY`/`R7_REGION` overrides or placeholders from the harness entry. A complete environment pair takes precedence over the saved file. |
| Setup times out or returns terminal instructions | Your harness may not support URL elicitation or may time out sooner than the form. Use the environment fallback. |
| HTTP `401` / `403` | Check key, region, and Rapid7 API permissions. Setup's “Ready” does not verify them. |
| Writes are disabled | Re-run browser setup with the write checkbox enabled, or supply the complete environment configuration with `R7_ALLOW_WRITES=true`. |
| Hermes says no inference provider | Configure its model/provider with `hermes model`; MCP and model credentials are separate. |
| OpenCode model not found | Select a configured model from `opencode models`; model IDs include the provider prefix. |

### Environment reference

| Variable | Purpose |
| --- | --- |
| `R7_API_KEY` + `R7_REGION` | Supply **both** to select environment-based credentials instead of the saved file. |
| `R7_ALLOW_WRITES` | Exact `true` or `false`, default `false`, in environment-based mode. Alone it does not override a saved write policy. |
| `R7_SETUP_TIMEOUT` | Local form wait in seconds, default `300`. Use a positive finite value. The harness may impose a shorter timeout. |
| `XDG_CONFIG_HOME` | Changes the saved credential location; keep consistent across processes intended to share credentials. |

No `.env` file is automatically loaded. Ordinary missing/invalid settings let the server start unconfigured so `setup` stays available.

## Available tools

| Tool | What it does |
| --- | --- |
| `setup` | Opens local browser onboarding when supported by the client. |
| `list_workflows` / `get_workflow` | Find workflows; read a definition by UUID. |
| `execute_workflow` | Execute an active API-triggered workflow without an input payload; write opt-in required. |
| `list_jobs` / `get_job` | Read jobs, filter by workflow or documented terminal status, inspect by UUID. |
| `cancel_job` | Request cancellation; write opt-in required. |
| `list_global_artifacts` / `get_global_artifact` | Find artifacts or read metadata. |
| `list_artifact_entries` | Read an artifact's default entity page. |
| `export_snippet` | Export a known snippet UUID; published version by default. |

List limits are 1–30 with `offset` pagination where documented. Tool inputs include UUID validation, enums, integer bounds, and strict confirmation booleans. Outputs preserve upstream JSON shapes.

Resources: `insightconnect://server/config` (no key), `insightconnect://workflows/{workflow_id}`, `insightconnect://jobs/{job_id}`, and `insightconnect://artifacts/{artifact_id}`.

### Current limits and safety

- No workflow input payload support, complete artifact-entity pagination, or snippet listing: the upstream contracts do not document what is needed. Regions `me1`/`aps2` are not supported yet. See [API contracts and limits](docs/api-contracts.md).
- No generic REST proxy, arbitrary trigger URL, import/overwrite, artifact deletion, or bulk mutation tools.
- Fixed regional HTTPS hosts, no redirects or environment proxies, no automatic retries, bounded HTTP deadlines, and a 2 MiB request/response limit. Unexpected compressed responses are rejected.
- Treat API content as untrusted data, not instructions. Tool results can contain sensitive workflow/job/artifact data and may be sent to your model provider or retained by the harness.
- The saved key is plaintext with Unix owner-only permissions—not encrypted storage. Setup is not proof of human authorization; keep harness approvals enabled and use least-privilege Rapid7 keys.
- A timed-out execution may already have started. Inspect jobs before considering another attempt; never assume cancellation rolls back external actions.

### Compatibility

The test suite drives the server with the official MCP Python SDK client over a real stdio subprocess, covering tool discovery, resources, and the URL-elicitation setup flow. Interactive harnesses and desktop apps differ in URL-elicitation support and tool timeouts; when setup cannot open a page, use the [environment fallback](#if-the-harness-cannot-open-setup).

## Development

```sh
uv sync --frozen
uv run ruff format --check src tests
uv run ruff check src tests
uv run mypy
uv run pytest -q
uv build
```

Ruff enforces cyclomatic complexity ≤10. The test suite runs fully offline: Rapid7 HTTP traffic is mocked, and setup-flow tests use loopback-only forms and temporary credential directories.

Dependency advisory check (contacts the public advisory service):

```sh
uv export --frozen --no-dev --no-emit-project --format requirements-txt -o .audit-requirements.txt
uv run pip-audit --no-deps --disable-pip -r .audit-requirements.txt
```

Official Rapid7 sources: [REST API overview](https://docs.rapid7.com/insightconnect/insightconnect-rest-api/) · [OpenAPI](https://docs.rapid7.com/_api/insightconnect-api-v1.yaml).
