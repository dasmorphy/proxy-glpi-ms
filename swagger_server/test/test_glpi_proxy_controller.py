# coding: utf-8

from __future__ import absolute_import

import unittest
from timeit import default_timer

from flask import Flask, Response, g
from werkzeug.datastructures import Headers, MultiDict

from swagger_server.controllers import clear_context
from swagger_server.controllers.glpi_proxy_controller import GlpiProxyView
from swagger_server.exception.custom_error_exception import CustomAPIException
from swagger_server.repository.proxy_repository import ProxyRepository
from swagger_server.test import BaseTestCase
from swagger_server.uses_cases.proxy_use_case import ProxyUseCase


SETTINGS = {
    "API": "https://glpi.example/apirest.php/",
    "APP_TOKEN": "configured-app-token",
    "USER_TOKEN_SESSION": "configured-user-token",
    "TIMEOUT": 12,
}


class FakeRequest:
    def __init__(self, headers=None, args=None, body=b""):
        self.headers = Headers(headers or {})
        self.args = MultiDict(args or [])
        self._body = body

    def get_data(self, cache=True):
        return self._body


class FakeRawHeaders:
    def __init__(self, values):
        self.values = values

    def keys(self):
        return list(dict(self.values).keys())

    def getlist(self, name):
        return [value for header, value in self.values if header == name]


class FakeRawResponse:
    def __init__(self, content, headers):
        self.content = content
        self.headers = FakeRawHeaders(headers)

    def read(self, decode_content=False):
        return self.content


class FakeResponse:
    def __init__(
        self, status_code, content=b"", headers=None, json_body=None, raw_headers=None
    ):
        self.status_code = status_code
        self.content = content
        self.headers = headers or {}
        self._json_body = json_body
        self.closed = False
        if raw_headers is not None:
            self.raw = FakeRawResponse(content, raw_headers)

    def json(self):
        if self._json_body is None:
            raise ValueError("No JSON")
        return self._json_body

    def close(self):
        self.closed = True


class FakeHttpClient:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def request(self, **kwargs):
        self.calls.append(kwargs)
        return self.responses.pop(0)


class FakeRepository:
    def __init__(self, token=None):
        self.token = token
        self.saved = []

    def get_glpi_token_cache(self, internal=None, external=None):
        return self.token

    def save_glpi_token_cache(
        self, token, usr_id=None, internal=None, external=None
    ):
        self.token = token
        self.saved.append(token)


class FakeControllerUseCase:
    def proxy(self, **kwargs):
        response = Response(b'{"ok":true}', status=207, content_type="application/json")
        response.headers["X-GLPI"] = "forwarded"
        response.headers["Content-Encoding"] = "gzip"
        response.headers["Content-Range"] = "0-9/25"
        response.headers.add("Set-Cookie", "glpi-session=one")
        response.headers.add("Set-Cookie", "glpi-preference=two")
        return response


