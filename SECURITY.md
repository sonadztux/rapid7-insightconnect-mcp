# Security Policy

## Reporting a vulnerability

Please do **not** open a public issue containing exploit details, API keys, credentials, tokens, private Rapid7 data, or other sensitive information.

Use GitHub's **Security** tab and **Report a vulnerability** if private vulnerability reporting is available for this repository.

If private vulnerability reporting is not available, open a minimal public issue asking for a private reporting channel. Include only enough information to identify the affected component. Do not include reproduction secrets, customer data, or working exploit details in the public issue.

When reporting privately, please include:

- the affected version or commit;
- the impacted component or tool;
- a clear description of the security impact;
- minimal reproduction steps;
- whether credentials, local files, or Rapid7 mutations are involved;
- any suggested mitigation, if known.

## Sensitive data

This project handles Rapid7 API credentials and can expose Rapid7 response data to an MCP client and its configured AI provider.

When testing or reporting issues:

- use a least-privilege test API key;
- revoke any key that may have been disclosed;
- redact workflow, job, artifact, and connection data unless it is required to reproduce the issue;
- never commit real credentials or tokenized local setup URLs.

## Security-sensitive areas

Changes in these areas deserve extra review and tests:

- credential loading and precedence;
- filesystem ownership, permissions, and symlink handling;
- the loopback setup form and one-time token lifecycle;
- HTTP destination validation, redirects, timeouts, retries, and body limits;
- response redaction;
- write enablement and `confirm=true` enforcement.

## Supported versions

Until the project has tagged releases, security fixes are applied to the latest commit on the default branch.
