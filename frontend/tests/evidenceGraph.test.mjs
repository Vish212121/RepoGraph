import assert from "node:assert/strict";
import test from "node:test";
import { buildEvidenceGraph, getRecord } from "../src/lib/evidenceGraph.ts";

const bundle = (tool_name, rows = [], derived_results = [], parameters = {}) => ({
  tool_name, rows, derived_results, parameters, snapshot_id: "snap-a", source_urls: [],
});

test("maps only explicit commit records and preserves source references", () => {
  const evidence = bundle("file_history", [{
    commit_sha: "abc123456789", file_path: "src/app.py", contributor: "dev", file_url: "https://github.com/org/repo/blob/abc/src/app.py",
  }]);
  const graph = buildEvidenceGraph(evidence, "tenant-a");
  assert.equal(graph.nodes.length, 3);
  assert.equal(graph.links.length, 2);
  assert.ok(graph.links.some(link => link.relation === "CHANGED"));
  assert.ok(graph.links.some(link => link.relation === "AUTHORED_BY"));
  const file = graph.nodes.find(node => node.kind === "file");
  assert.deepEqual(file.sources, ["https://github.com/org/repo/blob/abc/src/app.py"]);
  assert.deepEqual(getRecord(evidence, file.refs[0]), evidence.rows[0]);
});

test("uses contributor detail rows; aggregated totals alone do not invent commits", () => {
  const empty = buildEvidenceGraph(bundle("file_contributors", [{ contributor: "dev", commit_count: 9 }]), "tenant-a");
  assert.equal(empty.nodes.length, 0);
  assert.ok(empty.notices.some(message => message.includes("bounded detail sample")));
  const evidence = bundle("file_contributors", [], [{ commit_sha: "sha1", file_path: "src/app.py", contributor: "dev" }]);
  const graph = buildEvidenceGraph(evidence, "tenant-a");
  assert.equal(graph.links.length, 2);
  assert.equal(graph.links[0].refs[0].collection, "derived_results");
});

test("retains dependency witness direction and rejects malformed paths", () => {
  const evidence = bundle("impact_analysis", [
    { affected_file: "src/child.py", hop_distance: 2, witness_path: ["src/child.py", "src/mid.py", "src/base.py"], edge_types: ["python_import", "python_import"] },
    { affected_file: "src/other.py", hop_distance: 2, witness_path: ["src/other.py", "src/base.py"], edge_types: ["python_import"] },
  ], [], { file_path: "src/base.py" });
  const graph = buildEvidenceGraph(evidence, "tenant-a");
  assert.deepEqual(graph.links.map(link => [graph.nodes.find(node => node.id === link.source).value, graph.nodes.find(node => node.id === link.target).value]), [
    ["src/child.py", "src/mid.py"], ["src/mid.py", "src/base.py"],
  ]);
  assert.equal(graph.omittedRows, 1);
  assert.ok(graph.notices.some(message => message.toLowerCase().includes("static python import")));
});

test("keeps tenant and snapshot identities separate and reports graph bounds", () => {
  const evidence = bundle("file_history", [
    { commit_sha: "sha1", file_path: "src/a.py" }, { commit_sha: "sha2", file_path: "src/b.py" },
  ]);
  const alpha = buildEvidenceGraph(evidence, "alpha", 2, 1);
  const beta = buildEvidenceGraph(evidence, "beta");
  assert.notEqual(alpha.nodes[0].id, beta.nodes[0].id);
  assert.equal(alpha.nodes.length, 2);
  assert.equal(alpha.links.length, 1);
  assert.ok(alpha.notices.some(message => message.includes("Map limited")));
});

test("does not accept unsafe URL schemes", () => {
  const graph = buildEvidenceGraph(bundle("file_history", [{ commit_sha: "sha1", file_path: "src/a.py", file_url: "javascript:alert(1)" }]), "tenant-a");
  assert.deepEqual(graph.nodes.find(node => node.kind === "file").sources, []);
});
