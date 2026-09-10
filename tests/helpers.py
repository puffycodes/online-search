"""Lightweight stand-ins for ``requests`` objects, shared across test modules."""


class FakeResponse:
    """Minimal duck-type of ``requests.Response``.

    Pass ``json_data`` for a decodable body (or an ``Exception`` instance to
    have ``.json()`` raise it); leave it ``None`` to make ``.json()`` raise
    ``ValueError`` the way a non-JSON body does. ``raise_for_status`` is an
    optional exception raised by that method.
    """

    def __init__(self, *, json_data=None, text="", status_code=200, raise_for_status=None):
        self._json_data = json_data
        self.text = text
        self.status_code = status_code
        self.ok = 200 <= status_code < 400
        self._raise_for_status = raise_for_status

    def json(self):
        if isinstance(self._json_data, Exception):
            raise self._json_data
        if self._json_data is None:
            raise ValueError("No JSON object could be decoded")
        return self._json_data

    def raise_for_status(self):
        if self._raise_for_status is not None:
            raise self._raise_for_status


class FakeSession:
    """Records ``.get`` / ``.post`` calls and hands back queued FakeResponses."""

    def __init__(self, get_responses=None, post_responses=None):
        self._get = list(get_responses or [])
        self._post = list(post_responses or [])
        self.get_calls = []
        self.post_calls = []
        self.headers = {}

    def get(self, url, **kwargs):
        self.get_calls.append((url, kwargs))
        return self._get.pop(0) if self._get else FakeResponse(json_data={})

    def post(self, url, **kwargs):
        self.post_calls.append((url, kwargs))
        return self._post.pop(0) if self._post else FakeResponse(json_data={})
