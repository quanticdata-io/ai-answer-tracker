## What and why

## Checklist

- [ ] `ruff check .`, `ruff format --check .`, `mypy` and `pytest` pass
- [ ] Tests do not call the QuanticData API or the network
- [ ] New fixtures are synthetic or sanitised (`.example` domains, no keys, no personal data)
- [ ] CHANGELOG entry under "Unreleased" for user-facing changes
