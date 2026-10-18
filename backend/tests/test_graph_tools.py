from types import SimpleNamespace

import pytest

from app.tools.graph_queries import GraphQueryTools


class FakeGraph:
    def __init__(self, responses):
        self.responses = iter(responses)
        self.queries = []

    def ro_query(self, query, parameters):
        self.queries.append((query, parameters))
        return next(self.responses)


def result(header, rows):
    return SimpleNamespace(header=header, result_set=rows)


def test_file_history_runs_snapshot_resolution_then_multi_hop_query() -> None:
    graph = FakeGraph(
        [
            result(["snapshot_id"], [["pallets-flask-d086db856be1"]]),
            result(
                ["file_path", "commit_sha", "commit_url", "file_url"],
                [["src/flask/app.py", "abc123", "https://commit", "https://file"]],
            ),
        ]
    )

    evidence = GraphQueryTools(graph=graph).file_history("app.py")

    assert evidence.snapshot_id == "pallets-flask-d086db856be1"
    assert evidence.rows == [
        {
            "file_path": "src/flask/app.py",
            "commit_sha": "abc123",
            "commit_url": "https://commit",
            "file_url": "https://file",
        }
    ]
    assert evidence.source_urls == ["https://commit", "https://file"]
    assert "CHANGED" in graph.queries[1][0]
    assert "AUTHORED_BY" in graph.queries[1][0]


def test_file_change_detail_returns_bounded_patch_evidence() -> None:
    graph = FakeGraph(
        [
            result(["snapshot_id"], [["snap"]]),
            result(
                [
                    "file_path", "commit_sha", "commit_subject", "patch", "patch_available",
                    "patch_truncated", "patch_char_count", "commit_url", "file_url",
                ],
                [[
                    "src/flask/app.py", "abc123", "Improve app startup", "@@ -1 +1 @@\n-old\n+new",
                    True, False, 19, "https://commit", "https://file",
                ]],
            ),
        ]
    )

    evidence = GraphQueryTools(graph=graph).file_change_detail("src/flask/app.py", limit=99)

    assert evidence.tool_name == "file_change_detail"
    assert evidence.parameters["limit"] == 20
    assert evidence.rows[0]["patch_available"] is True
    assert evidence.source_urls == ["https://commit", "https://file"]
    assert "ch.patch AS patch" in graph.queries[1][0]
    prompt = evidence.to_prompt_context()
    assert "stored patch omitted from model prompt" in prompt
    assert "-old" not in prompt


def test_tools_bound_limits_and_reject_empty_inputs() -> None:
    graph = FakeGraph([result(["snapshot_id"], [["snap"]]), result([], [])])
    tools = GraphQueryTools(graph=graph)

    evidence = tools.file_contributors("app.py", limit=999)
    assert evidence.parameters["limit"] == 100

    with pytest.raises(ValueError):
        tools.file_history("  ")


def test_nested_falkordb_headers_become_column_names_and_source_urls() -> None:
    graph = FakeGraph(
        [
            result([[1, "snapshot_id"]], [["snap"]]),
            result(
                [[1, "file_path"], [1, "file_url"]],
                [["src/flask/app.py", "https://github.com/file"]],
            ),
        ]
    )

    evidence = GraphQueryTools(graph=graph).file_history("app.py")

    assert evidence.columns == ["file_path", "file_url"]
    assert evidence.rows == [
        {"file_path": "src/flask/app.py", "file_url": "https://github.com/file"}
    ]
    assert evidence.source_urls == ["https://github.com/file"]


def test_file_contributors_aggregates_each_contributor_across_matching_files() -> None:
    graph = FakeGraph(
        [
            result(["snapshot_id"], [["snap"]]),
            result(
                ["contributor", "commit_count", "file_paths", "file_urls"],
                [[
                    "davidism",
                    6,
                    ["src/flask/app.py", "src/flask/sansio/app.py"],
                    ["https://github.com/file-one", "https://github.com/file-two"],
                ]],
            ),
            result(
                [
                    "file_path", "commit_sha", "commit_subject", "commit_message", "authored_at",
                    "contributor", "display_name", "change_status", "additions", "deletions",
                    "commit_url", "file_url",
                ],
                [[
                    "src/flask/app.py", "abc123", "Improve app startup", "Improve app startup\n\nDetails",
                    "2026-10-07T14:01:40Z", "davidism", "David Lord", "modified", 42, 18,
                    "https://github.com/commit", "https://github.com/file-one",
                ]],
            ),
        ]
    )

    evidence = GraphQueryTools(graph=graph).file_contributors("app.py")

    assert evidence.rows[0]["contributor"] == "davidism"
    assert evidence.rows[0]["commit_count"] == 6
    assert evidence.rows[0]["file_paths"] == ["src/flask/app.py", "src/flask/sansio/app.py"]
    assert evidence.source_urls == [
        "https://github.com/file-one",
        "https://github.com/file-two",
        "https://github.com/commit",
    ]
    assert evidence.derived_results[0]["commit_subject"] == "Improve app startup"
    assert evidence.derived_results[0]["additions"] == 42
    assert evidence.derived_results[0]["deletions"] == 18
    assert "supporting_change_rows" in evidence.to_prompt_context()
    assert "collect(DISTINCT f.path)" in graph.queries[1][0]
    assert "commit_subject" in graph.queries[2][0]


