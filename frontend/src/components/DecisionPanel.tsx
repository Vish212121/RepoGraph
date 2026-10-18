import type { Evidence } from "../types";
import { safeSource } from "../lib/sources";

function listValues(value: unknown): string[] {
  return Array.isArray(value) ? value.filter(Boolean).map(String) : [];
}

export default function DecisionPanel({ evidence }: { evidence: Evidence }) {
  if (evidence.tool_name !== "trace_decision") return null;

  return (
    <article className="panel decision-panel">
      <div className="panel-heading">
        <div>
          <span className="panel-kicker">DECISION TRACE</span>
          <h3>Evidence behind repository choices</h3>
        </div>
        <span className="row-count">{evidence.rows.length} candidates</span>
      </div>
      <p className="decision-warning">
        These are decision candidates extracted from explicit discussion language. Confidence describes the extraction signal,
        not organizational authority.
      </p>
      <div className="decision-list">
        {evidence.rows.map((row, index) => {
          const superseded = listValues(row.superseded_statements);
          const excerpts = listValues(row.evidence_excerpts);
          const sourceUrl = safeSource(row.source_url);
          return (
            <div className="decision-row" key={`${String(row.decision_id)}-${index}`}>
              <div className="decision-row-heading">
                <span className="decision-number">0{index + 1}</span>
                <span className="decision-status">{String(row.status ?? "candidate")}</span>
                <span className="decision-confidence">confidence {String(row.confidence ?? "—")}</span>
              </div>
              <p className="decision-statement">{String(row.statement ?? "No decision statement returned")}</p>
              <div className="decision-source">
                <span>{String(row.source_type ?? "source")} · {String(row.source_id ?? "unknown")}</span>
                {sourceUrl && (
                  <a href={sourceUrl} target="_blank" rel="noreferrer">Open source ↗</a>
                )}
              </div>
              {excerpts.length > 0 && (
                <div className="decision-evidence">
                  <span className="trace-label">SUPPORTING EXCERPT</span>
                  <p>{excerpts[0]}</p>
                </div>
              )}
              {superseded.length > 0 && (
                <div className="decision-superseded">
                  <span className="trace-label">EXPLICITLY SUPERSEDES</span>
                  <p>{superseded.join(" · ")}</p>
                </div>
              )}
            </div>
          );
        })}
      </div>
    </article>
  );
}
