import json
import urllib.error
import urllib.request
from email.message import Message

import pytest

from ails_intel.http_client import HttpClient


class FakeResponse:
    def __init__(self, body: bytes, *, status: int = 200, content_type: str = "application/json"):
        self._body = body
        self.status = status
        self.headers = Message()
        if content_type:
            self.headers["Content-Type"] = content_type
        self.headers["Content-Length"] = str(len(body))

    def read(self):
        return self._body

    def getcode(self):
        return self.status

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


def test_json_retries_decode_error_and_recovers(monkeypatch):
    responses = [
        FakeResponse(b"<html>temporary upstream error</html>", content_type="text/html; charset=utf-8"),
        FakeResponse(b'{"ok": true}', content_type="application/json; charset=utf-8"),
    ]
    calls = []

    def fake_urlopen(req, timeout):
        calls.append((req.full_url, timeout))
        return responses.pop(0)

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    monkeypatch.setattr("ails_intel.http_client.time.sleep", lambda _: None)

    client = HttpClient(timeout=5, retries=1)
    assert client.json("https://example.test/api") == {"ok": True}
    assert len(calls) == 2
    assert client.last_diagnostic == {
        "http_status": 200,
        "content_type": "application/json",
        "response_bytes": len(b'{"ok": true}'),
        "attempt_count": 2,
        "error_type": "",
    }


def test_json_decode_failure_keeps_safe_response_diagnostics(monkeypatch):
    body = b"<html>still not json</html>"
    calls = []

    def fake_urlopen(req, timeout):
        calls.append((req.full_url, timeout))
        return FakeResponse(body, content_type="text/html; charset=utf-8")

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    monkeypatch.setattr("ails_intel.http_client.time.sleep", lambda _: None)

    client = HttpClient(timeout=5, retries=1)
    with pytest.raises(json.JSONDecodeError):
        client.json("https://example.test/api")

    assert len(calls) == 2
    assert client.last_diagnostic["http_status"] == 200
    assert client.last_diagnostic["content_type"] == "text/html"
    assert client.last_diagnostic["response_bytes"] == len(body)
    assert client.last_diagnostic["attempt_count"] == 2
    assert client.last_diagnostic["error_type"] == "JSONDecodeError"
    note = client.diagnostic_note()
    assert "http_status=200" in note
    assert "content_type=text/html" in note
    assert "error_type=JSONDecodeError" in note
    assert "<html>" not in note


def test_http_error_retries_and_records_status_without_body(monkeypatch):
    headers = Message()
    headers["Content-Type"] = "text/html; charset=UTF-8"
    headers["Content-Length"] = "321"
    calls = []

    def fake_urlopen(req, timeout):
        calls.append((req.full_url, timeout))
        raise urllib.error.HTTPError(req.full_url, 403, "Forbidden", headers, None)

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    monkeypatch.setattr("ails_intel.http_client.time.sleep", lambda _: None)

    client = HttpClient(timeout=5, retries=1)
    with pytest.raises(urllib.error.HTTPError):
        client.text("https://example.test/feed")

    assert len(calls) == 2
    assert client.last_diagnostic == {
        "http_status": 403,
        "content_type": "text/html",
        "response_bytes": 321,
        "attempt_count": 2,
        "error_type": "HTTPError",
    }
    assert client.diagnostic_log_fields() == {
        "http_status": 403,
        "content_type": "text/html",
        "response_bytes": 321,
        "attempt_count": 2,
    }


def test_clear_diagnostic_prevents_cross_collector_staleness():
    client = HttpClient()
    client.last_diagnostic = {"http_status": 500}
    client.clear_diagnostic()
    assert client.last_diagnostic == {}
    assert client.diagnostic_note() == ""
    assert client.diagnostic_log_fields() == {}
