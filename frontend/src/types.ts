export type EvidenceRow = Record<string, unknown>;

export interface Evidence {
  tool_name: string;
  query: string;
  parameters: Record<string, unknown>;
  columns: string[];
  rows: EvidenceRow[];
  snapshot_id: string | null;
  source_urls: string[];
  snapshot_selector_query: string | null;
  result_type: string;
  warnings: string[];
  derived_results: Record<string, unknown>[];
}

export interface QueryResponse {
  question: string;
  intent: string;
  answer: string;
  evidence: Evidence | null;
  model: string | null;
  used_fallback: boolean;
  limitation: string | null;
  execution_mode: string | null;
  tool_calls: ToolCall[];
  session_id: string | null;
}

export interface Finding {
  finding_id: string;
  text: string;
  status: string;
  version: number;
  snapshot_id: string | null;
  created_at: string;
  updated_at: string;
  references: Record<string, unknown>[];
  source_urls: string[];
  session_id: string | null;
  embedding_status: string;
}

export interface ToolCall {
  execution_mode: "mcp" | "direct";
  tool_name: string;
  arguments: Record<string, unknown>;
  result_rows: number;
}

export interface Snapshot {
  repository: string | null;
  repository_url: string | null;
  snapshot_id: string;
  commit_sha: string | null;
  captured_at: string | null;
  file_count: number | null;
  commit_count: number | null;
  snapshot_url: string | null;
}
