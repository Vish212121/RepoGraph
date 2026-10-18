from app.ingestion.normalizer import normalize_snapshot


def test_normalize_snapshot_builds_stable_entities_and_relationships() -> None:
    data = normalize_snapshot(
        repository_name="pallets/flask",
        repository_payload={
            "full_name": "pallets/flask",
            "name": "flask",
            "default_branch": "main",
            "html_url": "https://github.com/pallets/flask",
        },
        target_sha="a" * 40,
        tree_payload={
            "sha": "tree-sha",
            "truncated": False,
            "tree": [
                {
                    "path": "src/flask/app.py",
                    "mode": "100644",
                    "type": "blob",
                    "size": 120,
                    "sha": "blob-sha",
                }
            ],
        },
        commit_payloads=[
            {
                "sha": "a" * 40,
                "html_url": "https://github.com/pallets/flask/commit/" + "a" * 40,
                "author": {"login": "alice"},
                "committer": {"login": "alice"},
                "parents": [{"sha": "b" * 40}],
                "commit": {
                    "message": "Improve app startup\n\nDetails",
                    "author": {"name": "Alice", "email": "alice@example.com", "date": "2026-01-01T00:00:00Z"},
                    "committer": {"name": "Alice", "email": "alice@example.com", "date": "2026-01-01T00:00:00Z"},
                    "tree": {"sha": "tree-sha"},
                },
                "stats": {"additions": 4, "deletions": 2},
                "files": [
                    {
                        "filename": "src/flask/app.py",
                        "status": "modified",
                        "additions": 4,
                        "deletions": 2,
                        "patch": "@@ -1 +1 @@\n-old startup\n+new startup",
                    }
                ],
            }
        ],
        captured_at="2026-01-01T00:00:00Z",
    )

    assert data.snapshot["id"] == "pallets-flask-aaaaaaaaaaaa"
    assert data.snapshot["status"] == "building"
    assert data.snapshot["file_count"] == 1
    assert len(data.files) == 1
    assert len(data.commits) == 2
    assert data.commits[1]["partial"] is True
    assert data.people[0]["id"] == "github:user:alice"
    assert data.changed_files[0]["status"] == "modified"
    assert data.changed_files[0]["patch"] == "@@ -1 +1 @@\n-old startup\n+new startup"
    assert data.changed_files[0]["patch_available"] is True
    assert data.changed_files[0]["patch_truncated"] is False
    assert data.changed_files[0]["patch_char_count"] == len("@@ -1 +1 @@\n-old startup\n+new startup")
    assert data.parent_edges[0]["parent_id"] == "github:commit:" + "b" * 40

