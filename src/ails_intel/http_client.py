from __future__ import annotations

import json
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass

DEFAULT_USER_AGENT = "ails-intel/0.2 (+https://github.com/ohmyviv/ails-intel)"

@dataclass
class HttpClient:
    timeout: float = 30.0
    retries: int = 2
    user_agent: str = DEFAULT_USER_AGENT

    def _request(self, url: str) -> bytes:
        last_exc = None
        for attempt in range(self.retries + 1):
            try:
                req = urllib.request.Request(
                    url,
                    headers={
                        "User-Agent": self.user_agent,
                        "Accept": "application/json, application/atom+xml, application/xml, text/xml, */*",
                    },
                )
                with urllib.request.urlopen(req, timeout=self.timeout) as response:
                    return response.read()
            except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError) as exc:
                last_exc = exc
                if attempt >= self.retries:
                    raise
                time.sleep(min(2 ** attempt, 4))
        raise last_exc

    def json(self, base_url: str, params: dict[str, object] | None = None):
        url = base_url
        if params:
            url += ("&" if "?" in url else "?") + urllib.parse.urlencode(
                {k: v for k, v in params.items() if v is not None}, doseq=True
            )
        return json.loads(self._request(url).decode("utf-8"))

    def text(self, base_url: str, params: dict[str, object] | None = None) -> str:
        url = base_url
        if params:
            url += ("&" if "?" in url else "?") + urllib.parse.urlencode(
                {k: v for k, v in params.items() if v is not None}, doseq=True
            )
        return self._request(url).decode("utf-8")
