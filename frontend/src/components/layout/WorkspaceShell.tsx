import type { ReactNode } from "react";
import Icon from "../Icon";
import TenantSwitcher from "../TenantSwitcher";
import type { Snapshot } from "../../types";

export default function WorkspaceShell({ children, page, onPageChange, tenant, onTenantChange, snapshots, snapshotId, onSnapshotChange, snapshotsState, collapsed, onToggle }: {
  children: ReactNode; page: "explore" | "memory"; onPageChange: (page: "explore" | "memory") => void;
  tenant: string; onTenantChange: (tenant: string) => void; snapshots: Snapshot[]; snapshotId: string;
  onSnapshotChange: (id: string) => void; snapshotsState: "loading" | "ready" | "error"; collapsed: boolean; onToggle: () => void;
}) {
  const snapshot = snapshots.find(item => item.snapshot_id === snapshotId);
  return <div className={`workspace-shell ${collapsed ? "rail-collapsed" : ""}`}>
    <a href="#workspace-content" className="skip-link">Skip to workspace</a>
    <aside className="nav-rail">
      <a className="brand-lockup" href="#workspace-content" aria-label="RepoBrain workspace"><span className="brand-mark"><Icon name="graph" size={23}/></span><span className="rail-label">Repo<span className="brand-light">Brain</span><small>CONNECTED INTELLIGENCE</small></span></a>
      <span className="rail-heading rail-label">WORKSPACE</span>
      <nav aria-label="Main navigation">
        <button onClick={() => onPageChange("explore")} aria-current={page === "explore" ? "page" : undefined} title="Explore repository"><Icon name="graph"/><span className="rail-label">Explore</span><span className="nav-indicator"/></button>
        <button onClick={() => onPageChange("memory")} aria-current={page === "memory" ? "page" : undefined} title="Memory recall"><Icon name="memory"/><span className="rail-label">Memory recall</span><span className="nav-indicator"/></button>
      </nav>
      <div className="rail-bottom"><div className="rail-note rail-label"><span className="small-caps">BUILT ON CONNECTIONS</span><p>Follow an answer<br/>back to its evidence.</p><span className="stack-label">FalkorDB / Ollama</span></div><button className="rail-toggle" onClick={onToggle} aria-label={collapsed ? "Expand navigation" : "Collapse navigation"} aria-expanded={!collapsed}><Icon name="menu"/><span className="rail-label">Collapse sidebar</span></button></div>
    </aside>
    <div className="workspace-body">
      <header className="workspace-topbar">
        <div className="breadcrumb"><Icon name={page === "explore" ? "graph" : "memory"}/><span>Workspace</span><span className="slash">/</span><strong>{page === "explore" ? "Explore" : "Memory"}</strong></div>
        <div className="context-controls"><label className="snapshot-picker"><span>Snapshot</span><select value={snapshotId} onChange={event => onSnapshotChange(event.target.value)} disabled={snapshotsState === "loading" || !snapshots.length}>
          {!snapshots.length && <option value="">{snapshotsState === "loading" ? "Loading…" : "Latest complete snapshot"}</option>}
          {snapshots.map(item => <option key={item.snapshot_id} value={item.snapshot_id}>{item.repository ?? "Repository"} · {item.commit_sha?.slice(0, 8) ?? item.snapshot_id}</option>)}
        </select></label><TenantSwitcher tenant={tenant} onChange={onTenantChange}/></div>
      </header>
      <main id="workspace-content" className="workspace-content" tabIndex={-1}>
        <div className="page-heading"><div><p className="eyebrow">{page === "explore" ? "YOUR REPOSITORY, CONNECTED" : "CONTEXT THAT STAYS WITH YOU"}</p><h1>{page === "explore" ? <>Less searching.<br className="mobile-break"/> More understanding.</> : "Pick up where you left off."}</h1><p>{page === "explore" ? "Explore the people, changes, and connections behind your code." : "Search saved findings in this tenant. Recalled context may be stale or unverified."}</p></div><div className="repository-context"><span className="context-mark"/><div><strong>{snapshot?.repository ?? "Repository workspace"}</strong><span>{snapshotsState === "error" ? "Snapshot list unavailable" : snapshot ? `${snapshot.file_count ?? "—"} files · ${snapshot.commit_count ?? "—"} commits in snapshot` : "Select context, then ask a question"}</span></div></div></div>
        {children}
      </main>
      <footer className="workspace-footer"><span>REPOBRAIN <span className="footer-divider">/</span> EVIDENCE BEFORE ASSUMPTIONS</span><span>Repository queries are read-only · Saved findings are tenant-scoped</span></footer>
    </div>
  </div>;
}
