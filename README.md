# Rapid7 InsightConnect MCP

Use Rapid7 InsightConnect (Automation) from your AI assistant. Find workflows, check jobs, read global artifacts, export snippets, and, if you allow it, run workflows or cancel jobs.

- **Runs on your machine.** Your MCP client starts the server over stdio. There is no hosted service.
- **Read-only by default.** Workflow execution and job cancellation stay off until you turn them on.
- **Your API key stays out of the chat.** You enter it in a local browser page, not in the conversation.

**Get started:** [Install](#1-install) → [Add to your MCP client](#2-add-the-server-to-your-mcp-client) → [Connect Rapid7](#3-connect-your-rapid7-account) → [Try it](#4-try-it)

More: [Desktop apps and WSL](#desktop-apps-and-wsl) · [Troubleshooting](#troubleshooting) · [Reference](#reference) · [Development](#development)

## Requirements

- **Python 3.11+**, **Git**, and **[uv](https://docs.astral.sh/uv/getting-started/installation/)**
- An MCP client such as Claude Code, Codex, Hermes Agent, OpenCode, or Claude Desktop, with its AI model already set up. Your Rapid7 key does not sign you in to your AI provider.
- A Rapid7 API key and your organization's region. Give the key only the permissions you need. See [Rapid7 API keys](https://docs.rapid7.com/insight/api-overview/).

You don't need the API key to install. Until the server has credentials, it offers a `setup` tool and makes no Rapid7 requests.

> The commands below are for Bash or Zsh on Linux, macOS, or WSL. Type secrets into your own terminal, never into an assistant's chat or tool. For Windows desktop apps, see [Windows app with the server in WSL](#windows-app-with-the-server-in-wsl).

## 1. Install

```sh
git clone https://github.com/sonadztux/rapid7-insightconnect-mcp.git
cd rapid7-insightconnect-mcp
uv sync --frozen --no-dev

# Save the launcher path for the next step (keep this terminal open).
MCP_BIN="$(pwd)/.venv/bin/rapid7-insightconnect-mcp"
"$MCP_BIN" --help
```

You should see usage text that mentions `setup`. You don't start the server yourself: your MCP client launches it when needed.

Keep the folder where it is. Your MCP client runs the launcher from this path, so if you move the folder, register the server again.

<details>
<summary><strong>Alternative: run straight from Git with <code>uvx</code> (no clone)</strong></summary>

`uvx` can download, cache, and launch the server for your MCP client. Pin a specific commit:

```sh
MCP_SOURCE="git+https://github.com/sonadztux/rapid7-insightconnect-mcp.git@<COMMIT_SHA>"
UVX_BIN="$(command -v uvx)"
"$UVX_BIN" --from "$MCP_SOURCE" rapid7-insightconnect-mcp --help   # downloads and checks it
```

Then register it with **one** of these, instead of the commands in step 2:

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

For OpenCode or a desktop app, use the absolute `uvx` path as the command, with `--from <MCP_SOURCE> rapid7-insightconnect-mcp` as its arguments.

Notes:

- This route needs network access the first time. It does not use the project's `uv.lock`, so dependency versions can differ from a clone install.
- The repository is private, so you also need Git access to it.
- The package is not on PyPI. A plain `uvx rapid7-insightconnect-mcp` will not work.

Then go to [step 3](#3-connect-your-rapid7-account).

</details>

## 2. Add the server to your MCP client

These commands use `MCP_BIN` from step 1. In a new terminal, `cd` into the project folder and set it again:

```sh
MCP_BIN="$(pwd)/.venv/bin/rapid7-insightconnect-mcp"
```

Registering the server needs only the launcher path. **Never put your Rapid7 key in these commands.**

### Claude Code

Run this in the project where you want to use the server:

```sh
claude mcp add --transport stdio --scope project rapid7-insightconnect -- "$MCP_BIN"
claude mcp get rapid7-insightconnect
claude
```

- `--scope project` saves the entry in that project's `.mcp.json`. The file contains your launcher path, which is different on every machine, so check it before sharing.
- To use the server in all your projects, use `--scope user` instead.
- In Claude Code, type `/mcp` to check the connection. Approve the server if you're asked to.

See the [Claude Code MCP docs](https://code.claude.com/docs/en/mcp).

### Codex

```sh
codex mcp add rapid7-insightconnect -- "$MCP_BIN"
codex mcp list
codex
```

In Codex, type `/mcp` to check the server. You don't need `codex mcp login`; this server uses a Rapid7 API key, not OAuth.

See the [Codex MCP docs](https://developers.openai.com/codex/mcp/).

### Hermes Agent

```sh
hermes mcp add rapid7-insightconnect --command "$MCP_BIN"
hermes mcp list
hermes
```

When Hermes asks `Enable all 11 tools? [Y/n/select]`, choose `Y`, or pick the tools you want. Start a new Hermes session afterwards. If Hermes says **"No inference provider configured"**, run `hermes model` first.

See the [Hermes docs](https://hermes-agent.nousresearch.com/docs/).

### OpenCode

Add this `mcp` entry to `opencode.json` in your project. Merge it into the file if it already exists. Replace the path with the output of `echo "$MCP_BIN"`:

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

```sh
opencode mcp list
opencode
```

OpenCode may show tool names with a prefix, such as `rapid7-insightconnect_list_workflows`. To use the server in all your projects, add the entry to OpenCode's global `opencode.json` instead. See [OpenCode MCP servers](https://opencode.ai/docs/mcp-servers/).

## 3. Connect your Rapid7 account

### Recommended: the setup tool

1. Ask your assistant: **"Run the setup tool from rapid7-insightconnect."**
2. Approve opening the local setup page when your client asks.
3. Pick your region: `us`, `us2`, `us3`, `eu`, `ca`, `au`, or `ap`.
4. Paste your API key into the page. For a first test, leave **Allow workflow execution and cancellation** unchecked.
5. Click **Save**, go back to your assistant, and wait for **"Ready. Region …"**.

The tools work right away. If other copies of the server are already running in other clients, restart them to pick up the new settings.

**"Ready" means the settings were saved, not that Rapid7 accepted the key.** Your first request is the real check.

About the setup page:

- It runs at `http://127.0.0.1` on your machine and closes after you save. Its address includes a one-time token, so don't share it.
- Your key goes from the page straight to the server and never passes through the chat or a tool call.
- Keep the assistant's setup request open while you fill in the page. Some clients time out sooner than the page's 5-minute limit.
- The 5-minute limit covers approving the page and filling it in, not each step separately. If it runs out, call setup again.

The key is saved as plain text, readable only by your user account:

```text
~/.config/rapid7-insightconnect-mcp/credentials.json
```

If `XDG_CONFIG_HOME` is an absolute path, the file goes to `$XDG_CONFIG_HOME/rapid7-insightconnect-mcp/credentials.json` instead; relative values are ignored. Successful setup saves the folder with mode `0700` and the file with mode `0600`. MCP clients running as your user with the same configuration path share this saved account.

Saving and loading require a symlink-free directory path. Every ancestor must be owned by your user or root and must not be group- or world-writable; the credential folder itself must belong to your user. Setup refuses unsafe directories without changing their permissions. Loading also refuses a symlinked credential file, a file owned by another user, or a file accessible to other accounts, because it controls execution permission too. Saving atomically replaces the final file, including a final-file symlink, without following it.

Fix ownership and permissions only on directories you control, or choose a trusted absolute `XDG_CONFIG_HOME` path before rerunning setup. Setup cannot repair unsafe ancestry. These filesystem checks require POSIX descriptor-relative operations.

### Alternative: environment variables

Use this if your client can't open the setup page. Set the variables in your own terminal, then start your client from that same terminal:

```sh
read -r -s -p 'Rapid7 API key: ' R7_API_KEY; printf '\n'   # input is hidden
export R7_API_KEY
export R7_REGION=eu            # your region
export R7_ALLOW_WRITES=false

claude    # or: codex, hermes, opencode
```

Desktop apps opened from an icon don't see these variables. Use the app's own settings for environment variables or secrets instead. Never write a real key into a file that is tracked in Git.

For a guided walkthrough, run `"$MCP_BIN" setup`. It asks for your region and key, can test the key with one read-only request, and prints a config example. **It doesn't save anything.** You still need the environment variables above or your client's secret settings.

## 4. Try it

Start with something read-only:

> Use rapid7-insightconnect to list at most 5 workflows. Don't run anything.

More ideas:

- "Show the latest 5 InsightConnect jobs."
- "List global artifacts whose name contains `blocklist`."
- "Read workflow `<workflow UUID>` and explain its trigger."
- "Export the published version of snippet `<snippet UUID>`."

Reading the results:

- A list of Rapid7 JSON means everything works. An empty list can be normal.
- **"Credentials are not configured"** means the server is reachable but setup isn't finished yet.
- **HTTP 401** usually means a wrong key or region. **HTTP 403** usually means the key lacks permission.

To run workflows or cancel jobs, run setup again and tick the checkbox. Even then, the assistant has to pass `confirm=true` for each action, and it should ask you first. Cancelling a job doesn't undo actions that already ran.

## Desktop apps and WSL

A desktop app and a command-line tool with a similar name don't always share settings. The desktop app must be able to run the server's launcher on the machine where the app runs.

### Claude Desktop

Claude Desktop keeps its own config, separate from Claude Code:

1. Open **Settings → Developer → Edit Config**.
2. Add this entry to `claude_desktop_config.json`, using your own absolute path.
3. Quit Claude Desktop completely and reopen it.

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

On Windows with the server installed in WSL, use the [WSL setup](#windows-app-with-the-server-in-wsl) instead.

### Codex desktop app

Register the server with the [Codex command](#codex) under the same user account the app uses, or add this to `~/.codex/config.toml`:

```toml
[mcp_servers.rapid7-insightconnect]
command = "/absolute/path/to/rapid7-insightconnect-mcp/.venv/bin/rapid7-insightconnect-mcp"
args = []
```

Then check that the server is enabled in the app's MCP settings, and open a new session. A registration made inside WSL doesn't configure a native Windows app.

### Hermes Desktop

Complete the [Hermes setup](#hermes-agent) first, then start the desktop app from your project folder:

```sh
hermes desktop --cwd "$PWD"
```

If the `setup` tool doesn't appear, check which profile the desktop app uses.

### OpenCode Desktop

Open the project that contains your [`opencode.json` entry](#opencode), then restart the backend and look for `rapid7-insightconnect` among the MCP tools. See the [OpenCode config guide](https://opencode.ai/docs/config/) if it's missing.

### Windows app with the server in WSL

A Windows app can't run a Linux path directly. If the app accepts any command, launch the server through `wsl.exe`:

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

Run `wsl --list --quiet` in PowerShell to find the distribution name. The saved credentials belong to your WSL user. The setup page also needs Windows to reach WSL's `localhost`. Don't expose the page on a public address to work around this.

If your desktop app can't open the setup page, use the [environment variables](#alternative-environment-variables) instead.

## Troubleshooting

| Problem | What to try |
| --- | --- |
| `command not found`, or the server won't start | Use the absolute launcher path. Run `"$MCP_BIN" --help` to check the install. On Windows with WSL, use the `wsl.exe` wrapper. |
| Server doesn't show up in the client | Check the client's MCP list, approve or enable the server, then restart or open a new session. |
| Tool call denied | Approve the tool in your client. Don't turn off all permission checks. |
| "Credentials are not configured" | Run the `setup` tool, or set the environment variables. `rapid7-insightconnect-mcp setup` in a terminal doesn't save anything. |
| Saved settings are ignored | Remove old `R7_API_KEY` / `R7_REGION` values from the client's server entry. When both are set, they override the saved file. |
| Setup times out, or says the client can't open the page | Your client may not support opening the page, or may time out first. Use the environment variables. |
| HTTP 401 or 403 | Check the key, the region, and the key's Rapid7 permissions. |
| "Writes are disabled" | Run setup again with the checkbox ticked, or set `R7_ALLOW_WRITES=true` together with `R7_API_KEY` and `R7_REGION`. |
| Hermes: "No inference provider configured" | Run `hermes model`. Your AI model and Rapid7 credentials are set up separately. |

## Reference

### Tools

| Tool | What it does |
| --- | --- |
| `setup` | Opens the local setup page to connect your Rapid7 account. |
| `list_workflows` / `get_workflow` | Find workflows, or read one by UUID. |
| `execute_workflow` | Runs an active, API-triggered workflow without input. Needs writes enabled and `confirm=true`. |
| `list_jobs` / `get_job` | List jobs (filter by workflow or by `succeeded`/`failed`), or read one by UUID. |
| `cancel_job` | Asks Rapid7 to cancel a job. Needs writes enabled and `confirm=true`. |
| `list_global_artifacts` / `get_global_artifact` | Find global artifacts, or read one's details. |
| `list_artifact_entries` | Read the first page of an artifact's entries. |
| `export_snippet` | Export a snippet by UUID (published version by default). |

List tools return up to 30 items per call. Use `offset` to get the next page.

Resources: `insightconnect://server/config` (current settings, never the key), `insightconnect://workflows/{workflow_id}`, `insightconnect://jobs/{job_id}`, `insightconnect://artifacts/{artifact_id}`.

### Environment variables

| Variable | Purpose |
| --- | --- |
| `R7_API_KEY` and `R7_REGION` | Set **both** to use them instead of the saved credentials. |
| `R7_ALLOW_WRITES` | `true` or `false` (default). Only applies when `R7_API_KEY` and `R7_REGION` are also set. |
| `R7_SETUP_TIMEOUT` | How long the setup page waits, in seconds. Default `300`. |
| `XDG_CONFIG_HOME` | Changes where credentials are saved. |

`.env` files are not loaded. If settings are missing or invalid, the server still starts so that `setup` is available.

### Safety and limits

- Rapid7 data is treated as untrusted content, not instructions. Tool results can contain sensitive data, and your MCP client may send them to your AI provider.
- Your key is masked wherever it appears in a response, and so are fields whose names look like credentials (`password`, `secret`, `apiKey`, `Authorization`, and similar). Treat that as a safety net, not a guarantee: a secret kept in an ordinary field, such as a step's notes, still reaches your assistant.
- Requests only go to the fixed Rapid7 host for your region, over HTTPS. The server doesn't follow redirects, doesn't use proxy settings, doesn't retry automatically, and caps requests and responses at 2 MiB.
- If a workflow run times out, it may have started anyway. Check the jobs list before trying again.
- The saved key is plain text protected by file permissions, not encryption. Keep your client's tool approvals on and use a least-privilege key.
- Not supported yet: workflow input payloads, reading all pages of artifact entries, listing snippets, and the `me1` and `aps2` regions. Rapid7's API documentation doesn't describe the details needed for these.
- Import, overwrite, artifact deletion, bulk changes, and raw REST access are left out on purpose.

## Development

```sh
uv sync --frozen
uv run ruff format --check .
uv run ruff check .
uv run mypy
uv run pytest -q
uv build
```

The tests run offline: Rapid7 HTTP calls are mocked, and setup tests use temporary folders for credentials.

To check dependencies for known vulnerabilities (this contacts the public advisory database):

```sh
uv export --frozen --no-dev --no-emit-project --format requirements-txt -o .audit-requirements.txt
uv run pip-audit --no-deps --disable-pip -r .audit-requirements.txt
```

### Project layout

```text
insightconnect_mcp/
  cli.py            command line: serve over stdio, or run the setup wizard
  server.py         MCP tools and resources
  client.py         HTTP client for the Rapid7 API
  config.py         settings and region list
  runtime.py        holds the active credentials, so setup takes effect without a restart
  storage.py        reads and writes the saved credentials file
  setup_form.py     one-time local web page used by the setup tool
  setup_wizard.py   terminal walkthrough for `rapid7-insightconnect-mcp setup`
tests/
  data/insightconnect-api-v1.yaml   copy of Rapid7's OpenAPI spec, used to check routes
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

Requests authenticate with the `X-Api-Key` header against `https://{region}.api.insight.rapid7.com`. Results are returned exactly as Rapid7 sends them.

Rapid7 sources: [REST API overview](https://docs.rapid7.com/insightconnect/insightconnect-rest-api/) · [OpenAPI spec](https://docs.rapid7.com/_api/insightconnect-api-v1.yaml)
