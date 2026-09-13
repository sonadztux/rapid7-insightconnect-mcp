# API contracts and deliberate limits

Source of truth: https://docs.rapid7.com/_api/insightconnect-api-v1.yaml, retrieved 2026-09-13. Unmodified snapshot: `insightconnect-api-v1.yaml`; SHA-256 `3aca4619d44b65f9ac4d40caee4dc1dfc1fbb88693d55e3343d9f016f46411d7`. This is upstream reference data, not executable configuration.

Authentication (`X-Api-Key`) comes from https://docs.rapid7.com/insight/api-overview/ because the OpenAPI omits security schemes. Host: `https://{region}.api.insight.rapid7.com`. No user-configurable host.

| Tool | Official route |
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

Pagination uses `limit` and `offset`, **not** `page` and `size`. This server narrows upstream limit 0–30 to 1–30 and rejects negative offsets. Job filter `workflow_id` maps to `workflowId`; artifact `name` maps to `filterText`, with `sortBy=name` and `sortOrder`. Snippet `unpublished_version` maps to `unpublishedVersion`.

## Unresolved upstream documentation

- Workflow execution has no documented request body. API-trigger setup shows flat trigger JSON but does not verify that payload for this execution route. This release sends no body and supports no input-bearing workflow execution. Do not assume all workflows can run through this tool.
- Execution's HTTP 202 schema defines only optional `error`; no successful `jobId` contract. Return upstream JSON unchanged; do not manufacture an execution ID or promise job correlation.
- Artifact entities claim pagination but document no query parameters. This release reads only the upstream default page. Complete traversal of large artifacts is unsupported.
- Workflow versions are described as nullable but their schemas omit `nullable`.
- Job schemas have unusual nested `data.job.job` on get. Preserve it. Status schema says only `succeeded`/`failed` even though cancellation targets running/waiting jobs; do not validate response statuses against that enum.
- Artifact get uses lowercase `data.globalartifact`. Entity `data` is a string. Snippet export is an unwrapped JSON object.
- Some schema entries are null/invalid, including `GlobalArtifact.schema` and `WorkflowError.details`. Strict generated response models would reject potentially valid API responses. Inputs are strictly typed; outputs retain arbitrary upstream object fields and nested shapes.
- https://docs.rapid7.com/insight/product-apis/ lists `me1` and `aps2` beyond the seven OpenAPI regions. This initial server uses the OpenAPI's seven-region allowlist; those two regions are not supported yet.

## MVP boundary

Read-oriented workflow/job/artifact/snippet operations plus opt-in execution and cancellation. No import, overwrite, activation changes, artifact creation/deletion/entry mutation, arbitrary trigger URL, plugin operations, or complete REST parity. Additional list filters from the spec are omitted until needed.

Tests check all exposed route mappings, query mappings, representative envelope preservation, safety policy, and subprocess MCP discovery. They do not prove live-account behavior, undocumented API contracts, or individual harness UI integration.
