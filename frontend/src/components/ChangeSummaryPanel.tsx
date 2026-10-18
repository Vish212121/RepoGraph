import type { Evidence } from "../types";
import { safeSource } from "../lib/sources";

function text(value: unknown, fallback = "—"): string {
  if (value === null || value === undefined || value === "") return fallback;
  return String(value);
}

function number(value: unknown): number {
  return typeof value === "number" ? value : Number(value ?? 0);
}

function date(value: unknown): string {
  if (!value) return "Date unavailable";
  const parsed = new Date(String(value));
  return Number.isNaN(parsed.getTime())
    ? String(value)
    : parsed.toLocaleDateString(undefined, { year: "numeric", month: "short", day: "numeric" });
}

export default function ChangeSummaryPanel({ evidence }: { evidence: Evidence }) {
  const changes = evidence.tool_name === "file_contributors" ? evidence.derived_results : evidence.rows;
  if (!["file_contributors", "file_history", "contributor_changes", "commit_impact"].includes(evidence.tool_name)) {
    return null;
  }

  return (
    <article className="panel change-panel">
      <div className="panel-heading change-heading">
        <div>
          <span className="panel-kicker">CHANGE DETAIL</span>
          <h3>What changed in the matching files</h3>
        </div>
        <span className="row-count">{changes.length} change records</span>
      </div>
      <p className="change-intro">
        Commit subjects and line statistics come directly from the repository graph. Ask what changed in a
        specific file to inspect any captured line-level patch evidence.
      </p>
      <div className="change-list">
        {changes.length === 0 && <p className="muted">No change records returned for this query.</p>}
        {changes.map((change, index) => {
          const additions = number(change.additions);
          const deletions = number(change.deletions);
          const message = text(change.commit_message, "");
          const subject = text(change.commit_subject, message.split("\n")[0] || "Change summary unavailable");
          const commitUrl = safeSource(change.commit_url);

          return (
            <article className="change-row" key={`${text(change.commit_sha, "change")}-${index}`}>
              <div className="change-row-topline">
                <div className="change-file-block">
                  <code className="change-file">{text(change.file_path)}</code>
                  <span className="change-commit">{text(change.commit_sha, "commit").slice(0, 10)}</span>
                </div>
                <span className="change-date">{date(change.authored_at)}</span>
              </div>
              <div className="change-row-main">
                <div>
                  <h4>{subject}</h4>
                  <p className="change-author">
                    {text(change.display_name, text(change.contributor))}
                    <span> · </span>
                    <span className="change-status">{text(change.change_status, "modified")}</span>
                  </p>
                </div>
                <div className="change-stats" aria-label="Line changes">
                  <span className="additions">+{additions}</span>
                  <span className="deletions">−{deletions}</span>
                </div>
              </div>
              {message && message !== subject && (
                <details className="change-message">
                  <summary>Show commit message</summary>
                  <p>{message}</p>
                </details>
              )}
              {commitUrl && (
                <a className="change-link" href={commitUrl} target="_blank" rel="noreferrer">
                  Open commit evidence ↗
                </a>
              )}
            </article>
          );
        })}
      </div>
    </article>
  );
}
