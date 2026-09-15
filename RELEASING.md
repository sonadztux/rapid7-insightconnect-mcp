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
   uv sync --frozen --extra dev
   uv run ruff format --check .
   uv run ruff check .
   uv run mypy
   uv run pytest -q
   uv run pip-audit
   uv build
   ```

4. Merge the release changes to `main`.
5. Wait for the `checks` workflow on `main` to succeed. The release workflow then creates `v<version>` at that exact tested commit and dispatches trusted PyPI publishing on the tag. If that version already has a GitHub Release, the release workflow exits without publishing it again.

The publish workflow refuses to publish if the release tag does not exactly match `v` plus the version in `pyproject.toml`.

## Verify the published package

After the PyPI job succeeds, test the public distribution rather than the checkout:

```sh
uvx --from rapid7-insightconnect-mcp==0.2.1 rapid7-insightconnect-mcp --version
uvx --from rapid7-insightconnect-mcp==0.2.1 rapid7-insightconnect-mcp doctor
```

For future releases, replace `0.2.1` with the released version.
