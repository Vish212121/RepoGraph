import type { EvidenceRow } from "../types";

export type EntityKind = "file" | "commit" | "person";
export interface EvidenceRef {
  collection: "rows" | "derived_results";
  index: number;
}
export interface GraphNode {
  id: string;
  kind: EntityKind;
  label: string;
  value: string;
  sources: string[];
  refs: EvidenceRef[];
}
export interface GraphLink {
  id: string;
  source: string;
  target: string;
  relation: "CHANGED" | "AUTHORED_BY" | "DEPENDS_ON";
  basis: "repository record" | "static import";
  refs: EvidenceRef[];
}
export interface EvidenceGraph {
  nodes: GraphNode[];
  links: GraphLink[];
  totalNodes: number;
  totalLinks: number;
  omittedRows: number;
  notices: string[];
}
export type GraphSelection = { type: "node" | "link"; id: string } | null;
export interface EvidenceRecord { ref: EvidenceRef; row: EvidenceRow }
