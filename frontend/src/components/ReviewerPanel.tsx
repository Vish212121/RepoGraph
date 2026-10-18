import type { Evidence } from "../types";

export default function ReviewerPanel({ evidence }: { evidence: Evidence }) {
  if (evidence.tool_name !== "suggest_reviewers") return null;

  return (
    <article className="panel reviewer-panel">
      <div className="panel-heading">
        <div>
          <span className="panel-kicker">REVIEWER SIGNAL</span>
          <h3>People connected to these files</h3>
        </div>
        <span className="row-count">{evidence.rows.length} suggestions</span>
      </div>
      <p className="reviewer-warning">
        Ranked from file-change familiarity and verified pull-request review activity when available.
        Scores remain evidence-based signals, not a claim of maintainer status.
      </p>
      <div className="reviewer-list">
        {evidence.rows.map((row, index) => (
          <div className="reviewer-row" key={`${String(row.contributor)}-${index}`}>
            <div className="reviewer-rank">0{index + 1}</div>
            <div className="reviewer-main">
              <div className="reviewer-name">{String(row.display_name ?? row.contributor)}</div>
              <code>{String(row.contributor ?? "unknown")}</code>
              <div className="reviewer-files">
                {((row.file_paths ?? row.reviewed_file_paths) as string[] | undefined)?.join(" · ")}
              </div>
            </div>
            <div className="reviewer-score">
              <strong>{String(row.final_score ?? "—")}</strong>
              <span>score</span>
            </div>
            <div className="reviewer-meta">
              <span>{String(row.covered_files ?? 0)}/{String(row.requested_file_count ?? 0)} files</span>
              <span>{String(row.commit_count ?? 0)} commits</span>
              <span>{String(row.review_count ?? 0)} reviews</span>
              <span>{String(row.approval_count ?? 0)} approvals</span>
            </div>
          </div>
        ))}
      </div>
    </article>
  );
}
