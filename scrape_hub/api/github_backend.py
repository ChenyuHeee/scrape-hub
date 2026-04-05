"""
GitHub Actions backend — zero-cost serverless scraping.

Triggers a GitHub Actions workflow to run Playwright scraping,
then polls for completion and downloads the results artifact.

Requirements:
    - A GitHub personal access token (PAT) with `actions` scope
    - The scrape.yml workflow in the repo's .github/workflows/
"""

from __future__ import annotations

import io
import json
import os
import time
import uuid
import zipfile
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

import urllib.request
import urllib.error

import streamlit as st


# ── Config ──────────────────────────────────────────────────

def _secret(key: str) -> str:
    """Read from Streamlit secrets, then environment."""
    val = ""
    try:
        val = st.secrets.get(key, "")
    except Exception:
        pass
    if not val:
        val = os.environ.get(key, "")
    return val


def get_gh_token() -> str:
    return _secret("GITHUB_TOKEN")


def get_gh_repo() -> str:
    """Return 'owner/repo' string."""
    return _secret("GITHUB_REPO")


def get_gh_branch() -> str:
    return _secret("GITHUB_BRANCH") or "main"


def is_github_mode() -> bool:
    """Check if GitHub Actions backend is configured."""
    return bool(get_gh_token() and get_gh_repo())


# ── Data class ──────────────────────────────────────────────

@dataclass
class ScrapeResult:
    query_type: str
    query_value: str
    items: list[dict]
    collected_at: str = field(default_factory=lambda: datetime.now().isoformat())
    error: str | None = None


# ── GitHub API helpers ──────────────────────────────────────

_API = "https://api.github.com"


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    """Handler that stops on 3xx instead of following redirects."""
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def _gh_request(
    method: str,
    path: str,
    body: dict | None = None,
    accept: str = "application/vnd.github+json",
    follow_redirects: bool = True,
) -> tuple[int, Any]:
    """Make an authenticated GitHub API request. Returns (status, parsed_json_or_bytes)."""
    token = get_gh_token()
    url = f"{_API}{path}" if path.startswith("/") else path

    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": accept,
        "X-GitHub-Api-Version": "2022-11-28",
    }

    data = None
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        headers["Content-Type"] = "application/json"

    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        if follow_redirects:
            opener = urllib.request.build_opener()
        else:
            opener = urllib.request.build_opener(_NoRedirect)
        with opener.open(req, timeout=60) as resp:
            raw = resp.read()
            status = resp.status
            ct = resp.headers.get("Content-Type", "")
            if "json" in ct:
                return status, json.loads(raw)
            return status, raw
    except urllib.error.HTTPError as e:
        # 3xx redirects arrive here when follow_redirects=False
        if e.code in (301, 302, 303, 307, 308):
            location = e.headers.get("Location", "")
            return e.code, {"location": location}
        raw = e.read()
        try:
            return e.code, json.loads(raw)
        except Exception:
            return e.code, raw


# ── Public API ──────────────────────────────────────────────

def github_health_check() -> bool:
    """Verify GitHub token and repo access."""
    if not is_github_mode():
        return False
    repo = get_gh_repo()
    status, _ = _gh_request("GET", f"/repos/{repo}/actions/workflows")
    return status == 200


def trigger_scrape(
    platform: str,
    config: dict[str, Any],
) -> str:
    """
    Trigger the scrape workflow and return a task_id.

    Raises RuntimeError on failure.
    """
    repo = get_gh_repo()
    branch = get_gh_branch()
    task_id = uuid.uuid4().hex[:12]

    status, resp = _gh_request(
        "POST",
        f"/repos/{repo}/actions/workflows/scrape.yml/dispatches",
        body={
            "ref": branch,
            "inputs": {
                "platform": platform,
                "config_json": json.dumps(config, ensure_ascii=False),
                "task_id": task_id,
            },
        },
    )

    if status not in (204, 200):
        msg = resp.get("message", resp) if isinstance(resp, dict) else str(resp)
        raise RuntimeError(f"触发 GitHub Actions 失败 ({status}): {msg}")

    return task_id


