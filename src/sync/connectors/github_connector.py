"""GitHub sync connector — repos, issues, PRs, and README content.

Uses the GitHub REST API v3 with personal access token authentication.
Supports listing repos, issues, and pull requests; fetching their content;
and detecting changes via the API's built-in filtering parameters.
"""

from __future__ import annotations

import base64
import logging
from datetime import datetime, timezone
from typing import Any

import requests

from src.sync.connector_base import BaseSyncConnector
from src.sync.models import SyncConnectionResult, SyncResource

_MAX_PAGES = 10
_PAGE_SIZE = 100
_TIMEOUT = 15


class GithubConnector(BaseSyncConnector):
    """Sync connector for GitHub repos, issues, pull requests, and README files.

    Config keys:
        token:     GitHub personal access token (required)
        owner:     GitHub username or organization name
        repo:      Repository name (required for issues/prs)
        resource:  One of "repos", "issues", "prs" (default "issues")
    """

    connector_type = "github"

    def __init__(self, config: dict | None = None) -> None:
        super().__init__(config)
        self.token: str = self.config.get("token", "")
        self.owner: str = self.config.get("owner", "")
        self.repo: str = self.config.get("repo", "")
        self.resource_type: str = self.config.get("resource", "issues")
        self.base_url: str = "https://api.github.com"

        self.session = requests.Session()
        self.session.headers.update(
            {
                "Accept": "application/vnd.github+json",
                "User-Agent": "CognitiveOS-Sync/1.0",
                "X-GitHub-Api-Version": "2022-11-28",
            }
        )
        if self.token:
            self.session.headers["Authorization"] = f"Bearer {self.token}"

    # ── test_connection ──────────────────────────────────────────────────

    def test_connection(self) -> SyncConnectionResult:
        """Validate the token and connectivity by calling /user."""
        if not self.token:
            return SyncConnectionResult(
                success=False,
                message="GitHub personal access token is required",
            )

        try:
            resp = self.session.get(f"{self.base_url}/user", timeout=_TIMEOUT)
            if resp.status_code == 200:
                user = resp.json()
                return SyncConnectionResult(
                    success=True,
                    message=f"Connected as {user.get('login', 'unknown')}",
                )
            if resp.status_code == 401:
                return SyncConnectionResult(
                    success=False,
                    message="Invalid or expired GitHub token (HTTP 401)",
                )
            return SyncConnectionResult(
                success=False,
                message=f"GitHub API returned HTTP {resp.status_code}: {resp.text[:200]}",
            )
        except requests.exceptions.Timeout:
            return SyncConnectionResult(
                success=False,
                message="Connection timed out — check network or GitHub status",
            )
        except requests.exceptions.ConnectionError:
            return SyncConnectionResult(
                success=False,
                message="Could not reach api.github.com — check network",
            )
        except Exception:
            self.logger.exception("test_connection failed")
            return SyncConnectionResult(
                success=False,
                message="Unexpected error during connection test",
            )

    # ── list_resources ───────────────────────────────────────────────────

    def list_resources(self) -> list[SyncResource]:
        """List resources based on the configured resource type."""
        try:
            if self.resource_type == "repos":
                return self._list_repos()
            if self.resource_type == "issues":
                return self._list_issues()
            if self.resource_type == "prs":
                return self._list_prs()
            self.logger.warning(
                "Unknown resource_type=%s — expected repos|issues|prs",
                self.resource_type,
            )
            return []
        except Exception:
            self.logger.exception("list_resources failed")
            return []

    # ── fetch_changes ────────────────────────────────────────────────────

    def fetch_changes(self, since: datetime | None) -> list[dict[str, Any]]:
        """Return lightweight change descriptors since *since* (or all)."""
        try:
            if self.resource_type == "repos":
                return self._fetch_repo_changes(since)
            if self.resource_type == "issues":
                return self._fetch_issue_changes(since)
            if self.resource_type == "prs":
                return self._fetch_pr_changes(since)
            return _resources_to_changes(self.list_resources(), since)
        except Exception:
            self.logger.exception("fetch_changes failed")
            return []

    # ── fetch_content ────────────────────────────────────────────────────

    def fetch_content(self, resource_id: str) -> dict[str, Any]:
        """Fetch full content for a resource.

        resource_id formats:
            "owner/repo"                 → repo README
            "owner/repo/issues/123"      → issue body + comments
            "owner/repo/pulls/123"       → PR body + diff
        """
        try:
            parts = resource_id.split("/")
            if len(parts) == 2:
                return self._fetch_readme(parts[0], parts[1])
            if len(parts) >= 4 and parts[2] == "issues":
                return self._fetch_issue_content(parts[0], parts[1], int(parts[3]))
            if len(parts) >= 4 and parts[2] == "pulls":
                return self._fetch_pr_content(parts[0], parts[1], int(parts[3]))
            return {
                "content": "",
                "content_type": "text",
                "metadata": {"error": f"Unrecognized resource_id: {resource_id}"},
            }
        except Exception:
            self.logger.exception("fetch_content failed for %s", resource_id)
            return {
                "content": "",
                "content_type": "text",
                "metadata": {"error": f"fetch_content failed for {resource_id}"},
            }

    # ── Private: repos ───────────────────────────────────────────────────

    def _list_repos(self) -> list[SyncResource]:
        if self.owner:
            url = f"{self.base_url}/users/{self.owner}/repos"
        else:
            url = f"{self.base_url}/user/repos"
        params: dict[str, Any] = {"per_page": _PAGE_SIZE, "type": "all", "sort": "updated"}
        repos = self._paginate(url, params)

        results: list[SyncResource] = []
        for r in repos:
            results.append(
                SyncResource(
                    resource_id=r["full_name"],
                    name=r["full_name"],
                    resource_type="repository",
                    updated_at=_parse_iso(r.get("updated_at", "")),
                    size_bytes=r.get("size", 0) * 1024,
                    metadata={
                        "description": r.get("description") or "",
                        "language": r.get("language") or "",
                        "stars": r.get("stargazers_count", 0),
                        "forks": r.get("forks_count", 0),
                        "default_branch": r.get("default_branch", "main"),
                        "html_url": r["html_url"],
                        "private": r.get("private", False),
                    },
                )
            )
        return results

    def _fetch_repo_changes(self, since: datetime | None) -> list[dict[str, Any]]:
        resources = self._list_repos()
        return _resources_to_changes(resources, since)

    # ── Private: issues ──────────────────────────────────────────────────

    def _list_issues(self) -> list[SyncResource]:
        if not self.owner or not self.repo:
            self.logger.warning("list_issues requires owner and repo in config")
            return []
        url = f"{self.base_url}/repos/{self.owner}/{self.repo}/issues"
        params: dict[str, Any] = {
            "state": "all",
            "per_page": _PAGE_SIZE,
            "sort": "updated",
            "direction": "desc",
        }
        issues = self._paginate(url, params)

        results: list[SyncResource] = []
        for i in issues:
            # Exclude PRs that appear in the issues endpoint
            results.append(
                SyncResource(
                    resource_id=f"{self.owner}/{self.repo}/issues/{i['number']}",
                    name=f"#{i['number']}: {i['title']}",
                    resource_type="issue",
                    updated_at=_parse_iso(i.get("updated_at", "")),
                    size_bytes=len(i.get("body") or ""),
                    metadata={
                        "number": i["number"],
                        "state": i.get("state", "unknown"),
                        "html_url": i.get("html_url", ""),
                        "labels": [lbl["name"] for lbl in i.get("labels", [])],
                        "created_at": i.get("created_at", ""),
                        "comments": i.get("comments", 0),
                    },
                )
            )
        return results

    def _fetch_issue_changes(self, since: datetime | None) -> list[dict[str, Any]]:
        if not self.owner or not self.repo:
            return []
        url = f"{self.base_url}/repos/{self.owner}/{self.repo}/issues"
        params: dict[str, Any] = {
            "state": "all",
            "per_page": _PAGE_SIZE,
            "sort": "updated",
            "direction": "desc",
        }
        if since:
            params["since"] = since.isoformat()

        issues = self._paginate(url, params)
        return [
            {
                "resource_id": f"{self.owner}/{self.repo}/issues/{i['number']}",
                "resource_type": "issue",
                "updated_at": i.get("updated_at", ""),
                "change_type": "updated",
                "title": i.get("title", ""),
                "state": i.get("state", "unknown"),
            }
            for i in issues
        ]

    # ── Private: pull requests ───────────────────────────────────────────

    def _list_prs(self) -> list[SyncResource]:
        if not self.owner or not self.repo:
            self.logger.warning("list_prs requires owner and repo in config")
            return []
        url = f"{self.base_url}/repos/{self.owner}/{self.repo}/pulls"
        params: dict[str, Any] = {
            "state": "all",
            "per_page": _PAGE_SIZE,
            "sort": "updated",
            "direction": "desc",
        }
        prs = self._paginate(url, params)

        results: list[SyncResource] = []
        for p in prs:
            diff_estimate = (p.get("additions", 0) + p.get("deletions", 0)) * 100
            results.append(
                SyncResource(
                    resource_id=f"{self.owner}/{self.repo}/pulls/{p['number']}",
                    name=f"PR #{p['number']}: {p['title']}",
                    resource_type="pull_request",
                    updated_at=_parse_iso(p.get("updated_at", "")),
                    size_bytes=len(p.get("body") or "") + diff_estimate,
                    metadata={
                        "number": p["number"],
                        "state": p.get("state", "unknown"),
                        "draft": p.get("draft", False),
                        "merged": p.get("merged", False),
                        "html_url": p.get("html_url", ""),
                        "base_branch": p.get("base", {}).get("ref", ""),
                        "head_branch": p.get("head", {}).get("ref", ""),
                        "created_at": p.get("created_at", ""),
                        "additions": p.get("additions", 0),
                        "deletions": p.get("deletions", 0),
                    },
                )
            )
        return results

    def _fetch_pr_changes(self, since: datetime | None) -> list[dict[str, Any]]:
        if not self.owner or not self.repo:
            return []
        url = f"{self.base_url}/repos/{self.owner}/{self.repo}/pulls"
        params: dict[str, Any] = {
            "state": "all",
            "per_page": _PAGE_SIZE,
            "sort": "updated",
            "direction": "desc",
        }
        prs = self._paginate(url, params)
        if since:
            prs = [
                p
                for p in prs
                if _parse_iso(p.get("updated_at", "")) is not None
                and _parse_iso(p.get("updated_at", "")) >= since  # type: ignore[operator]
            ]

        return [
            {
                "resource_id": f"{self.owner}/{self.repo}/pulls/{p['number']}",
                "resource_type": "pull_request",
                "updated_at": p.get("updated_at", ""),
                "change_type": "updated",
                "title": p.get("title", ""),
                "state": p.get("state", "unknown"),
            }
            for p in prs
        ]

    # ── Private: content fetchers ────────────────────────────────────────

    def _fetch_readme(self, owner: str, repo: str) -> dict[str, Any]:
        url = f"{self.base_url}/repos/{owner}/{repo}/readme"
        try:
            resp = self.session.get(url, timeout=_TIMEOUT)
        except requests.exceptions.RequestException:
            self.logger.exception("README request failed")
            return {"content": "", "content_type": "text", "metadata": {"error": "Network error"}}

        if resp.status_code != 200:
            return {
                "content": "",
                "content_type": "text",
                "metadata": {"error": f"README not found (HTTP {resp.status_code})"},
            }

        data = resp.json()
        content = base64.b64decode(data.get("content", "")).decode("utf-8", errors="replace")
        return {
            "content": content,
            "content_type": "markdown",
            "metadata": {
                "name": data.get("name", "README.md"),
                "path": data.get("path", ""),
                "sha": data.get("sha", ""),
                "html_url": data.get("html_url", ""),
                "size": data.get("size", 0),
            },
        }

    def _fetch_issue_content(self, owner: str, repo: str, issue_number: int) -> dict[str, Any]:
        url = f"{self.base_url}/repos/{owner}/{repo}/issues/{issue_number}"
        try:
            resp = self.session.get(url, timeout=_TIMEOUT)
        except requests.exceptions.RequestException:
            self.logger.exception("Issue request failed")
            return {"content": "", "content_type": "text", "metadata": {"error": "Network error"}}

        if resp.status_code != 200:
            return {
                "content": "",
                "content_type": "text",
                "metadata": {"error": f"Issue #{issue_number} not found (HTTP {resp.status_code})"},
            }

        issue = resp.json()
        body = issue.get("body") or ""

        # Fetch comments
        comments_text = self._fetch_issue_comments(owner, repo, issue_number)
        if comments_text:
            full_content = f"# {issue['title']}\n\n{body}\n\n## Comments\n\n{comments_text}"
        else:
            full_content = f"# {issue['title']}\n\n{body}"

        return {
            "content": full_content,
            "content_type": "markdown",
            "metadata": {
                "number": issue["number"],
                "title": issue.get("title", ""),
                "state": issue.get("state", "unknown"),
                "html_url": issue.get("html_url", ""),
                "created_at": issue.get("created_at", ""),
                "updated_at": issue.get("updated_at", ""),
                "labels": [lbl["name"] for lbl in issue.get("labels", [])],
                "comments_count": issue.get("comments", 0),
            },
        }

    def _fetch_issue_comments(self, owner: str, repo: str, issue_number: int) -> str:
        url = f"{self.base_url}/repos/{owner}/{repo}/issues/{issue_number}/comments"
        params: dict[str, Any] = {"per_page": _PAGE_SIZE}
        comments = self._paginate(url, params)
        if not comments:
            return ""
        parts: list[str] = []
        for c in comments:
            user = c.get("user", {}).get("login", "unknown") if c.get("user") else "unknown"
            parts.append(f"**{user}** ({c.get('created_at', '')}):\n{c.get('body', '')}")
        return "\n\n---\n\n".join(parts)

    def _fetch_pr_content(self, owner: str, repo: str, pr_number: int) -> dict[str, Any]:
        url = f"{self.base_url}/repos/{owner}/{repo}/pulls/{pr_number}"
        try:
            resp = self.session.get(url, timeout=_TIMEOUT)
        except requests.exceptions.RequestException:
            self.logger.exception("PR request failed")
            return {"content": "", "content_type": "text", "metadata": {"error": "Network error"}}

        if resp.status_code != 200:
            return {
                "content": "",
                "content_type": "text",
                "metadata": {"error": f"PR #{pr_number} not found (HTTP {resp.status_code})"},
            }

        pr = resp.json()
        body = pr.get("body") or ""

        diff_text = self._fetch_pr_diff(owner, repo, pr_number)
        if diff_text:
            full_content = (
                f"# {pr['title']}\n\n{body}\n\n## Diff\n\n```diff\n{diff_text}\n```"
            )
        else:
            full_content = f"# {pr['title']}\n\n{body}"

        return {
            "content": full_content,
            "content_type": "markdown",
            "metadata": {
                "number": pr["number"],
                "title": pr.get("title", ""),
                "state": pr.get("state", "unknown"),
                "draft": pr.get("draft", False),
                "merged": pr.get("merged", False),
                "html_url": pr.get("html_url", ""),
                "base_branch": pr.get("base", {}).get("ref", ""),
                "head_branch": pr.get("head", {}).get("ref", ""),
                "created_at": pr.get("created_at", ""),
                "updated_at": pr.get("updated_at", ""),
                "additions": pr.get("additions", 0),
                "deletions": pr.get("deletions", 0),
            },
        }

    def _fetch_pr_diff(self, owner: str, repo: str, pr_number: int) -> str:
        url = f"{self.base_url}/repos/{owner}/{repo}/pulls/{pr_number}"
        try:
            resp = self.session.get(
                url,
                timeout=_TIMEOUT,
                headers={"Accept": "application/vnd.github.v3.diff"},
            )
        except requests.exceptions.RequestException:
            self.logger.exception("PR diff request failed")
            return ""

        if resp.status_code == 200:
            return resp.text[:50000]  # Truncate large diffs
        return ""

    # ── Private: pagination helper ───────────────────────────────────────

    def _paginate(
        self, url: str, params: dict[str, Any]
    ) -> list[dict[str, Any]]:
        """Collect all pages from a paginated GitHub API endpoint."""
        results: list[dict[str, Any]] = []
        page = 1
        while page <= _MAX_PAGES:
            p = {**params, "page": page}
            try:
                resp = self.session.get(url, params=p, timeout=_TIMEOUT)
            except requests.exceptions.RequestException:
                self.logger.exception("Pagination request failed at page %d", page)
                break

            if resp.status_code != 200:
                self.logger.warning(
                    "Pagination HTTP %d at page %d for %s", resp.status_code, page, url
                )
                break

            data = resp.json()
            if not isinstance(data, list) or not data:
                break

            results.extend(data)

            if len(data) < _PAGE_SIZE:
                break
            page += 1

        return results


# ── Shared helpers ───────────────────────────────────────────────────────


def _parse_iso(value: str) -> datetime | None:
    """Parse an ISO-8601 timestamp string to a timezone-aware datetime."""
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return dt
    except (ValueError, TypeError):
        return None


def _resources_to_changes(
    resources: list[SyncResource], since: datetime | None
) -> list[dict[str, Any]]:
    """Convert SyncResource list to change descriptors, optionally filtered."""
    filtered = resources
    if since is not None:
        filtered = [
            r
            for r in resources
            if r.updated_at is not None and r.updated_at >= since
        ]
    return [
        {
            "resource_id": r.resource_id,
            "resource_type": r.resource_type,
            "updated_at": r.updated_at.isoformat() if r.updated_at else None,
            "change_type": "updated",
            "name": r.name,
        }
        for r in filtered
    ]


# ── Auto-registration ───────────────────────────────────────────────────

from src.sync import _register  # noqa: E402

_register("github", GithubConnector)
