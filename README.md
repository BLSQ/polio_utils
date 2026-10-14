# polio_utils

Shared helpers for the polio pipelines running on OpenHEXA ("https://poliogo-pipeline.afro.who.int/") (workspace `polio-8e2250` for production, workspace `polio-staging-test` for testing).

Code that is not about one pipeline in particular lives here, so it is written, tested and fixed
once instead of being copied into every pipeline. Pipeline-specific business logic does not
belong here: it stays in the pipeline (`polio_pipelines`). Table schemas live in
`polio_contracts`.

Part of the Polio Refurbishing project, with
[polio_contracts](https://github.com/BLSQ/polio_contracts) and
[polio_pipelines](https://github.com/BLSQ/polio_pipelines).

## Modules

| Module | What it holds | Replaces |
| --- | --- | --- |
| `polio_utils.iaso` | `get_iaso_client`, `get_access_token`, `get_paginated` | `get_iaso_client` copied in 26 pipelines, `get_paginated` copied in 6 |

Import from the package, never from a module path. The IASO connection is a pipeline parameter,
so whoever runs the pipeline picks production or staging in the OpenHEXA form:

```python
from openhexa.sdk import CustomConnection, parameter, pipeline
from polio_utils import get_iaso_client, get_paginated


@pipeline("my_pipeline")
@parameter("iaso_connection", name="IASO connection", type=CustomConnection, default="iaso_polio")
def my_pipeline(iaso_connection: CustomConnection) -> None:
    base_url, headers = get_iaso_client(iaso_connection)
    campaigns = get_paginated(
        f"{base_url}/api/polio/dashboards/campaigns/",
        headers,
        results_key="campaigns",
    )
```

`get_iaso_client` reads how to authenticate from the connection: a `token` field (like
`iaso_polio`) is sent as it is; otherwise it logs in with `username` and `password` (like
`polio-staging`).

### Differences with the copies it replaces

- `get_iaso_client` takes the connection object the pipeline receives, not a slug, and decides
  from the connection's fields, not from the URL (the copies used the token when the URL contained
  "poliogo"). Same result for the connections of the workspace today.
- `get_paginated` **raises** on an HTTP error. The copies stopped reading and returned what they
  had, so a partial answer could be written to a table as if it were complete.
- `get_paginated` takes the query parameters as a dict and stops on IASO's `has_next` flag when
  the endpoint sends it.
- `get_access_token` raises when the login is refused or returns no token. The copies built the
  header `Bearer None` and failed later with a 401.


## Using it in a pipeline

Add the repository to the pipeline's `requirements.txt`; OpenHEXA installs it at run time:

```
pip install git+https://github.com/BLSQ/polio_utils.git
```

## Development

```bash
pip install -e .            # the package and its runtime dependencies (openhexa.sdk, requests)
pip install --group dev     # pytest and ruff (needs pip >= 25.1)
ruff check polio_utils tests
ruff format --check polio_utils tests
pytest tests -q
```

CI runs the same three checks on every push and pull request, and fails when any of them fails.

Every change is made on its own branch and merged through a pull request.
