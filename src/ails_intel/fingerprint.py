from __future__ import annotations
import hashlib

EMPTY_SHA256 = "sha256:e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"

def frozen_manifest_fingerprint(items: list[dict]) -> str:
    payload_lines = []
    for item in sorted(items, key=lambda x: int(x["item_index"])):
        payload_lines.append(
            f'{item["item_index"]}|{item["event_key_v11"]}|{item["title"]}|{item["primary_url"]}'
        )
    payload = "\n".join(payload_lines).encode("utf-8")
    return "sha256:" + hashlib.sha256(payload).hexdigest()
