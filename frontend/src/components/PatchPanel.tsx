import type { Evidence, EvidenceRow } from "../types";
import { safeSource } from "../lib/sources";

function text(value: unknown, fallback = "—"): string {
  if (value === null || value === undefined || value === "") return fallback;
  return String(value);
}

function date(value: unknown): string {
  if (!value) return "Date unavailable";
  const parsed = new Date(String(value));
  return Number.isNaN(parsed.getTime())
    ? String(value)
    : parsed.toLocaleDateString(undefined, { year: "numeric", month: "short", day: "numeric" });
}

function PatchLines({ patch }: { patch: string }) {
  return (
    <pre className="patch-code" aria-label="Unified diff patch">
      {patch.split("\n").map((line, index) => {
        const className = line.startsWith("+++") || line.startsWith("---")
          ? "patch-file"
          : line.startsWith("+")
            ? "patch-add"
            : line.startsWith("-")
              ? "patch-remove"
              : line.startsWith("@@")
                ? "patch-hunk"
                : "patch-context";
        return <span className={className} key={`${index}-${line}`}>{line || " "}{"\n"}</span>;
      })}
    </pre>
  );
}

function PatchRecord({ row, index }: { row: EvidenceRow; index: number }) {
  const patch = typeof row.patch === "string" ? row.patch : "";
  const commitUrl = safeSource(row.commit_url);
  const patchAvailable = Boolean(row.patch_available && patch);
  const patchTruncated = Boolean(row.patch_truncated);
  const previousPath = typeof row.previous_path === "string" ? row.previous_path : "";
  const title = text(row.commit_subject, text(row.commit_message, "Change summary unavailable").split("\n")[0]);

  return (
    <article className="patch-record">
      <div className="patch-record-head">
        <div>
          <code className="patch-path">{text(row.file_path)}</code>
          {previousPath && <span className="patch-rename">renamed from {previousPath}</span>}
        </div>
        <span className={patchAvailable ? "patch-status available" : "patch-status unavailable"}>
          {patchAvailable ? "Patch available" : "Patch unavailable"}
        </span>
      </div>
      <div className="patch-summary">
        <div>
          <h4>{title}</h4>
          <p>
            {text(row.display_name, text(row.contributor))} · {date(row.authored_at)} · {text(row.change_status, "modified")}
          </p>
        </div>
        <div className="change-stats" aria-label="Line changes">
          <span className="additions">+{text(row.additions, "0")}</span>
          <span className="deletions">−{text(row.deletions, "0")}</span>
        </div>
      </div>
      {patchAvailable ? (
        <details className="patch-details" open={index === 0}>
          <summary>View unified diff</summary>
          {patchTruncated && (
            <p className="patch-notice">This patch is a bounded excerpt. Open the commit for the complete GitHub diff.</p>
          )}
          <PatchLines patch={patch} />
        </details>
      ) : (
        <p className="patch-notice">No inline patch was returned in this snapshot. Inspect the available metadata or open the commit source.</p>
      )}
      {commitUrl && <a className="change-link" href={commitUrl} target="_blank" rel="noreferrer">Open commit on GitHub ↗</a>}
    </article>
  );
}

export default function PatchPanel({ evidence }: { evidence: Evidence }) {
  if (evidence.tool_name !== "file_change_detail") return null;

  return (
    <article className="panel patch-panel">
      <div className="panel-heading patch-heading">
        <div>
          <span className="panel-kicker">LINE-LEVEL EVIDENCE</span>
          <h3>What changed in the file</h3>
        </div>
        <span className="row-count">{evidence.rows.length} changes</span>
      </div>
      <p className="patch-intro">These unified diffs were captured from GitHub during snapshot ingestion.</p>
      <div className="patch-list">
        {evidence.rows.length === 0 && <p className="muted">No changes matched this query in the selected snapshot.</p>}
        {evidence.rows.map((row, index) => <PatchRecord key={`${text(row.commit_sha)}-${index}`} row={row} index={index} />)}
      </div>
    </article>
  );
}
