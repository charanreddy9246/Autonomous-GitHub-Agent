import os
import time

import requests

GITHUB_API = "https://api.github.com"


class GitHubClient:
    def __init__(self, token: str | None = None, repo: str | None = None):
        self.token = token or os.environ["GITHUB_TOKEN"]
        self.repo = repo or os.environ["GITHUB_REPO"]  # "owner/repo"
        self.session = requests.Session()
        self.session.headers.update(
            {
                "Authorization": f"Bearer {self.token}",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
            }
        )
        self.call_count = 0
        self.total_time_s = 0.0

    def _request(self, method: str, path: str, **kwargs):
        url = path if path.startswith("http") else f"{GITHUB_API}{path}"
        start = time.monotonic()
        resp = self.session.request(method, url, timeout=20, **kwargs)
        self.total_time_s += time.monotonic() - start
        self.call_count += 1
        if resp.status_code >= 400:
            raise GitHubAPIError(resp.status_code, resp.text, method, url)
        if resp.status_code == 204 or not resp.content:
            return None
        return resp.json()

    def get(self, path, **kw):
        return self._request("GET", path, **kw)

    def post(self, path, **kw):
        return self._request("POST", path, **kw)

    def patch(self, path, **kw):
        return self._request("PATCH", path, **kw)

    def delete(self, path, **kw):
        return self._request("DELETE", path, **kw)

    def repo_path(self, suffix: str) -> str:
        return f"/repos/{self.repo}{suffix}"


class GitHubAPIError(Exception):
    def __init__(self, status_code: int, body: str, method: str, url: str):
        self.status_code = status_code
        self.body = body
        super().__init__(f"{method} {url} -> {status_code}: {body[:300]}")
