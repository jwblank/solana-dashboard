from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path

from prepare_pages_artifact import prepare

CHECK_FILES = [
    "index.html",
    "app.js",
    "styles.css",
    "glossary.js",
    "accessibility.js",
    "build-version.js",
    "data/dashboard.json",
    "data/overview.json",
    "data/overview_history.json",
    "data/ledger.json",
    "data/backtest_summary.json",
    "data/signaalonderzoek.json",
]


def git_sha() -> str:
    return subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()


def git_branch() -> str:
    return subprocess.check_output(["git", "rev-parse", "--abbrev-ref", "HEAD"], text=True).strip()


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def read_bytes(path: Path) -> bytes:
    return path.read_bytes()


def fetch_bytes(url: str) -> tuple[int, bytes, str | None]:
    request = urllib.request.Request(url, headers={"Cache-Control": "no-cache"})
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            return response.status, response.read(), response.headers.get("Last-Modified")
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read(), None


def url_for(base_url: str, file_path: str, expected_sha: str) -> str:
    base = base_url.rstrip("/") + "/"
    separator = "&" if "?" in file_path else "?"
    return f"{base}{file_path}{separator}sync={expected_sha}"


def compare_once(
    site_dir: Path,
    base_url: str,
    expected_sha: str,
    branch: str,
) -> tuple[bool, list[str]]:
    messages = []
    temp_root = Path(tempfile.mkdtemp(prefix="pages-sync-"))
    try:
        expected_dir = temp_root / "artifact"
        prepare(site_dir, expected_dir, expected_sha, branch, "1970-01-01T00:00:00Z")
        info_status, info_body, info_modified = fetch_bytes(
            url_for(base_url, "deployment-info.json", expected_sha)
        )
        if info_status != 200:
            messages.append(f"deployment-info.json | live status {info_status} | FAIL")
            return False, messages
        try:
            info = json.loads(info_body)
        except json.JSONDecodeError as exc:
            messages.append(f"deployment-info.json | invalid JSON: {exc} | FAIL")
            return False, messages
        live_sha = info.get("git_sha")
        info_ok = live_sha == expected_sha
        messages.append(
            "deployment-info.json | "
            f"live git_sha {live_sha} | expected {expected_sha} | "
            f"last-modified {info_modified or 'n.v.t.'} | {'OK' if info_ok else 'FAIL'}"
        )
        if not info_ok:
            return False, messages

        all_ok = True
        for file_path in CHECK_FILES:
            local_path = expected_dir / file_path
            if not local_path.exists():
                messages.append(f"{file_path} | local missing | FAIL")
                all_ok = False
                continue
            local_hash = sha256_bytes(read_bytes(local_path))
            status, body, modified = fetch_bytes(url_for(base_url, file_path, expected_sha))
            live_hash = sha256_bytes(body) if status == 200 else "-"
            ok = status == 200 and local_hash == live_hash
            all_ok = all_ok and ok
            messages.append(
                f"{file_path} | repo/artifact {local_hash} | live {live_hash} | "
                f"status {status} | last-modified {modified or 'n.v.t.'} | {'OK' if ok else 'FAIL'}"
            )
        return all_ok, messages
    finally:
        shutil.rmtree(temp_root, ignore_errors=True)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Compare the expected Pages artifact with the live GitHub Pages site."
    )
    parser.add_argument("--site-dir", default="site")
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--expected-sha", default=git_sha())
    parser.add_argument("--branch", default=git_branch())
    parser.add_argument("--retries", type=int, default=1)
    parser.add_argument("--sleep-seconds", type=int, default=10)
    args = parser.parse_args()

    final_messages = []
    for attempt in range(1, args.retries + 1):
        ok, messages = compare_once(
            Path(args.site_dir), args.base_url, args.expected_sha, args.branch
        )
        final_messages = messages
        print(f"Pages sync check attempt {attempt}/{args.retries}")
        print("Bestand | Repo/artifact hash | Live hash | Status | Last-Modified | Resultaat")
        for message in messages:
            print(message)
        if ok:
            return
        if attempt < args.retries:
            time.sleep(args.sleep_seconds)

    print("Pages sync check failed after retries.", file=sys.stderr)
    if final_messages:
        print("\n".join(final_messages), file=sys.stderr)
    raise SystemExit(1)


if __name__ == "__main__":
    main()
