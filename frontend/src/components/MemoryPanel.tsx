import type { Evidence } from "../types";
import SourceLinks from "./SourceLinks";

export default function MemoryPanel({ evidence }: { evidence: Evidence }) {
  if (evidence.tool_name !== "recall_context") return null;

  const semanticAvailable = evidence.rows.some((row) => String(row.retrieval_method ?? "").includes("semantic"));

  return (
    <article className="panel memory-panel">
      <div className="panel-heading">
        <div>
          <span className="panel-kicker">PERSISTENT MEMORY</span>
          <h3>Findings recalled for this tenant</h3>
        </div>
        <span className="row-count">{semanticAvailable ? "semantic + graph" : "lexical fallback"}</span>
      </div>
      <p className="memory-warning">These are user-owned findings, not automatically verified current repository facts.</p>
      <div className="memory-list">
        {evidence.rows.length === 0 && <p className="muted">No saved findings matched this search. Try another topic, or save an answer from Explore first.</p>}
        {evidence.rows.map((row, index) => (
          <div className="memory-row" key={`${String(row.finding_id)}-${index}`}>
            <div className="memory-row-meta">
              <code>{String(row.finding_id ?? "unknown")}</code>
              <span>{String(row.status ?? "active")} · v{String(row.version ?? "?")}{row.stale ? " · stale" : ""}</span>
            </div>
            <p>{String(row.text ?? "No finding text returned")}</p>
            <div className="memory-signals">
              <span className={String(row.retrieval_method ?? "").includes("semantic") ? "memory-method semantic" : "memory-method"}>
                {String(row.retrieval_method ?? "saved finding")}
              </span>
              {typeof row.semantic_score === "number" && <span>similarity {row.semantic_score.toFixed(2)}</span>}
              <span>snapshot: {String(row.snapshot_id ?? "unspecified")}</span>
            </div>
            {Array.isArray(row.linked_entities) && row.linked_entities.length > 0 && (
              <div className="memory-entities" aria-label="Linked repository entities">
                {row.linked_entities.map((entity) => <code key={String(entity)}>{String(entity)}</code>)}
              </div>
            )}
            {Array.isArray(row.source_urls) && <SourceLinks urls={row.source_urls}/>}
          </div>
        ))}
      </div>
    </article>
  );
}
