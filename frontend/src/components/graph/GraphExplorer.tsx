import { Component, lazy, Suspense, useCallback, useMemo, useState, type ReactNode } from "react";
import type { Evidence } from "../../types";
import type { EntityKind, EvidenceGraph, GraphSelection } from "../../types/graph";
import Icon from "../Icon";
import GraphInspector from "./GraphInspector";

const GraphCanvas = lazy(() => import("./GraphCanvas"));
class CanvasBoundary extends Component<{ children: ReactNode; onFailure: () => void }, { failed: boolean }> {
  state = { failed: false };
  static getDerivedStateFromError() { return { failed: true }; }
  componentDidCatch() { this.props.onFailure(); }
  render() { return this.state.failed ? null : this.props.children; }
}

export default function GraphExplorer({ graph, evidence }: { graph: EvidenceGraph; evidence: Evidence }) {
  const [mode, setMode] = useState<"3d" | "list">(() => window.matchMedia("(max-width: 700px)").matches ? "list" : "3d");
  const [failed, setFailed] = useState(false);
  const [selection, setSelection] = useState<GraphSelection>(null);
  const [kinds, setKinds] = useState<EntityKind[]>(["file", "commit", "person"]);
  const [search, setSearch] = useState("");
  const [resetToken, setResetToken] = useState(0), [focusToken, setFocusToken] = useState(0);
  const visible = useMemo(() => {
    const nodes = graph.nodes.filter(node => kinds.includes(node.kind));
    const ids = new Set(nodes.map(node => node.id));
    return { ...graph, nodes, links: graph.links.filter(link => ids.has(link.source) && ids.has(link.target)) };
  }, [graph, kinds]);
  const fail = useCallback(() => { setFailed(true); setMode("list"); }, []);
  const label = (id: string) => graph.nodes.find(node => node.id === id)?.value ?? id;
  const filtered = visible.nodes.filter(node => node.value.toLowerCase().includes(search.toLowerCase()));
  return <section className="graph-explorer" aria-label="Graph explorer">
    <div className="graph-toolbar"><div><span className="panel-kicker">CONNECTION MAP</span><h2>See the relationships.</h2></div><div className="segmented" aria-label="Graph display mode"><button aria-pressed={mode === "3d"} disabled={failed} onClick={() => setMode("3d")}><Icon name="graph" size={16}/>3D graph</button><button aria-pressed={mode === "list"} onClick={() => setMode("list")}><Icon name="list" size={16}/>List</button></div></div>
    <div className="graph-filters"><div className="entity-filters">{(["file", "commit", "person"] as const).map(kind => <button key={kind} aria-pressed={kinds.includes(kind)} onClick={() => { setKinds(current => current.includes(kind) ? current.filter(item => item !== kind) : [...current, kind]); setSelection(null); }}><span className={`node-shape ${kind}`}/>{kind === "person" ? "People" : `${kind[0].toUpperCase()}${kind.slice(1)}s`}<span className="filter-count">{graph.nodes.filter(node => node.kind === kind).length}</span></button>)}</div><div className="graph-actions"><button className="text-button" disabled={!selection || mode !== "3d"} onClick={() => setFocusToken(value => value + 1)}><Icon name="focus" size={15}/>Focus</button><button className="text-button" disabled={mode !== "3d"} onClick={() => { setSelection(null); setResetToken(value => value + 1); }}><Icon name="graph" size={15}/>Fit view</button></div></div>
    {failed && <p className="notice" role="status">3D rendering is unavailable in this browser. All mapped relationships are accessible in List view.</p>}
    <div className="graph-stage"><div className="graph-visual">
      {!visible.nodes.length ? <div className="graph-no-data"><Icon name="graph" size={36}/><h3>{graph.nodes.length ? "No entities match these filters" : "No supported relationships returned"}</h3><p>{graph.nodes.length ? "Enable an entity type above to continue." : "Use Overview and Evidence to inspect this result. The map never guesses missing connections."}</p></div> : mode === "3d" ? <CanvasBoundary onFailure={fail}><Suspense fallback={<div className="graph-no-data" role="status"><span className="loader"/>Loading the 3D explorer…</div>}><GraphCanvas graph={visible} selection={selection} onSelect={setSelection} resetToken={resetToken} focusToken={focusToken} onFailure={fail}/></Suspense></CanvasBoundary> : <div className="graph-list">
        <label className="entity-search"><Icon name="search" size={16}/><input aria-label="Find an entity" placeholder="Find an entity…" value={search} onChange={event => setSearch(event.target.value)}/></label>
        <h3>Entities <span>{filtered.length}</span></h3><div className="entity-list">{filtered.map(node => <button key={node.id} aria-pressed={selection?.id === node.id} onClick={() => setSelection({ type: "node", id: node.id })}><Icon name={node.kind}/><span>{node.value}</span><small>{node.kind}</small><Icon name="arrow" size={14}/></button>)}</div>
        {filtered.length === 0 && <p className="muted">No entities match your search.</p>}
        <h3>Directed relationships <span>{visible.links.length}</span></h3><div className="relationship-list">{visible.links.map(link => <button key={link.id} aria-pressed={selection?.id === link.id} onClick={() => setSelection({ type: "link", id: link.id })}><span>{label(link.source)}</span><small>→ {link.relation.toLowerCase().replace(/_/g, " ")} →</small><span>{label(link.target)}</span><em>{link.basis}</em></button>)}</div>
      </div>}
    </div><GraphInspector graph={visible} evidence={evidence} selection={selection} onSelect={setSelection}/></div>
    <div className="graph-footnote"><span>{visible.nodes.length} / {graph.totalNodes} entities · {visible.links.length} / {graph.totalLinks} relationships</span><span>Arrow direction follows the returned relationship</span></div>
    {graph.notices.map(notice => <p key={notice} className="notice">{notice}</p>)}
  </section>;
}
