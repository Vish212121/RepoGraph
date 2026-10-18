import type { Evidence, EvidenceRow } from "../types";
import type { EntityKind, EvidenceGraph, EvidenceRef, GraphLink, GraphNode } from "../types/graph";
import { safeSource } from "./sources.ts";

const text = (value: unknown): string => typeof value === "string" ? value.trim() : "";
const commitTools = new Set(["file_history", "file_change_detail", "commit_impact", "contributor_changes"]);
const refKey = (ref: EvidenceRef) => `${ref.collection}:${ref.index}`;

export function getRecord(evidence: Evidence, ref: EvidenceRef): EvidenceRow | undefined {
  return evidence[ref.collection]?.[ref.index];
}

/** Interpret only known tool contracts, never answer prose or aggregated cross-products. */
export function buildEvidenceGraph(evidence: Evidence | null, scope: string, maxNodes = 100, maxLinks = 180): EvidenceGraph {
  const nodes = new Map<string, GraphNode>();
  const links = new Map<string, GraphLink>();
  const notices = new Set<string>();
  let omittedRows = 0;
  const attach = (refs: EvidenceRef[], ref: EvidenceRef) => {
    if (!refs.some(item => refKey(item) === refKey(ref))) refs.push(ref);
  };
  const addNode = (kind: EntityKind, value: string, ref: EvidenceRef, source?: unknown): string => {
    const id = JSON.stringify([scope, evidence?.snapshot_id ?? null, kind, value]);
    let node = nodes.get(id);
    if (!node) {
      node = { id, kind, value, label: kind === "file" ? value.split("/").pop() || value : kind === "commit" ? value.slice(0, 8) : value, sources: [], refs: [] };
      nodes.set(id, node);
    }
    attach(node.refs, ref);
    const url = safeSource(source);
    if (url && !node.sources.includes(url)) node.sources.push(url);
    return id;
  };
  const addLink = (source: string, target: string, relation: GraphLink["relation"], ref: EvidenceRef) => {
    const id = JSON.stringify([source, relation, target]);
    let link = links.get(id);
    if (!link) {
      link = { id, source, target, relation, basis: relation === "DEPENDS_ON" ? "static import" : "repository record", refs: [] };
      links.set(id, link);
    }
    attach(link.refs, ref);
  };
  if (evidence) {
    const collection = evidence.tool_name === "file_contributors" ? "derived_results" : "rows";
    const supported = commitTools.has(evidence.tool_name) || evidence.tool_name === "file_contributors";
    if (supported) {
      for (const [index, row] of (evidence[collection] ?? []).entries()) {
        const sha = text(row.commit_sha), file = text(row.file_path), person = text(row.contributor);
        if (!sha || !file) { omittedRows++; continue; }
        const ref: EvidenceRef = { collection, index };
        const commit = addNode("commit", sha, ref, row.commit_url);
        addLink(commit, addNode("file", file, ref, row.file_url), "CHANGED", ref);
        if (person) addLink(commit, addNode("person", person, ref), "AUTHORED_BY", ref);
      }
      if (evidence.tool_name === "file_contributors") notices.add("The map uses the returned commit detail records. Contributor totals may cover more commits than this bounded detail sample.");
    } else if (evidence.tool_name === "impact_analysis") {
      notices.add("Static Python import paths only. These connections do not verify runtime behavior or dynamic imports.");
      for (const [index, row] of evidence.rows.entries()) {
        const path = row.witness_path, types = row.edge_types;
        // Reject a malformed path as a whole: never bridge missing intermediate nodes.
        if (!Array.isArray(path) || path.length < 2 || !path.every(item => typeof item === "string" && item.trim()) ||
            !Array.isArray(types) || types.length !== path.length - 1 || !types.every(item => item === "python_import") ||
            row.hop_distance !== path.length - 1 || text(row.affected_file) !== path[0] ||
            (text(evidence.parameters.file_path) && path[path.length - 1] !== evidence.parameters.file_path)) {
          omittedRows++; continue;
        }
        const ref: EvidenceRef = { collection: "rows", index };
        const ids = path.map((value, i) => addNode("file", value, ref, i === 0 ? row.affected_file_url : i === path.length - 1 ? row.target_file_url : undefined));
        for (let i = 0; i < ids.length - 1; i++) addLink(ids[i], ids[i + 1], "DEPENDS_ON", ref);
      }
    } else notices.add("This result does not expose supported entity-level relationships. Its answer and evidence remain available in the other views.");
  }
  if (omittedRows) notices.add(`${omittedRows} incomplete or unsupported evidence record(s) could not be mapped. Inspect them in Evidence.`);
  // Keep complete link endpoints. All records remain available outside the bounded canvas.
  const displayed = new Set<string>();
  const visibleLinks: GraphLink[] = [];
  for (const link of links.values()) {
    const required = [link.source, link.target].filter(id => !displayed.has(id));
    if (displayed.size + required.length > Math.max(0, maxNodes) || visibleLinks.length >= Math.max(0, maxLinks)) continue;
    required.forEach(id => displayed.add(id));
    visibleLinks.push(link);
  }
  if (displayed.size < nodes.size || visibleLinks.length < links.size) notices.add(`Map limited to ${displayed.size} of ${nodes.size} entities and ${visibleLinks.length} of ${links.size} relationships. All returned records remain in Evidence.`);
  return { nodes: [...nodes.values()].filter(node => displayed.has(node.id)), links: visibleLinks, totalNodes: nodes.size, totalLinks: links.size, omittedRows, notices: [...notices] };
}