def poll_workflow_run(
    task_id: str,
    max_wait: int = 600,
    poll_interval: int = 10,
    progress_callback=None,
) -> int | None:
    """
    Poll for the workflow run triggered by task_id.
    Returns the run_id when completed, or None on timeout/failure.
    """
    repo = get_gh_repo()
    start = time.time()
    run_id = None

    # Phase 1: Find the workflow run (may take a few seconds to appear)
    while time.time() - start < max_wait:
        elapsed = int(time.time() - start)
        if progress_callback:
            progress_callback(0, 1, f"⏳ 等待 GitHub Actions 启动... ({elapsed}s)")

        status, data = _gh_request(
            "GET",
            f"/repos/{repo}/actions/workflows/scrape.yml/runs?per_page=5",
        )
        if status == 200:
            for run in data.get("workflow_runs", []):
                # Match by checking the run was created recently (within 120s)
                # and is in 'queued' or 'in_progress' or 'completed' state
                run_name = run.get("name", "")
                run_status = run.get("status", "")
                # We can't match by task_id in run metadata easily,
                # so we match the most recent run
                if run_status in ("queued", "in_progress", "completed"):
                    run_id = run["id"]
                    break

        if run_id:
            break
        time.sleep(min(poll_interval, 5))

    if not run_id:
        return None

    # Phase 2: Wait for completion
    while time.time() - start < max_wait:
        elapsed = int(time.time() - start)
        status, data = _gh_request("GET", f"/repos/{repo}/actions/runs/{run_id}")

        if status != 200:
            time.sleep(poll_interval)
            continue

        run_status = data.get("status", "")
        conclusion = data.get("conclusion", "")

        if progress_callback:
            status_text = {"queued": "排队中", "in_progress": "运行中"}.get(run_status, run_status)
            progress_callback(0.5 if run_status == "in_progress" else 0.2, 1,
                              f"⚙️ GitHub Actions {status_text}... ({elapsed}s)")

        if run_status == "completed":
            if conclusion == "success":
                return run_id
            else:
                raise RuntimeError(f"GitHub Actions 运行失败: {conclusion}")

        time.sleep(poll_interval)

    return None


def download_result(run_id: int, task_id: str) -> list[ScrapeResult]:
    """Download the scrape result artifact from a completed workflow run."""
    repo = get_gh_repo()

    # List artifacts for this run
    status, data = _gh_request("GET", f"/repos/{repo}/actions/runs/{run_id}/artifacts")
    if status != 200:
        raise RuntimeError(f"获取 Artifacts 列表失败 ({status})")

    artifact_url = None
    for art in data.get("artifacts", []):
        if task_id in art.get("name", ""):
            artifact_url = art.get("archive_download_url")
            break

    if not artifact_url:
        raise RuntimeError(f"未找到任务 {task_id} 的结果文件")

    # Download the zip — must handle redirect manually because GitHub
    # redirects to Azure Blob Storage which rejects the Authorization header.
    status, resp = _gh_request("GET", artifact_url, follow_redirects=False)
    if status in (301, 302, 303, 307, 308):
        download_url = resp.get("location", "") if isinstance(resp, dict) else ""
        if not download_url:
            raise RuntimeError("Artifact 重定向 URL 为空")
        # Fetch from the redirect URL WITHOUT auth headers
        dl_req = urllib.request.Request(download_url, method="GET")
        try:
            with urllib.request.urlopen(dl_req, timeout=120) as dl_resp:
                raw = dl_resp.read()
        except urllib.error.HTTPError as e:
            raise RuntimeError(f"下载 Artifact 失败 ({e.code})")
    elif status == 200:
        raw = resp
    else:
        raise RuntimeError(f"下载 Artifact 失败 ({status})")

    # Extract JSON from zip
    with zipfile.ZipFile(io.BytesIO(raw)) as zf:
        names = zf.namelist()
        if not names:
            raise RuntimeError("Artifact zip 为空")
        content = zf.read(names[0])

    data = json.loads(content)

    results = []
    for item in data.get("results", []):
        results.append(ScrapeResult(
            query_type=item["query_type"],
            query_value=item["query_value"],
            items=item["items"],
            collected_at=item.get("collected_at", ""),
            error=item.get("error"),
        ))

    return results


def github_scrape(
    platform: str,
    config: dict[str, Any],
    progress_callback=None,
) -> list[ScrapeResult]:
    """
    Full pipeline: trigger → poll → download results.

    This is the main entry point used by Streamlit pages.
    """
    if progress_callback:
        progress_callback(0, 1, "🚀 正在触发 GitHub Actions...")

    task_id = trigger_scrape(platform, config)

    run_id = poll_workflow_run(
        task_id,
        max_wait=600,
        poll_interval=8,
        progress_callback=progress_callback,
    )

    if run_id is None:
        raise RuntimeError("等待 GitHub Actions 超时（10分钟），请稍后在 Actions 页面查看结果。")

    if progress_callback:
        progress_callback(0.9, 1, "📥 正在下载结果...")

    results = download_result(run_id, task_id)

    if progress_callback:
        total = sum(len(r.items) for r in results)
        progress_callback(1, 1, f"✅ 完成！共收集 {total} 条")

    return results
