from __future__ import annotations

import argparse
import re
from pathlib import Path

TEXT_SUFFIXES = {".py", ".md", ".yml", ".yaml", ".toml", ".json", ".txt", ".ini", ".cfg", ".sh"}

# Keep deny patterns compositional so the repository does not contain forbidden
# values merely because the scanner recognizes them.
DENY_PATTERNS = {
    "google_sheet_url": re.compile(r"https?://" + r"docs\.google\.com" + r"/spreadsheets/d/", re.I),
    "legacy_service_account_key_env": re.compile("GOOGLE_" + "SERVICE_ACCOUNT_" + "JSON"),
    "private_key": re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    "openai_secret_key": re.compile(r"\bsk-[A-Za-z0-9_-]{20,}\b"),
    "github_classic_token": re.compile(r"\bghp_[A-Za-z0-9]{20,}\b"),
    "github_fine_grained_token": re.compile(r"\bgithub_pat_[A-Za-z0-9_]{20,}\b"),
}

LONG_TOKEN = re.compile(r"(?<![A-Za-z0-9_-])([A-Za-z0-9_-]{40,60})(?![A-Za-z0-9_-])")


def _looks_like_opaque_locator(token: str) -> bool:
    if re.fullmatch(r"[0-9a-fA-F]{40}", token):  # pinned action commit SHA
        return False
    return ("_" in token or "-" in token) and any(c.isdigit() for c in token) and any(c.isupper() for c in token) and any(c.islower() for c in token)


def scan(root: Path) -> list[str]:
    findings: list[str] = []
    for path in root.rglob("*"):
        if not path.is_file() or ".git" in path.parts or path.suffix not in TEXT_SUFFIXES:
            continue
        rel = path.relative_to(root)
        text = path.read_text(encoding="utf-8", errors="ignore")
        for name, pattern in DENY_PATTERNS.items():
            if pattern.search(text):
                findings.append(f"{rel}:{name}")
        for token in LONG_TOKEN.findall(text):
            if _looks_like_opaque_locator(token):
                findings.append(f"{rel}:opaque_long_locator")
                break
    return sorted(set(findings))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("root", nargs="?", default=".")
    args = parser.parse_args()
    findings = scan(Path(args.root))
    if findings:
        print("PUBLIC_REPO_LEAK_GUARD=FAIL")
        for finding in findings:
            print(f"- {finding}")
        raise SystemExit(1)
    print("PUBLIC_REPO_LEAK_GUARD=PASS")


if __name__ == "__main__":
    main()
