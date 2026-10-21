"""Authenticated access to the IASO API.

Every pipeline reads IASO the same way: it opens a session from an OpenHEXA connection, then walks
the pages of an endpoint. Both steps used to be copied into each pipeline (``get_iaso_client`` in
26 of them, ``get_paginated`` in 6) and the copies drifted apart.

The connection is not looked up here. The pipeline declares it as a parameter, so the person who
runs it picks the IASO instance in the OpenHEXA form (production, staging...) and the pipeline
receives the connection object::

    from openhexa.sdk import CustomConnection, parameter, pipeline
    from polio_utils import get_iaso_client


    @pipeline("my_pipeline")
    @parameter(
        "iaso_connection",
        name="IASO connection",
        type=CustomConnection,
        default="iaso_polio",
    )
    def my_pipeline(iaso_connection: CustomConnection) -> None:
        base_url, headers = get_iaso_client(iaso_connection)

The functions that talk to the network take an optional ``session``. In a pipeline it is left out
and ``requests`` is used directly; in a test it is a small fake that returns fixed answers, so the
tests need no server and no credential.

Temporary by design: the official ``iaso-client`` library cannot read the ``/api/polio/...``
endpoints nor take a token in its released version (1.2.0). When a release offers
``IasoClient.raw(..., fetch_all=True)`` and a public way to set a token, this module becomes a thin
layer on top of it and ``get_access_token`` and the pagination loop of ``get_paginated`` are
removed. See the README, "Why not iaso-client (yet)".
"""

import requests
from openhexa.sdk import CustomConnection

#: Seconds to wait for one HTTP answer before giving up.
DEFAULT_TIMEOUT_SECONDS = 120

#: Largest page the IASO dashboard endpoints accept (``EtlPaginator.max_page_size`` in IASO).
MAX_PAGE_SIZE = 1000


class IasoApiError(RuntimeError):
    """Raised when IASO answers, but not with something the caller can use."""


def get_iaso_client(
    connection: CustomConnection,
    session: requests.Session | None = None,
    timeout: int = DEFAULT_TIMEOUT_SECONDS,
) -> tuple[str, dict[str, str]]:
    """Open an authenticated session against the IASO instance of an OpenHEXA connection.

    The way to authenticate is read from the connection itself:

    * a connection with a ``token`` field (e.g. ``iaso_polio``, production) sends that token;
    * a connection with ``username`` and ``password`` (e.g. ``polio-staging``) logs in on
      ``/api/token/`` to get one.

    The copies this replaces decided from the URL instead (a URL containing "poliogo" meant
    "use the token") and took the connection slug as a string.

    Args:
        connection: The IASO connection, as the pipeline receives it from a ``CustomConnection``
            parameter. It needs a ``url`` field, and either a ``token`` or a ``username`` and a
            ``password``.
        session: HTTP session to use for the login. Defaults to the ``requests`` module.
        timeout: Seconds to wait for the login answer.

    Returns:
        The base URL of the instance, without trailing slash, and the headers to send with every
        request.
    """
    base_url = connection.url.rstrip("/")
    token = get_access_token(
        base_url=base_url,
        token=getattr(connection, "token", None),
        username=getattr(connection, "username", None),
        password=getattr(connection, "password", None),
        session=session,
        timeout=timeout,
    )
    return base_url, auth_headers(token)


def get_access_token(
    base_url: str,
    token: str | None = None,
    username: str | None = None,
    password: str | None = None,
    session: requests.Session | None = None,
    timeout: int = DEFAULT_TIMEOUT_SECONDS,
) -> str:
    """Get a bearer token for an IASO instance.

    A token given directly is used as it is. Otherwise a token is asked on ``/api/token/`` with the
    username and password.

    The copies this replaces did not check the login answer: a refused login produced the header
    ``Bearer None`` and every later call failed with a confusing 401. Here the login fails at once.

    Args:
        base_url: Base URL of the IASO instance, without trailing slash.
        token: Token stored on the connection, if any.
        username: Username of the connection, used when there is no token.
        password: Password of the connection, used when there is no token.
        session: HTTP session to use. Defaults to the ``requests`` module.
        timeout: Seconds to wait for the login answer.

    Returns:
        The token to send as ``Authorization: Bearer <token>``.

    Raises:
        ValueError: If there is no token and no username and password either.
        requests.HTTPError: If the login request is refused.
        IasoApiError: If the login answer carries no access token.
    """
    if token:
        return token
    if not (username and password):
        raise ValueError(f"The connection to {base_url} has neither a token nor a username and a password.")

    http = session or requests
    response = http.post(
        f"{base_url}/api/token/",
        json={"username": username, "password": password},
        timeout=timeout,
    )
    response.raise_for_status()
    access = response.json().get("access")
    if not access:
        raise IasoApiError(f"IASO at {base_url} returned no access token for this username.")
    return access


