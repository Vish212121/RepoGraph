"""Convert GitHub JSON responses into stable RepoBrain graph records."""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from pathlib import PurePosixPath
from typing import Any

from app.ingestion.models import SnapshotData


MAX_PATCH_CHARS = 12_000


def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _source_url(repository: str, suffix: str = "") -> str:
    return f"https://github.com/{repository}{suffix}"


def _file_id(repository: str, path: str) -> str:
    return f"github:{repository}:file:{path}"


def _commit_id(sha: str) -> str:
    return f"github:commit:{sha}"


def _person_record(repository: str, person: dict[str, Any] | None, fallback: dict[str, Any] | None) -> dict[str, Any]:
    person = person or {}
    fallback = fallback or {}
    login = person.get("login")
    name = person.get("name") or fallback.get("name") or "Unknown"
    email = fallback.get("email") or ""
    if login:
        person_id = f"github:user:{login}"
        identity_source = "github_login"
    else:
        digest = hashlib.sha256(f"github|{email.lower()}|{name.lower()}".encode()).hexdigest()[:24]
        person_id = f"github:identity:{digest}"
        identity_source = "hashed_commit_identity"
    return {
        "id": person_id,
        "provider": "github",
        "login": login,
        "display_name": name,
        "identity_source": identity_source,
    }


