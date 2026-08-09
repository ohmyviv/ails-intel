from __future__ import annotations
import hashlib
import re
from urllib.parse import urlsplit, urlunsplit

WS = re.compile(r"\s+")

def normalize_title(title: str) -> str:
    return WS.sub(" ", (title or "").strip()).casefold()

def canonical_url(url: str) -> str:
    if not url:
        return ""
    p = urlsplit(url.strip())
    return urlunsplit((p.scheme.lower(), p.netloc.lower(), p.path.rstrip("/"), "", ""))

def sha256_hex(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()

def make_signal_key(source_id: str, stable_id: str, url: str, title: str, published_date: str) -> str:
    locator = (stable_id or "").strip() or canonical_url(url)
    payload = "|".join([source_id.strip(), locator, normalize_title(title), (published_date or "").strip()])
    return "sha256:" + sha256_hex(payload)

def make_signal_id(report_date_yyyymmdd: str, signal_key: str) -> str:
    return f"SIG-{report_date_yyyymmdd}-{sha256_hex(signal_key)[:12]}"

def make_coverage_id(run_key: str, producer_id: str, attempt_id: str, channel_id: str, route_id: str, source_id: str) -> str:
    payload = "|".join([run_key, producer_id, attempt_id, channel_id, route_id, source_id])
    return "sha256:" + sha256_hex(payload)
