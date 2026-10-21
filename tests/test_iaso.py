"""Tests of polio_utils.iaso.

The HTTP layer is replaced by :class:`FakeSession`, which answers from a fixed list and records
what was asked, and an OpenHEXA connection by a ``SimpleNamespace`` carrying the same fields, so
the tests need no server, no workspace and no credential.
"""

from types import SimpleNamespace

import pytest
import requests

from polio_utils.iaso import IasoApiError, auth_headers, get_access_token, get_iaso_client, get_paginated

URL = "https://iaso.example.org/api/polio/dashboards/campaigns/"
HEADERS = {"Authorization": "Bearer token"}


class FakeResponse:
    """Minimal stand-in for a ``requests`` response.

    Args:
        payload: The object returned by ``.json()``.
        status_code: The HTTP status to report.
    """

    def __init__(self, payload: object, status_code: int = 200) -> None:
        self._payload = payload
        self.status_code = status_code

    def json(self) -> object:
        """Return the payload.

        Returns:
            The object this response was built with.
        """
        return self._payload

    def raise_for_status(self) -> None:
        """Raise when the status is an error, like ``requests`` does.

        Raises:
            requests.HTTPError: If the status code is 400 or above.
        """
        if self.status_code >= 400:
            raise requests.HTTPError(f"HTTP {self.status_code}")


class FakeSession:
    """Answers each request with the next response of a fixed list, and records the calls.

    Args:
        responses: The responses to return, in order.
    """

    def __init__(self, responses: list[FakeResponse]) -> None:
        self.responses = list(responses)
        self.calls: list[dict] = []

    def get(self, url: str, **kwargs: object) -> FakeResponse:
        """Record a GET and return the next response.

        Args:
            url: The requested URL.
            **kwargs: The other arguments of the call.

        Returns:
            The next response of the list.
        """
        self.calls.append({"method": "GET", "url": url, **kwargs})
        return self.responses.pop(0)

    def post(self, url: str, **kwargs: object) -> FakeResponse:
        """Record a POST and return the next response.

        Args:
            url: The requested URL.
            **kwargs: The other arguments of the call.

        Returns:
            The next response of the list.
        """
        self.calls.append({"method": "POST", "url": url, **kwargs})
        return self.responses.pop(0)


# --- get_iaso_client / get_access_token -------------------------------------------------------


def test_a_connection_with_a_token_uses_it_without_logging_in() -> None:
    """A connection like iaso_polio (url + token) sends its token: no login request is made."""
    connection = SimpleNamespace(url="https://poliogo.example.org/", token="stored-token")
    session = FakeSession([])

    base_url, headers = get_iaso_client(connection, session=session)

    assert base_url == "https://poliogo.example.org"
    assert headers == {"Authorization": "Bearer stored-token"}
    assert session.calls == []


def test_a_connection_with_username_and_password_logs_in() -> None:
    """A connection like polio-staging (url + username + password) asks /api/token/ for a token."""
    connection = SimpleNamespace(url="https://iaso.example.org", username="user", password="secret")
    session = FakeSession([FakeResponse({"access": "fresh-token"})])

    base_url, headers = get_iaso_client(connection, session=session)

    assert base_url == "https://iaso.example.org"
    assert headers == {"Authorization": "Bearer fresh-token"}
    assert session.calls[0]["url"] == "https://iaso.example.org/api/token/"
    assert session.calls[0]["json"] == {"username": "user", "password": "secret"}


def test_a_connection_without_credentials_fails() -> None:
    """A connection with neither a token nor a username and password is a configuration error."""
    connection = SimpleNamespace(url="https://iaso.example.org", username="user")

    with pytest.raises(ValueError, match="neither a token"):
        get_iaso_client(connection, session=FakeSession([]))


def test_a_refused_login_fails_at_once() -> None:
    """A refused login raises, instead of producing the header ``Bearer None``."""
    session = FakeSession([FakeResponse({"detail": "No active account"}, status_code=401)])

    with pytest.raises(requests.HTTPError):
        get_access_token("https://iaso.example.org", username="user", password="wrong", session=session)


def test_a_login_answer_without_token_fails() -> None:
    """A 200 answer that carries no access token is an error too."""
    session = FakeSession([FakeResponse({})])

    with pytest.raises(IasoApiError):
        get_access_token("https://iaso.example.org", username="user", password="secret", session=session)


def test_auth_headers() -> None:
    """The token is sent as a bearer token."""
    assert auth_headers("abc") == {"Authorization": "Bearer abc"}


# --- get_paginated ----------------------------------------------------------------------------


def test_pages_are_read_until_iaso_says_there_is_no_next_page() -> None:
    """Records of every page are concatenated, in order, and the extra parameters are sent each time."""
    session = FakeSession(
        [
            FakeResponse({"campaigns": [{"id": 1}, {"id": 2}], "has_next": True}),
            FakeResponse({"campaigns": [{"id": 3}], "has_next": False}),
        ]
    )

    records = get_paginated(
        URL, HEADERS, results_key="campaigns", params={"show_test": "true"}, page_size=2, session=session
    )

    assert records == [{"id": 1}, {"id": 2}, {"id": 3}]
    assert [call["params"] for call in session.calls] == [
        {"show_test": "true", "page": 1, "limit": 2},
        {"show_test": "true", "page": 2, "limit": 2},
    ]


def test_without_has_next_a_short_page_is_the_last_one() -> None:
    """For an endpoint that does not say, a page shorter than the page size ends the reading."""
    session = FakeSession(
        [
            FakeResponse({"results": [{"id": 1}, {"id": 2}]}),
            FakeResponse({"results": [{"id": 3}]}),
        ]
    )

    assert get_paginated(URL, HEADERS, page_size=2, session=session) == [{"id": 1}, {"id": 2}, {"id": 3}]
    assert len(session.calls) == 2


def test_an_empty_page_ends_the_reading() -> None:
    """An empty first page returns no records, without asking for a second page."""
    session = FakeSession([FakeResponse({"results": [], "has_next": True})])

    assert get_paginated(URL, HEADERS, session=session) == []
    assert len(session.calls) == 1


def test_a_plain_list_is_the_whole_answer() -> None:
    """An endpoint without pagination answers a list: it is read once, even when it is long."""
    session = FakeSession([FakeResponse([{"id": 1}, {"id": 2}, {"id": 3}])])

    assert get_paginated(URL, HEADERS, page_size=2, session=session) == [{"id": 1}, {"id": 2}, {"id": 3}]
    assert len(session.calls) == 1


def test_an_http_error_on_any_page_fails_the_read() -> None:
    """A failing page raises: the records already read are not returned as if they were complete."""
    session = FakeSession(
        [
            FakeResponse({"campaigns": [{"id": 1}], "has_next": True}),
            FakeResponse({"detail": "Server error"}, status_code=500),
        ]
    )

    with pytest.raises(requests.HTTPError):
        get_paginated(URL, HEADERS, results_key="campaigns", page_size=1, session=session)


def test_a_page_without_the_results_key_fails() -> None:
    """A page that does not hold its records where expected is reported, with the keys it has."""
    session = FakeSession([FakeResponse({"results": [{"id": 1}]})])

    with pytest.raises(IasoApiError, match="campaigns"):
        get_paginated(URL, HEADERS, results_key="campaigns", session=session)
