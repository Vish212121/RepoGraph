import type { Evidence } from "../types";
import SourceLinks from "./SourceLinks";

const preferred = ["contributor", "display_name", "commit_count", "file_path", "commit_sha", "commit_subject", "affected_file", "hop_distance", "statement", "text", "status", "authored_at", "final_score"];
function valueText(value: unknown): string {
  if (value == null || value === "") return "—";
  if (Array.isArray(value)) return value.map(valueText).join(" · ");
  if (typeof value === "object") return JSON.stringify(value);
  return String(value);
}
export default function EvidenceTable({ evidence, title = "What the graph returned" }: { evidence: Evidence; title?: string }) {
  const columns = [...preferred.filter(key => evidence.columns.includes(key)), ...evidence.columns.filter(key => !preferred.includes(key) && !/(url|patch|message)/.test(key))].slice(0, 5);
  return <article className="panel evidence-panel"><div className="panel-heading"><div><span className="panel-kicker">STRUCTURED EVIDENCE</span><h3>{title}</h3></div><span className="row-count">{evidence.rows.length} records</span></div>
    <p className="muted">Key fields are shown below. Expand a record to inspect every returned field.</p>
    {evidence.rows.length ? <div className="table-wrap" role="region" aria-label={title} tabIndex={0}><table><thead><tr>{columns.map(column => <th key={column} scope="col">{column.replace(/_/g, " ")}</th>)}<th scope="col">Full record</th></tr></thead><tbody>{evidence.rows.map((row, index) => <tr key={index}>{columns.map(column => <td key={column}><span className="cell-value" title={valueText(row[column])}>{valueText(row[column])}</span></td>)}<td><details className="record-detail"><summary>Record {index + 1}</summary><pre>{JSON.stringify(row, null, 2)}</pre><SourceLinks urls={Object.entries(row).filter(([key]) => /urls?$/.test(key)).flatMap(([, value]) => Array.isArray(value) ? value : [value])}/></details></td></tr>)}</tbody></table></div> : <p className="notice">No matching records were returned.</p>}
    {evidence.source_urls.length > 0 && <div className="source-strip"><span className="small-caps">RETURNED SOURCES</span><SourceLinks urls={evidence.source_urls}/></div>}
  </article>;
}
