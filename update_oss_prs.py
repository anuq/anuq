#!/usr/bin/env python3
"""
Fetches merged/open PRs submitted by GITHUB_USER to repos they don't own,
then rewrites the <!-- OSS_PRS_START --> … <!-- OSS_PRS_END --> block in README.md.

Required env vars:
  GITHUB_TOKEN  – personal access token (needs public_repo read scope)
  GITHUB_USER   – GitHub username (default: anuq)
"""

import os
import re
import sys
from datetime import datetime, timezone
import urllib.request
import urllib.error
import json

GITHUB_USER = os.getenv("GITHUB_USER", "anuq")
TOKEN = os.getenv("GITHUB_TOKEN", "")
README = "README.md"

HEADERS = {
    "Accept": "application/vnd.github+json",
    "X-GitHub-Api-Version": "2022-11-28",
}
if TOKEN:
    HEADERS["Authorization"] = f"Bearer {TOKEN}"


def gh(url: str) -> dict | list:
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req) as r:
        return json.loads(r.read())


def search_prs(state: str) -> list[dict]:
    """Return all PRs (not in own repos) with the given state."""
    results = []
    page = 1
    while True:
        query = f"type:pr+author:{GITHUB_USER}+is:{state}+-user:{GITHUB_USER}"
        url = (
            f"https://api.github.com/search/issues"
            f"?q={query}&sort=updated&order=desc&per_page=100&page={page}"
        )
        data = gh(url)
        items = data.get("items", [])
        if not items:
            break
        results.extend(items)
        if len(items) < 100:
            break
        page += 1
    return results


def badge(state: str) -> str:
    if state == "merged":
        return "![merged](https://img.shields.io/badge/merged-8957e5?style=flat-square)"
    if state == "closed":
        return "![closed](https://img.shields.io/badge/closed-red?style=flat-square)"
    return "![open](https://img.shields.io/badge/open-238636?style=flat-square)"


def repo_from_url(html_url: str) -> str:
    # https://github.com/OWNER/REPO/pull/N  →  OWNER/REPO
    parts = html_url.split("/")
    return f"{parts[3]}/{parts[4]}"


def pr_number(html_url: str) -> int:
    return int(html_url.split("/")[-1])


def is_merged(pr: dict) -> bool:
    # Search API doesn't expose merged status directly; check pull_request.merged_at
    pr_url = pr.get("pull_request", {}).get("url", "")
    if not pr_url:
        return False
    try:
        detail = gh(pr_url)
        return bool(detail.get("merged_at"))
    except Exception:
        return False


def build_table(prs: list[dict]) -> str:
    rows = ["| PR | Repository | Description | Status |", "|----|------------|-------------|--------|"]
    for pr in prs:
        url = pr["html_url"]
        repo = repo_from_url(url)
        num = pr_number(url)
        title = pr["title"].replace("|", "\\|")
        state = pr["state"]  # open / closed
        if state == "closed":
            state = "merged" if is_merged(pr) else "closed"
        rows.append(f"| [#{num}]({url}) | {repo} | {title} | {badge(state)} |")
    return "\n".join(rows)


def main():
    print("Fetching open PRs …")
    open_prs = search_prs("open")
    print(f"  found {len(open_prs)}")

    print("Fetching merged PRs …")
    merged_prs = search_prs("merged")
    print(f"  found {len(merged_prs)}")

    # merged first (most recent), then still-open
    all_prs = sorted(merged_prs, key=lambda p: p["updated_at"], reverse=True)
    all_prs += sorted(open_prs, key=lambda p: p["updated_at"], reverse=True)

    if not all_prs:
        print("No PRs found – README unchanged.")
        return

    table = build_table(all_prs)
    updated_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    block = f"<!-- OSS_PRS_START -->\n{table}\n\n_Last updated: {updated_at}_\n<!-- OSS_PRS_END -->"

    with open(README, "r") as f:
        content = f.read()

    new_content = re.sub(
        r"<!-- OSS_PRS_START -->.*?<!-- OSS_PRS_END -->",
        block,
        content,
        flags=re.DOTALL,
    )

    if new_content == content:
        print("No changes.")
        return

    with open(README, "w") as f:
        f.write(new_content)

    print(f"README updated with {len(all_prs)} PRs.")


if __name__ == "__main__":
    main()