def test_impact_analysis_returns_derived_evidence_and_bounds_hops() -> None:
    graph = FakeGraph(
        [
            result(["snapshot_id"], [["snap"]]),
            result(
                ["affected_file", "hop_distance", "witness_path", "edge_types", "affected_file_url", "target_file_url"],
                [["tests/test_app.py", 2, ["tests/test_app.py", "src/pkg/app.py"], ["python_import"], "https://affected", "https://target"]],
            ),
        ]
    )

    evidence = GraphQueryTools(graph=graph).impact_analysis("src/pkg/app.py", max_hops=2)

    assert evidence.result_type == "derived"
    assert evidence.rows[0]["hop_distance"] == 2
    assert evidence.source_urls == ["https://affected", "https://target"]
    assert "DEPENDS_ON*1..2" in graph.queries[1][0]


def test_suggest_reviewers_scores_coverage_recency_and_activity() -> None:
    graph = FakeGraph(
        [
            result(["snapshot_id"], [["snap"]]),
            result(
                [
                    "contributor", "display_name", "covered_files", "commit_count",
                    "file_paths", "commit_shas", "commit_urls", "file_urls",
                    "last_authored_at", "snapshot_captured_at",
                ],
                [[
                    "davidism", "David Lord", 2, 6,
                    ["src/flask/app.py", "src/flask/sansio/app.py"],
                    ["a", "b"], ["https://commit"], ["https://file"],
                    "2026-10-07T14:01:40Z", "2026-10-17T10:02:29Z",
                ]],
            ),
            result([], []),
        ]
    )

    evidence = GraphQueryTools(graph=graph).suggest_reviewers(
        ["src/flask/app.py", "src/flask/sansio/app.py"],
    )

    row = evidence.rows[0]
    assert evidence.result_type == "derived"
    assert row["coverage_score"] == 1.0
    assert row["activity_score"] == 0.6
    assert row["final_score"] > 0.5
    assert evidence.parameters["file_paths"] == ["src/flask/app.py", "src/flask/sansio/app.py"]


def test_suggest_reviewers_merges_verified_review_history() -> None:
    graph = FakeGraph(
        [
            result(["snapshot_id"], [["snap"]]),
            result([], []),
            result(
                [
                    "contributor", "display_name", "review_count", "approval_review_ids",
                    "changes_requested_review_ids", "reviewed_file_paths", "review_urls",
                    "last_reviewed_at", "snapshot_captured_at",
                ],
                [[
                    "reviewer", "Review Person", 2, ["review-1"], [],
                    ["src/flask/app.py"], ["https://review"],
                    "2026-10-15T10:00:00Z", "2026-10-17T10:02:29Z",
                ]],
            ),
        ]
    )

    evidence = GraphQueryTools(graph=graph).suggest_reviewers(["src/flask/app.py"])

    row = evidence.rows[0]
    assert row["contributor"] == "reviewer"
    assert row["review_count"] == 2
    assert row["approval_count"] == 1
    assert row["reviewed_file_paths"] == ["src/flask/app.py"]
    assert row["review_overlap_score"] == 1.0
    assert evidence.source_urls == ["https://review"]


def test_trace_decision_returns_source_evidence_and_warnings() -> None:
    graph = FakeGraph(
        [
            result(["snapshot_id"], [["snap"]]),
            result(
                [
                    "decision_id", "topic", "source_title", "statement", "status", "confidence",
                    "extraction_method", "source_type", "source_id", "source_url",
                    "evidence_excerpts", "evidence_urls", "superseded_statements",
                ],
                [[
                    "decision-1", "request handling", "PR #1",
                    "We decided to use the new request handling path.", "adopted", 0.9,
                    "explicit_cue_phrase", "pull_request", "github:pull:repo:1", "https://source",
                    ["We decided to use the new request handling path."], ["https://source"], [],
                ]],
            ),
        ]
    )

    evidence = GraphQueryTools(graph=graph).trace_decision("request handling")

    assert evidence.tool_name == "trace_decision"
    assert evidence.result_type == "derived"
    assert evidence.rows[0]["source_id"] == "github:pull:repo:1"
    assert evidence.source_urls == ["https://source"]
    assert evidence.warnings
    assert "CONTAINS_DECISION" in graph.queries[1][0]