def auth_headers(token: str) -> dict[str, str]:
    """Build the headers that authenticate a request to IASO.

    Args:
        token: A bearer token.

    Returns:
        The ``Authorization`` header.
    """
    return {"Authorization": f"Bearer {token}"}


def get_paginated(
    url: str,
    headers: dict[str, str],
    results_key: str = "results",
    params: dict[str, str] | None = None,
    page_size: int = MAX_PAGE_SIZE,
    session: requests.Session | None = None,
    timeout: int = DEFAULT_TIMEOUT_SECONDS,
) -> list[dict]:
    """Read every page of a paginated IASO endpoint.

    Pages are requested one after the other with the ``page`` and ``limit`` query parameters.
    Reading stops when IASO says there is no next page or, for an endpoint that does not say, when
    a page comes back shorter than ``page_size``.

    Unlike the copies it replaces, an HTTP error is raised instead of ending the loop: otherwise a
    partial result would be published as if it were complete.

    Args:
        url: Full URL of the endpoint, without query string.
        headers: Authentication headers, as returned by :func:`get_iaso_client`.
        results_key: Key of the page payload that holds the records, for example ``"campaigns"``
            for ``/api/polio/dashboards/campaigns/``.
        params: Extra query parameters, sent on every page. Booleans must be given as the strings
            ``"true"`` / ``"false"``, as IASO expects them.
        page_size: Number of records asked per page.
        session: HTTP session to use. Defaults to the ``requests`` module.
        timeout: Seconds to wait for each page.

    Returns:
        The records of every page, in the order IASO returned them.

    Raises:
        requests.HTTPError: If any page is answered with an HTTP error.
        IasoApiError: If a page does not hold its records under ``results_key``.
    """
    http = session or requests
    records: list[dict] = []
    page = 1
    while True:
        query = {**(params or {}), "page": page, "limit": page_size}
        response = http.get(url, headers=headers, params=query, timeout=timeout)
        response.raise_for_status()
        payload = response.json()
        page_records = extract_page_records(payload, results_key)
        records.extend(page_records)
        if not has_next_page(payload, len(page_records), page_size):
            return records
        page += 1


def extract_page_records(payload: dict | list, results_key: str) -> list[dict]:
    """Take the records out of one page of an IASO answer.

    Args:
        payload: The decoded JSON of one page.
        results_key: Key that holds the records when the page is an object.

    Returns:
        The records of the page. A page that is a plain list is returned as it is.

    Raises:
        IasoApiError: If the page is an object without a list under ``results_key``.
    """
    if isinstance(payload, list):
        return payload
    records = payload.get(results_key) if isinstance(payload, dict) else None
    if not isinstance(records, list):
        keys = sorted(payload) if isinstance(payload, dict) else type(payload).__name__
        raise IasoApiError(f"Expected a list under '{results_key}' in the IASO answer, got: {keys}")
    return records


def has_next_page(payload: dict | list, nb_records: int, page_size: int) -> bool:
    """Decide whether another page must be requested.

    Args:
        payload: The decoded JSON of the page just read.
        nb_records: How many records that page held.
        page_size: How many records were asked for.

    Returns:
        False when the page was empty, when it was a plain list (an endpoint without pagination
        answers everything at once, and asking again would repeat it), or when IASO says there is
        no next page. Otherwise True when the page was full.
    """
    if nb_records == 0 or isinstance(payload, list):
        return False
    if "has_next" in payload:
        return bool(payload["has_next"])
    return nb_records >= page_size
