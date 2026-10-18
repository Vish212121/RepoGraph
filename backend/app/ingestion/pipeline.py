"""Orchestrate fetch, normalization, manifest persistence, and graph loading."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.config import Settings, get_settings
from app.ingestion.github_client import GitHubClient
from app.ingestion.loader import GraphLoader
from app.ingestion.models import SnapshotData
from app.ingestion.normalizer import normalize_snapshot


def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _manifest_path(settings: Settings) -> Path:
    return settings.data_dir / "repository.json"


def _known_sha(settings: Settings) -> str | None:
    if settings.target_sha:
        return settings.target_sha
    path = _manifest_path(settings)
    if not path.exists():
        return None
    try:
        manifest = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if manifest.get("repository") == settings.target_repo:
        return manifest.get("commit_sha")
    return None


def _write_manifest(settings: Settings, data: SnapshotData) -> None:
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    manifest = {
        "repository": settings.target_repo,
        "commit_sha": data.snapshot["commit_sha"],
        "default_branch": data.repository.get("default_branch"),
        "snapshot_id": data.snapshot["id"],
        "captured_at": data.snapshot["captured_at"],
        "source_url": data.repository["source_url"],
        "counts": data.counts,
    }
    _manifest_path(settings).write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")


def ingest_repository(
    settings: Settings | None = None,
    client: GitHubClient | None = None,
    loader: GraphLoader | None = None,
) -> tuple[SnapshotData, dict[str, int]]:
    """Ingest one exact repository snapshot and return its data and counts."""

    active_settings = settings or get_settings()
    api = client or GitHubClient(
        base_url=active_settings.github_api_base_url,
        token=active_settings.github_token,
    )
    repository_payload = api.get_repository(active_settings.target_repo)
    target_sha = _known_sha(active_settings)
    if not target_sha:
        branch = repository_payload.get("default_branch")
        if not branch:
            raise RuntimeError("GitHub repository response did not contain a default branch")
        target_sha = api.get_commit(active_settings.target_repo, branch).get("sha")
    if not target_sha:
        raise RuntimeError("Could not resolve a target commit SHA")

    target_commit = api.get_commit(active_settings.target_repo, target_sha)
    resolved_sha = target_commit.get("sha")
    if resolved_sha != target_sha:
        raise RuntimeError(f"GitHub resolved {target_sha} to unexpected commit {resolved_sha}")

    tree_sha = ((target_commit.get("commit") or {}).get("tree") or {}).get("sha") or target_sha
    tree_payload = api.get_tree(active_settings.target_repo, tree_sha)
    if tree_payload.get("truncated"):
        raise RuntimeError("GitHub returned a truncated recursive tree; snapshot was not loaded")
    tree_entries = tree_payload.get("tree") or []
    if len([entry for entry in tree_entries if entry.get("type") == "blob"]) > active_settings.snapshot_max_files:
        raise RuntimeError(
            f"Repository contains more than the configured file limit ({active_settings.snapshot_max_files})"
        )

    commit_summaries = api.list_commits(
        active_settings.target_repo,
        target_sha,
        active_settings.snapshot_commit_limit,
    )
    commit_payloads = [
        api.get_commit(active_settings.target_repo, summary["sha"])
        for summary in commit_summaries
        if summary.get("sha")
    ]
    if not commit_payloads or commit_payloads[0].get("sha") != target_sha:
        raise RuntimeError("The fetched commit history did not begin at the requested target SHA")

    data = normalize_snapshot(
        repository_name=active_settings.target_repo,
        repository_payload=repository_payload,
        target_sha=target_sha,
        tree_payload=tree_payload,
        commit_payloads=commit_payloads,
        captured_at=_now(),
    )
    if not data.files or not data.commits:
        raise RuntimeError("Snapshot normalization produced no files or commits")

    _write_manifest(active_settings, data)
    active_loader = loader or GraphLoader(batch_size=active_settings.ingest_batch_size)
    counts = active_loader.load(data)
    return data, counts

