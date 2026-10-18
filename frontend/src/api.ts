import type { Evidence, Finding, QueryResponse, Snapshot } from "./types";

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "http://127.0.0.1:8010";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...(init?.headers ?? {}),
    },
  });

  if (!response.ok) {
    let detail = `Request failed with status ${response.status}`;
    try {
      const payload = (await response.json()) as { detail?: string };
      detail = payload.detail ?? detail;
    } catch {
      // Keep the status-based message when the server did not return JSON.
    }
    throw new Error(detail);
  }

  return (await response.json()) as T;
}

function tenantHeaders(tenant: string): HeadersInit {
  return { "X-Demo-Tenant": tenant };
}

export function queryRepository(
  question: string,
  snapshotId: string | undefined,
  tenant: string,
  sessionId?: string | null,
  signal?: AbortSignal,
): Promise<QueryResponse> {
  return request<QueryResponse>("/api/query", {
    method: "POST",
    signal,
    headers: tenantHeaders(tenant),
    body: JSON.stringify({
      question,
      snapshot_id: snapshotId || null,
      session_id: sessionId || null,
    }),
  });
}

export function listSnapshots(signal?: AbortSignal): Promise<Snapshot[]> {
  return request<Snapshot[]>("/api/snapshots", { signal });
}

export function createFinding(
  tenant: string,
  payload: {
    text: string;
    references: Record<string, string>[];
    source_urls: string[];
    snapshot_id?: string | null;
    session_id?: string | null;
    idempotency_key?: string;
  },
  signal?: AbortSignal,
): Promise<Finding> {
  return request<Finding>("/api/findings", {
    method: "POST",
    signal,
    headers: tenantHeaders(tenant),
    body: JSON.stringify(payload),
  });
}

export function recallMemory(tenant: string, query: string, snapshotId?: string, signal?: AbortSignal): Promise<Evidence> {
  const params = new URLSearchParams({ q: query });
  if (snapshotId) params.set("snapshot_id", snapshotId);
  return request<Evidence>(`/api/memory?${params.toString()}`, { headers: tenantHeaders(tenant), signal });
}
