"""Require a durable project checkpoint in each code-changing PR commit.

CI checks commits individually, not merely the aggregate PR diff. GitHub branch
protection must require this workflow to prevent bypass through a direct push.
"""
from __future__ import annotations

import argparse
import re
import subprocess
import sys

IMPACT_PREFIXES = ("content_manager/", "scripts/", "tests/", ".github/workflows/")
IMPACT_FILES = {"pyproject.toml", "Launch-ContentManager.bat"}
LEDGER = "docs/DEVELOPMENT-LOG.md"


def needs_checkpoint(paths: set[str]) -> bool:
    return any(p in IMPACT_FILES or p.startswith(IMPACT_PREFIXES) for p in paths)


def _git(*args: str) -> str:
    return subprocess.check_output(["git", *args], text=True).strip()


def verify_range(base: str, head: str) -> list[str]:
    """Return code-changing commits missing their own checkpoint.

    Merge commits are excluded because their constituent commits are checked
    on the PR; the merge itself should not introduce unreviewed changes.
    """
    for sha in (base, head):
        if not re.fullmatch(r"[0-9a-fA-F]{40}", sha):
            raise ValueError("Expected full 40-character commit SHA")
    failures = []
    revisions = _git("rev-list", "--reverse", "--no-merges", f"{base}..{head}")
    for sha in revisions.splitlines():
        paths = set(_git("diff-tree", "--root", "--no-commit-id", "--name-only", "-r", sha).splitlines())
        if needs_checkpoint(paths) and LEDGER not in paths:
            failures.append(sha)
    return failures


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Check each PR code commit updates the progress ledger")
    parser.add_argument("--base", required=True, help="Pull request base commit SHA")
    parser.add_argument("--head", required=True, help="Pull request head commit SHA")
    args = parser.parse_args(argv)
    try:
        failures = verify_range(args.base, args.head)
    except (OSError, subprocess.CalledProcessError, ValueError) as exc:
        print(f"Cannot check progress ledger: {exc}", file=sys.stderr)
        return 2
    if failures:
        print("Missing docs/DEVELOPMENT-LOG.md in code-changing commits:")
        for sha in failures:
            print(f"  {sha}")
        print("Record the feature, tests, limitations and next step in each such commit.")
        return 1
    print("Progress ledger updated in every code-changing PR commit.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
