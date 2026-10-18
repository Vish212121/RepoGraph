import type { QueryResponse } from "../types";
import Icon from "./Icon";
export default function ReasoningTrace({ result }: { result: QueryResponse }) {
  return <article className="panel trace-panel"><div className="panel-heading"><div><span className="panel-kicker">EXECUTION RECORD</span><h3>How this response was produced</h3></div><Icon name="code"/></div>
    <div className="trace-grid"><div><span className="trace-label">SELECTED INTENT</span><code>{result.intent}</code></div><div><span className="trace-label">RETURNED TOOL</span><code>{result.evidence?.tool_name ?? "None"}</code></div><div><span className="trace-label">GATEWAY</span><code>{result.execution_mode ?? "Not reported"}</code></div><div><span className="trace-label">RESULTS</span><code>{result.evidence?.rows.length ?? 0} evidence records</code></div></div>
    {result.tool_calls.length > 0 && <ol className="tool-timeline">{result.tool_calls.map((call, i) => <li key={i}><span className="timeline-number">{i + 1}</span><div><strong>{call.tool_name}</strong><p>{call.execution_mode} · {call.result_rows} rows</p><details><summary>Tool arguments</summary><pre>{JSON.stringify(call.arguments, null, 2)}</pre></details></div></li>)}</ol>}
    <p className="muted">This is the returned tool execution record, not the model’s private reasoning. Inspect Graph for supported relationships and Query details for Cypher.</p>
  </article>;
}
