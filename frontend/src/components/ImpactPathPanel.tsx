import type { Evidence } from "../types";

function pathLabel(value: unknown): string {
  if (!Array.isArray(value)) return String(value ?? "");
  return value.map((item) => String(item)).join("  →  ");
}

export default function ImpactPathPanel({ evidence }: { evidence: Evidence }) {
  if (evidence.tool_name !== "impact_analysis") return null;

  return (
    <article className="panel impact-panel">
      <div className="panel-heading">
        <div>
          <span className="panel-kicker">DERIVED IMPACT PATHS</span>
          <h3>Static dependency witnesses</h3>
        </div>
        <span className="row-count">{evidence.rows.length} affected files</span>
      </div>
      <p className="impact-warning">
        These paths come from statically extracted Python imports. Runtime and dynamic imports are not verified.
      </p>
      <div className="impact-list">
        {evidence.rows.map((row, index) => (
          <div className="impact-row" key={`${String(row.affected_file)}-${index}`}>
            <div className="impact-file">{String(row.affected_file ?? "Unknown file")}</div>
            <span className="hop-badge">{String(row.hop_distance ?? "?")} hop{row.hop_distance === 1 ? "" : "s"}</span>
            <div className="impact-path"><span className="trace-label">WITNESS PATH</span>{pathLabel(row.witness_path)}</div>
          </div>
        ))}
      </div>
    </article>
  );
}