class TestGlpiProxyController(BaseTestCase):
    def test_controller_and_after_request_preserve_glpi_headers(self):
        app = Flask(__name__)
        view = GlpiProxyView.__new__(GlpiProxyView)
        view.proxy_use_case = FakeControllerUseCase()

        @app.before_request
        def set_test_context():
            g.start_time = default_timer()
            g.internal = "internal-id"
            g.external = "external-id"
            g.channel = "test"
            g.system = "tests"

        app.after_request(clear_context)
        app.add_url_rule(
            "/proxy",
            view_func=lambda: view._proxy("GET", "Ticket"),
        )

        response = app.test_client().get("/proxy")

        self.assertEqual(200, response.status_code)
        self.assertEqual(
            {
                "data": {"ok": True},
                "error_code": 0,
                "external_transaction_id": None,
                "internal_transaction_id": response.json["internal_transaction_id"],
                "message": "Datos obtenidos correctamente",
            },
            response.json,
        )
        self.assertEqual("forwarded", response.headers["X-GLPI"])
        self.assertEqual("0-9/25", response.headers["Content-Range"])
        self.assertEqual(
            ["glpi-session=one", "glpi-preference=two"],
            response.headers.getlist("Set-Cookie"),
        )
        self.assertEqual("application/json", response.content_type)
        self.assertNotIn("Content-Encoding", response.headers)
        self.assertEqual("internal-id", response.headers["X-Internal-Transaction-Id"])

    def test_forwards_headers_query_body_and_forces_glpi_tokens(self):
        repository = FakeRepository("cached-session")
        http = FakeHttpClient(
            [
                FakeResponse(
                    200,
                    b'{"ok":true}',
                    {
                        "Content-Type": "application/json",
                        "Content-Encoding": "gzip",
                        "Content-Length": "11",
                        "X-GLPI": "yes",
                    },
                    raw_headers=[
                        ("Content-Type", "application/json"),
                        ("Content-Encoding", "gzip"),
                        ("Content-Length", "11"),
                        ("X-GLPI", "yes"),
                        ("Set-Cookie", "first=1"),
                        ("Set-Cookie", "second=2"),
                    ],
                )
            ]
        )
        use_case = ProxyUseCase(repository, http, SETTINGS)
        request = FakeRequest(
            headers={
                "App-Token": "untrusted-app-token",
                "Session-Token": "untrusted-session-token",
                "Content-Type": "application/json",
                "X-Custom": "forward-me",
            },
            args=[
                ("endpoint", "Ticket/123"),
                ("range", "0-9"),
                ("range", "10-19"),
            ],
            body=b'{"input":{"name":"test"}}',
        )

        response = use_case.proxy("POST", "Ticket/123", request)

        call = http.calls[0]
        self.assertEqual("https://glpi.example/apirest.php/Ticket/123", call["url"])
        self.assertEqual("configured-app-token", call["headers"]["App-Token"])
        self.assertEqual("cached-session", call["headers"]["Session-Token"])
        self.assertEqual("forward-me", call["headers"]["X-Custom"])
        self.assertEqual([("range", "0-9"), ("range", "10-19")], call["params"])
        self.assertEqual(b'{"input":{"name":"test"}}', call["data"])
        self.assertTrue(call["stream"])
        self.assertEqual(200, response.status_code)
        self.assertEqual("yes", response.headers["X-GLPI"])
        self.assertEqual("gzip", response.headers["Content-Encoding"])
        self.assertEqual("11", response.headers["Content-Length"])
        self.assertEqual(
            ["first=1", "second=2"], response.headers.getlist("Set-Cookie")
        )

    def test_renews_token_and_retries_once_after_401(self):
        repository = FakeRepository("expired-session")
        http = FakeHttpClient(
            [
                FakeResponse(401),
                FakeResponse(200, json_body={"session_token": "new-session"}),
                FakeResponse(204),
            ]
        )
        use_case = ProxyUseCase(repository, http, SETTINGS)

        response = use_case.proxy(
            "DELETE", "Ticket/123", FakeRequest(args=[("endpoint", "Ticket/123")])
        )

        self.assertEqual(204, response.status_code)
        self.assertEqual(["new-session"], repository.saved)
        self.assertEqual("GET", http.calls[1]["method"])
        self.assertEqual(
            "https://glpi.example/apirest.php/initSession", http.calls[1]["url"]
        )
        self.assertEqual(
            {
                "App-Token": "configured-app-token",
                "Authorization": "user_token configured-user-token",
            },
            http.calls[1]["headers"],
        )
        self.assertEqual("new-session", http.calls[2]["headers"]["Session-Token"])

    def test_initializes_session_when_cache_is_empty(self):
        repository = FakeRepository()
        http = FakeHttpClient(
            [
                FakeResponse(200, json_body={"session_token": "first-session"}),
                FakeResponse(200, b"[]"),
            ]
        )
        use_case = ProxyUseCase(repository, http, SETTINGS)

        use_case.proxy("GET", "Ticket", FakeRequest())

        self.assertEqual(["first-session"], repository.saved)
        self.assertEqual("first-session", http.calls[1]["headers"]["Session-Token"])

    def test_rejects_absolute_endpoint(self):
        use_case = ProxyUseCase(FakeRepository("token"), FakeHttpClient([]), SETTINGS)

        with self.assertRaises(CustomAPIException) as context:
            use_case.proxy("GET", "https://evil.example/path", FakeRequest())

        self.assertEqual(400, context.exception.status_code)


class FakeRedis:
    def __init__(self):
        self.values = {}

    def get(self, key):
        return self.values.get(key)

    def set(self, key, value, ex=None):
        self.values[key] = value
        self.last_set = (key, value, ex)


class TestProxyRepository(BaseTestCase):
    def test_saves_and_reads_token_using_a_stable_key(self):
        redis = FakeRedis()
        repository = ProxyRepository.__new__(ProxyRepository)
        repository.redis_client = type("Client", (), {"client": redis})()

        repository.save_glpi_token_cache("session-token")

        self.assertEqual("session-token", repository.get_glpi_token_cache())
        self.assertEqual(
            (ProxyRepository.SESSION_TOKEN_KEY, "session-token", None), redis.last_set
        )


if __name__ == '__main__':
    import unittest
    unittest.main()
