"""Internal models shared by the GitHub client, normalizer, and graph loader."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class SnapshotData:
    """A normalized, self-contained repository snapshot ready for loading."""

    repository: dict[str, Any]
    snapshot: dict[str, Any]
    files: list[dict[str, Any]] = field(default_factory=list)
    commits: list[dict[str, Any]] = field(default_factory=list)
    people: list[dict[str, Any]] = field(default_factory=list)
    snapshot_files: list[dict[str, Any]] = field(default_factory=list)
    changed_files: list[dict[str, Any]] = field(default_factory=list)
    authored_by: list[dict[str, Any]] = field(default_factory=list)
    committed_by: list[dict[str, Any]] = field(default_factory=list)
    parent_edges: list[dict[str, Any]] = field(default_factory=list)
    pull_requests: list[dict[str, Any]] = field(default_factory=list)
    pull_request_files: list[dict[str, Any]] = field(default_factory=list)
    reviews: list[dict[str, Any]] = field(default_factory=list)
    pull_request_authors: list[dict[str, Any]] = field(default_factory=list)
    review_people: list[dict[str, Any]] = field(default_factory=list)

    @property
    def counts(self) -> dict[str, int]:
        """Return useful counts for logs, manifests, and API responses."""

        return {
            "files": len(self.files),
            "commits": len(self.commits),
            "people": len(self.people),
            "snapshot_files": len(self.snapshot_files),
            "changed_files": len(self.changed_files),
            "authored_by": len(self.authored_by),
            "committed_by": len(self.committed_by),
            "parent_edges": len(self.parent_edges),
            "pull_requests": len(self.pull_requests),
            "pull_request_files": len(self.pull_request_files),
            "reviews": len(self.reviews),
            "pull_request_authors": len(self.pull_request_authors),
            "review_people": len(self.review_people),
        }

