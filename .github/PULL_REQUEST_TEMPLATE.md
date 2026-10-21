Explain what problem this PR is solving.

Related JIRA tickets: POLIO-XXX

## Self proofreading checklist

- [ ] `ruff check` and `ruff format --check` pass
- [ ] Every new or changed function has a test, or the PR says why not
- [ ] Docstrings follow the Google style (Args / Returns / Raises)
- [ ] No pipeline-specific business logic was added to this library
- [ ] No secret, credential or real data in code, tests or fixtures
- [ ] CLAUDE.md and README.md are still true after this change

## Changes

Which files go together, and the reasoning behind the changes.

## Impact on the pipelines

Which pipelines will use this, and whether anything behaves differently from the copy it replaces.

## How to test

```bash
pip install -e .
pip install --group dev
ruff check polio_utils tests
ruff format --check polio_utils tests
pytest tests -q
```

## Notes

Known limits, trade-offs, follow-ups.
