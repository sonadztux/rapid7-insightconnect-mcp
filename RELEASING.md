# Releasing

This project uses GitHub Releases and PyPI trusted publishing. No PyPI API token should be stored in repository secrets.

## One-time PyPI setup

Create the `rapid7-insightconnect-mcp` project on PyPI or configure a pending trusted publisher with:

- **Owner:** `sonadztux`
- **Repository:** `rapid7-insightconnect-mcp`
- **Workflow:** `publish.yml`
- **Environment:** `pypi`

In GitHub, create the `pypi` environment. Add required reviewers if you want a human approval gate before a release can publish.

The publish workflow receives only `contents: read` and `id-token: write`. It does not use a PyPI password or API token.

## Prepare a release

1. Update the version in `pyproject.toml`.
2. Run `uv lock` so the editable root package version in `uv.lock` matches.
3. Run the full validation suite:

   ```sh
   uv sync --frozen
   uv run ruff format --check .
   uv run ruff check .
   uv run mypy
   uv run pytest -q
   uv run pip-audit
   uv build
   ```

4. Merge the release changes to `main`.
5. Create a GitHub Release with tag `v<version>`, for example `v0.2.0`.

The publish workflow refuses to publish if the GitHub release tag does not exactly match `v` plus the version in `pyproject.toml`.

## Verify the published package

After the PyPI job succeeds, test the public distribution rather than the checkout:

```sh
uvx --from rapid7-insightconnect-mcp==0.2.0 rapid7-insightconnect-mcp --version
uvx --from rapid7-insightconnect-mcp==0.2.0 rapid7-insightconnect-mcp doctor
```

For future releases, replace `0.2.0` with the released version.
