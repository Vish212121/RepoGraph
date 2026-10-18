import type { Evidence } from "../../types";
import type { EvidenceGraph, GraphSelection } from "../../types/graph";
import { getRecord } from "../../lib/evidenceGraph";
import Icon from "../Icon";
import SourceLinks from "../SourceLinks";

export default function GraphInspector({ graph, evidence, selection, onSelect }: { graph: EvidenceGraph; evidence: Evidence; selection: GraphSelection; onSelect: (value: GraphSelection) => void }) {
  const node = selection?.type === "node" ? graph.nodes.find(item => item.id === selection.id) : undefined;
  const link = selection?.type === "link" ? graph.links.find(item => item.id === selection.id) : undefined;
  const entity = node ?? link;
  const related = node ? graph.links.filter(item => item.source === node.id || item.target === node.id) : [];
  const names = new Map(graph.nodes.map(item => [item.id, item]));
  const sources = node?.sources ?? (link ? [names.get(link.source), names.get(link.target)].flatMap(item => item?.sources ?? []) : []);
  return <aside className="graph-inspector" aria-label="Selection details">
    <div className="inspector-heading"><span className="small-caps">INSPECTOR</span>{selection && <button className="icon-button" aria-label="Clear selection" onClick={() => onSelect(null)}><Icon name="close" size={15}/></button>}</div>
    {!entity ? <div className="inspector-empty"><span className="inspector-symbol"><Icon name="focus" size={28}/></span><h3>Every connection<br/>has a story.</h3><p>Select an entity or a relationship to see the records behind it.</p><div className="inspector-tip"><Icon name="list" size={16}/>Use List view for keyboard navigation.</div></div> : <div className="inspector-content" key={entity.id}>
      <div className="entity-type"><Icon name={node?.kind ?? "graph"}/>{node?.kind ?? "relationship"}</div>
      <h3>{node?.label ?? link?.relation.toLowerCase().replace(/_/g, " ")}</h3>
      {node && <code className="entity-value">{node.value}</code>}
      {link && <p className="relationship-sentence">{names.get(link.source)?.value}<span>→ {link.relation.toLowerCase().replace(/_/g, " ")} →</span>{names.get(link.target)?.value}</p>}
      <span className="basis-badge">{link?.basis ?? "Returned repository entity"}</span>
      <div className="inspector-section"><span className="small-caps">SOURCE LINKS</span><SourceLinks urls={sources}/></div>
      {related.length > 0 && <div className="inspector-section"><span className="small-caps">CONNECTED THROUGH · {related.length}</span><div className="related-links">{related.map(item => <button key={item.id} onClick={() => onSelect({ type: "link", id: item.id })}><span>{item.relation.toLowerCase().replace(/_/g, " ")}</span><strong>{names.get(item.source === node?.id ? item.target : item.source)?.label}</strong><Icon name="arrow" size={14}/></button>)}</div></div>}
      <div className="inspector-section"><span className="small-caps">SUPPORTING RECORDS · {entity.refs.length}</span><p className="muted">Snapshot <code>{evidence.snapshot_id ?? "unspecified"}</code></p>
        {entity.refs.map(ref => { const row = getRecord(evidence, ref); return <details className="record-detail" key={`${ref.collection}:${ref.index}`}><summary>{ref.collection === "derived_results" ? "Commit detail" : "Evidence row"} {ref.index + 1}</summary><pre>{JSON.stringify(row, null, 2)}</pre></details>; })}
      </div>
    </div>}
  </aside>;
}
