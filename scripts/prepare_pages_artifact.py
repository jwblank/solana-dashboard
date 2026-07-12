from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
from datetime import UTC, datetime
from pathlib import Path

VERSIONED_ASSETS = [
    "./styles.css",
    "./glossary.js",
    "./accessibility.js",
    "./build-version.js",
    "./app.js",
]


def git_value(args: list[str], fallback: str) -> str:
    try:
        return subprocess.check_output(["git", *args], text=True).strip()
    except Exception:
        return fallback


def build_version() -> str:
    return os.environ.get("GITHUB_SHA") or git_value(["rev-parse", "HEAD"], "local")


def branch_name() -> str:
    return os.environ.get("GITHUB_REF_NAME") or git_value(
        ["rev-parse", "--abbrev-ref", "HEAD"], "unknown"
    )


def copy_site(site_dir: Path, out_dir: Path) -> None:
    if out_dir.exists():
        shutil.rmtree(out_dir)
    shutil.copytree(site_dir, out_dir)


def with_version(path: str, version: str) -> str:
    separator = "&" if "?" in path else "?"
    return f"{path}{separator}v={version}"


def stamp_index(out_dir: Path, version: str) -> None:
    index_path = out_dir / "index.html"
    html = index_path.read_text(encoding="utf-8")
    for asset in VERSIONED_ASSETS:
        html = html.replace(f'href="{asset}"', f'href="{with_version(asset, version)}"')
        html = html.replace(f'src="{asset}"', f'src="{with_version(asset, version)}"')
    index_path.write_text(html, encoding="utf-8")


def write_build_version(out_dir: Path, version: str) -> None:
    (out_dir / "build-version.js").write_text(
        f'window.SOL_REALITY_CHECK_BUILD = "{version}";\n',
        encoding="utf-8",
    )


def write_deployment_info(out_dir: Path, version: str, branch: str, deployed_at: str) -> None:
    info = {
        "git_sha": version,
        "deployed_at_utc": deployed_at,
        "branch": branch,
        "site_source": "site/",
        "schema_version": "1.0",
    }
    (out_dir / "deployment-info.json").write_text(
        json.dumps(info, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def validate_required(out_dir: Path) -> None:
    required = [
        "index.html",
        "app.js",
        "styles.css",
        "build-version.js",
        "data/dashboard.json",
        "data/overview.json",
        "data/overview_history.json",
        "data/ledger.json",
        "data/backtest_summary.json",
        "data/signaalonderzoek.json",
        "data/predictive_power.json",
        "deployment-info.json",
    ]
    missing = [item for item in required if not (out_dir / item).exists()]
    if missing:
        raise SystemExit(f"Missing Pages artifact files: {missing}")


def prepare(site_dir: Path, out_dir: Path, version: str, branch: str, deployed_at: str) -> None:
    copy_site(site_dir, out_dir)
    stamp_index(out_dir, version)
    write_build_version(out_dir, version)
    write_deployment_info(out_dir, version, branch, deployed_at)
    validate_required(out_dir)


def main() -> None:
    parser = argparse.ArgumentParser(description="Prepare a deterministic GitHub Pages artifact.")
    parser.add_argument("--site-dir", default="site")
    parser.add_argument("--out-dir", default=".pages-artifact")
    parser.add_argument("--git-sha", default=build_version())
    parser.add_argument("--branch", default=branch_name())
    parser.add_argument(
        "--deployed-at-utc",
        default=datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
    )
    args = parser.parse_args()
    prepare(
        Path(args.site_dir),
        Path(args.out_dir),
        args.git_sha,
        args.branch,
        args.deployed_at_utc,
    )
    print(f"Prepared Pages artifact in {args.out_dir} for {args.git_sha}")


if __name__ == "__main__":
    main()