def normalize_snapshot(
    repository_name: str,
    repository_payload: dict[str, Any],
    target_sha: str,
    tree_payload: dict[str, Any],
    commit_payloads: list[dict[str, Any]],
    captured_at: str | None = None,
) -> SnapshotData:
    """Build a deterministic graph payload from validated GitHub responses."""

    captured_at = captured_at or _now()
    snapshot_id = f"{repository_name.replace('/', '-')}-{target_sha[:12]}"
    repo_id = f"github:{repository_name}"
    source_repo_url = _source_url(repository_name)

    repository = {
        "id": repo_id,
        "full_name": repository_payload.get("full_name", repository_name),
        "name": repository_payload.get("name", repository_name.rsplit("/", 1)[-1]),
        "description": repository_payload.get("description"),
        "default_branch": repository_payload.get("default_branch"),
        "html_url": repository_payload.get("html_url", source_repo_url),
        "provider": "github",
        "source_type": "github_rest",
        "source_url": source_repo_url,
        "observed_at": captured_at,
    }
    snapshot = {
        "id": snapshot_id,
        "repository_id": repo_id,
        "commit_sha": target_sha,
        "tree_sha": tree_payload.get("sha", target_sha),
        "status": "building",
        "captured_at": captured_at,
        "source_type": "github_rest",
        "source_url": f"{source_repo_url}/tree/{target_sha}",
        "ingestion_version": "2",
    }

    file_records: dict[str, dict[str, Any]] = {}
    snapshot_files: list[dict[str, Any]] = []
    for entry in tree_payload.get("tree", []):
        if entry.get("type") != "blob" or not entry.get("path"):
            continue
        path = str(entry["path"])
        file_id = _file_id(repository_name, path)
        file_record = {
            "id": file_id,
            "repository_id": repo_id,
            "path": path,
            "extension": PurePosixPath(path).suffix.lower(),
            "kind": "blob",
            "source_url": f"{source_repo_url}/blob/{target_sha}/{path}",
        }
        file_records[file_id] = file_record
        snapshot_files.append(
            {
                "snapshot_id": snapshot_id,
                "file_id": file_id,
                "file_sha": entry.get("sha"),
                "size": entry.get("size"),
                "mode": entry.get("mode"),
                "source_url": file_record["source_url"],
            }
        )

    people: dict[str, dict[str, Any]] = {}
    commits: dict[str, dict[str, Any]] = {}
    changed_files: list[dict[str, Any]] = []
    authored_by: list[dict[str, Any]] = []
    committed_by: list[dict[str, Any]] = []
    parent_edges: list[dict[str, Any]] = []

    for payload in commit_payloads:
        sha = payload.get("sha")
        if not sha:
            continue
        commit_id = _commit_id(sha)
        commit_info = payload.get("commit") or {}
        author_info = commit_info.get("author") or {}
        committer_info = commit_info.get("committer") or {}
        commit_record = {
            "id": commit_id,
            "sha": sha,
            "message": commit_info.get("message", ""),
            "subject": str(commit_info.get("message", "")).splitlines()[0][:300],
            "authored_at": author_info.get("date"),
            "committed_at": committer_info.get("date"),
            "html_url": payload.get("html_url", f"{source_repo_url}/commit/{sha}"),
            "additions": (payload.get("stats") or {}).get("additions", 0),
            "deletions": (payload.get("stats") or {}).get("deletions", 0),
            "changed_files": len(payload.get("files") or []),
            "partial": False,
            "source_url": payload.get("html_url", f"{source_repo_url}/commit/{sha}"),
        }
        commits[commit_id] = commit_record

        author = _person_record(repository_name, payload.get("author"), author_info)
        committer = _person_record(repository_name, payload.get("committer"), committer_info)
        people[author["id"]] = author
        people[committer["id"]] = committer
        authored_by.append({"snapshot_id": snapshot_id, "commit_id": commit_id, "person_id": author["id"]})
        committed_by.append({"snapshot_id": snapshot_id, "commit_id": commit_id, "person_id": committer["id"]})

        for parent in payload.get("parents") or []:
            parent_sha = parent.get("sha")
            if not parent_sha:
                continue
            parent_id = _commit_id(parent_sha)
            commits.setdefault(
                parent_id,
                {
                    "id": parent_id,
                    "sha": parent_sha,
                    "message": None,
                    "subject": None,
                    "authored_at": None,
                    "committed_at": None,
                    "html_url": f"{source_repo_url}/commit/{parent_sha}",
                    "additions": None,
                    "deletions": None,
                    "changed_files": None,
                    "partial": True,
                    "source_url": f"{source_repo_url}/commit/{parent_sha}",
                },
            )
            parent_edges.append(
                {
                    "snapshot_id": snapshot_id,
                    "commit_id": commit_id,
                    "parent_id": parent_id,
                }
            )

        for changed in payload.get("files") or []:
            path = changed.get("filename")
            if not path:
                continue
            raw_patch = changed.get("patch")
            patch_available = isinstance(raw_patch, str) and bool(raw_patch)
            patch_char_count = len(raw_patch) if patch_available else 0
            patch_truncated = patch_available and patch_char_count > MAX_PATCH_CHARS
            patch = raw_patch[:MAX_PATCH_CHARS] if patch_available else None
            file_id = _file_id(repository_name, path)
            file_records.setdefault(
                file_id,
                {
                    "id": file_id,
                    "repository_id": repo_id,
                    "path": path,
                    "extension": PurePosixPath(path).suffix.lower(),
                    "kind": "blob",
                    "source_url": f"{source_repo_url}/blob/{target_sha}/{path}",
                },
            )
            changed_files.append(
                {
                    "snapshot_id": snapshot_id,
                    "commit_id": commit_id,
                    "file_id": file_id,
                    "status": changed.get("status"),
                    "additions": changed.get("additions", 0),
                    "deletions": changed.get("deletions", 0),
                    "previous_path": changed.get("previous_filename"),
                    "patch": patch,
                    "patch_available": patch_available,
                    "patch_truncated": patch_truncated,
                    "patch_char_count": patch_char_count,
                    "source_url": commit_record["source_url"],
                }
            )

    snapshot.update(
        {
            "file_count": len(snapshot_files),
            "commit_count": sum(1 for commit in commits.values() if not commit["partial"]),
        }
    )
    return SnapshotData(
        repository=repository,
        snapshot=snapshot,
        files=list(file_records.values()),
        commits=list(commits.values()),
        people=list(people.values()),
        snapshot_files=snapshot_files,
        changed_files=changed_files,
        authored_by=authored_by,
        committed_by=committed_by,
        parent_edges=parent_edges,
    )

