from __future__ import annotations

import json
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field

DEFAULT_USER_AGENT = "ails-intel/0.2 (+https://github.com/ohmyviv/ails-intel)"


def _header_value(headers, name: str) -> str:
    if headers is None:
        return ""
    try:
        return str(headers.get(name, "") or "").strip()
    except Exception:
        return ""


def _content_type(headers) -> str:
    return _header_value(headers, "Content-Type").split(";", 1)[0].strip()


def _content_length(headers) -> int:
    raw = _header_value(headers, "Content-Length")
    try:
        return max(0, int(raw))
    except (TypeError, ValueError):
        return 0


@dataclass
class HttpClient:
    timeout: float = 30.0
    retries: int = 2
    user_agent: str = DEFAULT_USER_AGENT
    last_diagnostic: dict[str, object] = field(default_factory=dict, init=False)

    def clear_diagnostic(self) -> None:
        self.last_diagnostic = {}

    def diagnostic_note(self) -> str:
        if not self.last_diagnostic:
            return ""
        ordered = (
            "http_status",
            "content_type",
            "response_bytes",
            "attempt_count",
            "error_type",
        )
        return ";".join(f"{key}={self.last_diagnostic.get(key, '')}" for key in ordered)

    def diagnostic_log_fields(self) -> dict[str, object]:
        if not self.last_diagnostic:
            return {}
        return {
            "http_status": int(self.last_diagnostic.get("http_status", 0) or 0),
            "content_type": str(self.last_diagnostic.get("content_type", "") or ""),
            "response_bytes": int(self.last_diagnostic.get("response_bytes", 0) or 0),
            "attempt_count": int(self.last_diagnostic.get("attempt_count", 0) or 0),
        }

    def _request_once(self, url: str) -> bytes:
        req = urllib.request.Request(
            url,
            headers={
                "User-Agent": self.user_agent,
                "Accept": "application/json, application/atom+xml, application/rss+xml, application/xml, text/xml, */*",
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as response:
                body = response.read()
                status = int(getattr(response, "status", 0) or response.getcode() or 0)
                self.last_diagnostic = {
                    "http_status": status,
                    "content_type": _content_type(getattr(response, "headers", None)),
                    "response_bytes": len(body),
                    "attempt_count": 1,
                    "error_type": "",
                }
                return body
        except urllib.error.HTTPError as exc:
            self.last_diagnostic = {
                "http_status": int(getattr(exc, "code", 0) or 0),
                "content_type": _content_type(getattr(exc, "headers", None)),
                "response_bytes": _content_length(getattr(exc, "headers", None)),
                "attempt_count": 1,
                "error_type": type(exc).__name__,
            }
            raise
        except (urllib.error.URLError, TimeoutError) as exc:
            self.last_diagnostic = {
                "http_status": 0,
                "content_type": "",
                "response_bytes": 0,
                "attempt_count": 1,
                "error_type": type(exc).__name__,
            }
            raise

    def _request(self, url: str, *, retries: int | None = None) -> bytes:
        retry_limit = self.retries if retries is None else max(0, int(retries))
        last_exc = None
        for attempt in range(retry_limit + 1):
            try:
                body = self._request_once(url)
                self.last_diagnostic["attempt_count"] = attempt + 1
                return body
            except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError) as exc:
                last_exc = exc
                self.last_diagnostic["attempt_count"] = attempt + 1
                if attempt >= retry_limit:
                    raise
                time.sleep(min(2 ** attempt, 4))
        raise last_exc

    @staticmethod
    def _url(base_url: str, params: dict[str, object] | None = None) -> str:
        url = base_url
        if params:
            url += ("&" if "?" in url else "?") + urllib.parse.urlencode(
                {k: v for k, v in params.items() if v is not None}, doseq=True
            )
        return url

    def json(self, base_url: str, params: dict[str, object] | None = None):
        url = self._url(base_url, params)
        last_exc = None
        for attempt in range(self.retries + 1):
            try:
                body = self._request(url, retries=0)
                payload = json.loads(body.decode("utf-8"))
                self.last_diagnostic["attempt_count"] = attempt + 1
                self.last_diagnostic["error_type"] = ""
                return payload
            except (
                urllib.error.HTTPError,
                urllib.error.URLError,
                TimeoutError,
                UnicodeDecodeError,
                json.JSONDecodeError,
            ) as exc:
                last_exc = exc
                if not self.last_diagnostic:
                    self.last_diagnostic = {
                        "http_status": 0,
                        "content_type": "",
                        "response_bytes": 0,
                    }
                self.last_diagnostic["attempt_count"] = attempt + 1
                self.last_diagnostic["error_type"] = type(exc).__name__
                if attempt >= self.retries:
                    raise
                time.sleep(min(2 ** attempt, 4))
        raise last_exc

    def text(self, base_url: str, params: dict[str, object] | None = None) -> str:
        return self._request(self._url(base_url, params)).decode("utf-8")
