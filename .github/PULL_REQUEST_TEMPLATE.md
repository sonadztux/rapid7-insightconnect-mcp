## Summary

<!-- What changes, and why? -->

## Validation

- [ ] `uv run ruff format --check .`
- [ ] `uv run ruff check .`
- [ ] `uv run mypy`
- [ ] `uv run pytest -q`
- [ ] `uv run pip-audit`
- [ ] `uv build`

## Security and user impact

- [ ] No real API keys, credentials, tokenized setup URLs, customer data, or private local paths are included.
- [ ] Credential, setup, HTTP, redaction, or write-gating changes fail closed and have regression coverage.
- [ ] User-visible behavior is reflected in README/docs where needed.
- [ ] Mutations remain disabled by default and require explicit per-call confirmation.

<!-- If an item does not apply, explain briefly. -->
