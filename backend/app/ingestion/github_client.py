"""Small, dependency-light GitHub REST client used by repository ingestion."""

from __future__ import annotations

import base64
import json
import time
from dataclasses import dataclass
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urljoin, urlparse, quote
from urllib.request import Request, urlopen


RETRYABLE_STATUS_CODES = {429, 500, 502, 503, 504}


class GitHubAPIError(RuntimeError):
    """An actionable GitHub API error."""

    def __init__(self, status_code: int, url: str, message: str) -> None:
        super().__init__(f"GitHub API error {status_code} for {url}: {message}")
        self.status_code = status_code
        self.url = url
        self.message = message


@dataclass(frozen=True)
class GitHubResponse:
    payload: dict | list
    headers: dict[str, str]


class GitHubClient:
    """Fetch only the GitHub resources needed for one bounded snapshot."""

    def __init__(
        self,
        base_url: str = "https://api.github.com",
        token: str | None = None,
        timeout: float = 30.0,
        max_retries: int = 3,
    ) -> None:
        self.base_url = base_url.rstrip("/") + "/"
        self.token = token or None
        self.timeout = timeout
        self.max_retries = max_retries

    @staticmethod
    def _split_repo(repository: str) -> tuple[str, str]:
        parts = repository.strip("/").split("/")
        if len(parts) != 2 or not all(parts):
            raise ValueError("repository must have the form owner/name")
        return parts[0], parts[1]

    def _request(self, path_or_url: str, params: dict[str, str | int] | None = None) -> GitHubResponse:
        if path_or_url.startswith("http://") or path_or_url.startswith("https://"):
            url = path_or_url
        else:
            url = urljoin(self.base_url, path_or_url.lstrip("/"))

        if params:
            separator = "&" if "?" in url else "?"
            url = f"{url}{separator}{urlencode(params)}"

        headers = {
            "Accept": "application/vnd.github+json",
            "User-Agent": "RepoBrain/0.1",
        }
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"

        for attempt in range(self.max_retries + 1):
            request = Request(url, headers=headers, method="GET")
            try:
                with urlopen(request, timeout=self.timeout) as response:
                    raw = response.read().decode("utf-8")
                    payload = json.loads(raw) if raw else {}
                    response_headers = {key.lower(): value for key, value in response.headers.items()}
                    return GitHubResponse(payload=payload, headers=response_headers)
            except HTTPError as exc:
                body = exc.read().decode("utf-8", errors="replace")
                try:
                    detail = json.loads(body).get("message", body)
                except json.JSONDecodeError:
                    detail = body or str(exc.reason)
                if exc.code not in RETRYABLE_STATUS_CODES or attempt >= self.max_retries:
                    raise GitHubAPIError(exc.code, url, str(detail)) from exc
            except URLError as exc:
                if attempt >= self.max_retries:
                    raise RuntimeError(f"Could not reach GitHub at {url}: {exc.reason}") from exc

            time.sleep(2**attempt)

        raise AssertionError("unreachable")

    def get_repository(self, repository: str) -> dict:
        owner, name = self._split_repo(repository)
        response = self._request(f"/repos/{owner}/{name}")
        if not isinstance(response.payload, dict):
            raise GitHubAPIError(200, response.headers.get("x-github-request-id", "repository"), "unexpected response")
        return response.payload

    def get_commit(self, repository: str, ref: str) -> dict:
        owner, name = self._split_repo(repository)
        response = self._request(f"/repos/{owner}/{name}/commits/{ref}")
        if not isinstance(response.payload, dict):
            raise GitHubAPIError(200, ref, "unexpected commit response")
        return response.payload

    def get_tree(self, repository: str, tree_sha: str) -> dict:
        owner, name = self._split_repo(repository)
        response = self._request(
            f"/repos/{owner}/{name}/git/trees/{tree_sha}",
            params={"recursive": "1"},
        )
        if not isinstance(response.payload, dict):
            raise GitHubAPIError(200, tree_sha, "unexpected tree response")
        return response.payload

    def get_file_content(self, repository: str, path: str, ref: str) -> tuple[str, dict]:
        """Return decoded file content and the source payload for one ref."""

        owner, name = self._split_repo(repository)
        encoded_path = quote(path, safe="/")
        try:
            response = self._request(
                f"/repos/{owner}/{name}/contents/{encoded_path}",
                params={"ref": ref},
            )
        except GitHubAPIError as exc:
            if exc.status_code != 403:
                raise
            raw_url = f"https://raw.githubusercontent.com/{owner}/{name}/{ref}/{encoded_path}"
            request = Request(raw_url, headers={"User-Agent": "RepoBrain/0.1"}, method="GET")
            try:
                with urlopen(request, timeout=self.timeout) as raw_response:
                    return raw_response.read().decode("utf-8"), {
                        "sha": None,
                        "source_url": raw_url,
                        "encoding": "raw",
                    }
            except (HTTPError, URLError, UnicodeDecodeError) as raw_exc:
                raise exc from raw_exc
        if not isinstance(response.payload, dict):
            raise GitHubAPIError(200, path, "unexpected file content response")
        if response.payload.get("encoding") != "base64":
            raise GitHubAPIError(200, path, "GitHub did not return base64 file content")
        try:
            content = base64.b64decode(response.payload["content"], validate=False).decode("utf-8")
        except (ValueError, UnicodeDecodeError) as exc:
            raise GitHubAPIError(200, path, "file content was not valid UTF-8 base64") from exc
        return content, response.payload

    def list_commits(self, repository: str, ref: str, limit: int) -> list[dict]:
        owner, name = self._split_repo(repository)
        commits: list[dict] = []
        page = 1
        while len(commits) < limit:
            response = self._request(
                f"/repos/{owner}/{name}/commits",
                params={"sha": ref, "per_page": min(100, limit), "page": page},
            )
            if not isinstance(response.payload, list):
                raise GitHubAPIError(200, repository, "unexpected commits response")
            if not response.payload:
                break
            commits.extend(item for item in response.payload if isinstance(item, dict))
            next_url = self._next_url(response.headers.get("link", ""))
            if not next_url:
                break
            page += 1
        return commits[:limit]

    def _list_paginated(self, path: str, params: dict[str, str | int], limit: int) -> list[dict]:
        items: list[dict] = []
        page = 1
        while len(items) < limit:
            response = self._request(path, {**params, "per_page": min(100, limit), "page": page})
            if not isinstance(response.payload, list):
                raise GitHubAPIError(200, path, "unexpected list response")
            page_items = [item for item in response.payload if isinstance(item, dict)]
            items.extend(page_items)
            if len(page_items) < min(100, limit) or not response.headers.get("link") or not self._next_url(response.headers.get("link", "")):
                break
            page += 1
        return items[:limit]

    def list_pull_requests(self, repository: str, limit: int = 50) -> list[dict]:
        owner, name = self._split_repo(repository)
        return self._list_paginated(
            f"/repos/{owner}/{name}/pulls",
            {"state": "all", "sort": "updated", "direction": "desc"},
            limit,
        )

    def list_pull_request_files(self, repository: str, number: int, limit: int = 100) -> list[dict]:
        owner, name = self._split_repo(repository)
        return self._list_paginated(f"/repos/{owner}/{name}/pulls/{number}/files", {}, limit)

    def list_pull_request_reviews(self, repository: str, number: int, limit: int = 100) -> list[dict]:
        owner, name = self._split_repo(repository)
        return self._list_paginated(f"/repos/{owner}/{name}/pulls/{number}/reviews", {}, limit)

    def list_issues(self, repository: str, limit: int = 25) -> list[dict]:
        owner, name = self._split_repo(repository)
        return self._list_paginated(
            f"/repos/{owner}/{name}/issues",
            {"state": "all", "sort": "updated", "direction": "desc"},
            limit,
        )

    def list_issue_comments(self, repository: str, number: int, limit: int = 100) -> list[dict]:
        owner, name = self._split_repo(repository)
        return self._list_paginated(f"/repos/{owner}/{name}/issues/{number}/comments", {}, limit)

    def list_pull_request_comments(self, repository: str, number: int, limit: int = 100) -> list[dict]:
        owner, name = self._split_repo(repository)
        return self._list_paginated(f"/repos/{owner}/{name}/pulls/{number}/comments", {}, limit)

    @staticmethod
    def _next_url(link_header: str) -> str | None:
        for link in link_header.split(","):
            url_part, *params = link.split(";")
            relation = "".join(params)
            if 'rel="next"' in relation:
                return url_part.strip().strip("<>")
        return None

