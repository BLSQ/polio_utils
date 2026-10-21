# CLAUDE.md

Context for AI coding agents and new colleagues working in this repository.

## What this repository is

`polio_utils` is the shared Python library of the polio pipelines that run on OpenHEXA
("https://poliogo-pipeline.afro.who.int/") (workspace `polio-8e2250` for production, workspace `polio-staging-test` for testing). It holds the code every pipeline needs and used to copy: IASO
authentication and paginated reads today; ONA downloads, facility matching, OpenHEXA client,
email/Slack alerts and file helpers as they are moved in.

It is one of three repositories of the Polio Refurbishing project:

| Repository | Holds |
| --- | --- |
| `polio_utils` (this one) | Shared helpers. No pipeline-specific business logic. |
| `polio_contracts` | Schema contracts of the tables the pipelines publish. |
| `polio_pipelines` | The pipelines, rebuilt one by one on top of the two libraries. |

The legacy pipelines live in `iaso-pipelines`. They are the reference for current behaviour and
are not modified by this project.

The conventions come from `polio_iaso_pipelines_example` (BLSQ); follow it when in doubt.

## Layout

| Path | What it holds |
| --- | --- |
| `polio_utils/` | The package. One module per area; public names re-exported in `__init__.py`. |
| `tests/` | One test file per module: `tests/test_<module>.py`. |
| `.github/workflows/ci.yml` | Ruff (check + format) and pytest on every pull request and every push to `main`. |
| `pyproject.toml` | Packaging, dependencies, and the single ruff and pytest configuration. |

## Domain vocabulary

- **IASO**: the platform holding campaigns, rounds, scopes and the org unit pyramid
  (country -> region -> district -> facility).
- **OpenHEXA connection**: where every credential lives. Never in code. The IASO connections of
  workspace `polio-8e2250` are CUSTOM connections: `iaso_polio` (production, `url` + `token`) and
  `polio-staging` (`url` + `username` + `password`).
- **Connection parameter**: pipelines declare the IASO connection as a parameter of type
  `CustomConnection` (default `iaso_polio`) and pass the object they receive to
  `get_iaso_client`. The library never looks a connection up by slug and never decides from the
  URL: a `token` field means "send it", otherwise it logs in with `username` and `password`.

## Relation with `iaso-client` (official IASO library)

`iaso-client` (PyPI, repo `BLSQ/iaso-client`) is the official Python client of IASO, maintained
by the IASO team and pre-installed in the OpenHEXA images. It is **not used yet**, on purpose:

- The released version (1.2.0) only covers org units, org unit types, forms, form versions and
  instances. The generic call for other endpoints, `IasoClient.raw(..., fetch_all=True)`, exists
  on its `main` branch but is not released, so it cannot read the `/api/polio/...` endpoints the
  pipelines need.
- It only logs in with a username and a password. Setting a token (what `iaso_polio` holds) is
  only possible through its internal `client.transport.set_bearer_token()`.

When a release has `raw()` and a public way to set a token, `polio_utils.iaso` becomes a thin
layer on top of it: `get_iaso_client` returns an `IasoClient` (token or login, decided from the
connection as today), `get_access_token` and the pagination loop of `get_paginated` are removed,
and only the extraction of `results_key` from each page stays here. Until then, do not add
another hand-written IASO client: extend `polio_utils.iaso`. For org units, forms or instances,
use `iaso-client` directly.

## Commands

```bash
pip install -e .                       # package + runtime dependencies
pip install --group dev                # pytest + ruff (pip >= 25.1)
ruff check polio_utils tests           # lint
ruff format polio_utils tests          # format
pytest tests -q                        # tests
pytest tests -q -k paginated           # one group of tests
```

Do not run anything against a real IASO, OpenHEXA workspace or database. Tests use fakes.

## Code style

- Python 3.11+, line length 120, ruff rules and ignores as in `pyproject.toml`.
- Docstrings: Google style. One-line summary, then `Args:`, `Returns:`, `Raises:` as needed.
- Type annotations on every function signature.
- `snake_case` functions and variables, `PascalCase` classes. Names say what the function
  answers.

## Conventions an agent must follow here

1. **No business logic.** A helper belongs here only if it is not about one pipeline. Campaign
   rules, scope rules, matching rules for one form stay in `polio_pipelines`.
2. **Network functions take an optional `session`.** It defaults to `requests`; tests pass a
   fake. Then the decision logic is testable without a server.
3. **Fail loudly.** Raise on HTTP errors and on answers that do not have the expected shape. A
   helper must never return partial data as if it were complete.
4. **Every public function has a test in the same change**, in `tests/test_<module>.py`, with
   small hand-written fixtures (a few records, only the fields the function reads).
5. **Re-export public names in `polio_utils/__init__.py`**; pipelines import from the package.
6. **Changing a public signature is a breaking change** for every pipeline that pins this
   library. Add a new argument with a default instead, and say so in the pull request.
7. **One branch per change**, merged through a pull request. Never commit to `main`.

## Out of scope for an agent

Do not push, open pull requests or change `.github/` unless asked. Never put a secret, a token or
real data in code, tests, fixtures or logs.
