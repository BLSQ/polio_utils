"""Shared helpers for the polio pipelines running on OpenHEXA.

One module per area:

=========================== ============================================================
Module                      What it holds
=========================== ============================================================
:mod:`polio_utils.iaso`     Authentication to IASO and paginated reads of its endpoints
=========================== ============================================================

The public names are re-exported here, so a pipeline imports from the package and never from a
module path::

    from polio_utils import get_iaso_client, get_paginated

That indirection is what lets the modules be reorganised later without touching the pipelines.
"""

from polio_utils.iaso import (
    IasoApiError,
    auth_headers,
    get_access_token,
    get_iaso_client,
    get_paginated,
)

__all__ = [
    "IasoApiError",
    "auth_headers",
    "get_access_token",
    "get_iaso_client",
    "get_paginated",
]
