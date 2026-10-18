from app.evidence.models import EvidenceBundle
from app.mcp.gateway import DirectToolGateway, MCPToolGateway


class FakeTools:
    def file_contributors(self, **kwargs):
        return EvidenceBundle(
            tool_name="file_contributors",
            query="MATCH ...",
            parameters=kwargs,
            columns=["contributor"],
            rows=[{"contributor": "davidism"}],
            snapshot_id="snap-1",
        )

    def file_change_detail(self, **kwargs):
        return EvidenceBundle(
            tool_name="file_change_detail",
            query="MATCH ...",
            parameters=kwargs,
            columns=["file_path", "patch_available"],
            rows=[{"file_path": "src/flask/app.py", "patch_available": True}],
            snapshot_id="snap-1",
        )


class FakeMCPClient:
    def call_tool(self, name, arguments):
        return EvidenceBundle(
            tool_name="file_contributors",
            query="MATCH ...",
            parameters=arguments,
            columns=["contributor"],
            rows=[{"contributor": "davidism"}],
            snapshot_id="snap-1",
        )


def test_direct_gateway_records_explicit_trace():
    evidence, trace = DirectToolGateway(FakeTools()).invoke(
        "file_contributors", {"path_fragment": "app.py", "snapshot_id": "snap-1"}
    )
    assert evidence.rows[0]["contributor"] == "davidism"
    assert trace.execution_mode == "direct"
    assert trace.tool_name == "repobrain_file_contributors"
    assert trace.result_rows == 1


def test_mcp_gateway_maps_intent_to_stable_tool_name():
    evidence, trace = MCPToolGateway(FakeMCPClient()).invoke(
        "file_contributors", {"path_fragment": "app.py"}
    )
    assert evidence.has_evidence
    assert trace.execution_mode == "mcp"
    assert trace.tool_name == "repobrain_file_contributors"


def test_direct_gateway_supports_line_level_change_detail():
    evidence, trace = DirectToolGateway(FakeTools()).invoke(
        "file_change_detail", {"path_fragment": "src/flask/app.py", "snapshot_id": "snap-1"}
    )
    assert evidence.rows[0]["patch_available"] is True
    assert trace.tool_name == "repobrain_file_change_detail"
