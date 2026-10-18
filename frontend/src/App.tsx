import { useEffect, useMemo, useRef, useState } from "react";
import { createFinding, listSnapshots, queryRepository, recallMemory } from "./api";
import AnswerPanel from "./components/AnswerPanel";
import ChangeSummaryPanel from "./components/ChangeSummaryPanel";
import EvidenceTable from "./components/EvidenceTable";
import ImpactPathPanel from "./components/ImpactPathPanel";
import ReviewerPanel from "./components/ReviewerPanel";
import DecisionPanel from "./components/DecisionPanel";
import MemoryPanel from "./components/MemoryPanel";
import PatchPanel from "./components/PatchPanel";
import QueryComposer from "./components/QueryComposer";
import QueryDetails from "./components/QueryDetails";
import ReasoningTrace from "./components/ReasoningTrace";
import WorkspaceShell from "./components/layout/WorkspaceShell";
import GraphExplorer from "./components/graph/GraphExplorer";
import GraphPreview from "./components/graph/GraphPreview";
import Icon, { type IconName } from "./components/Icon";
import SourceLinks from "./components/SourceLinks";
import { buildEvidenceGraph } from "./lib/evidenceGraph";
import type { QueryResponse, Snapshot } from "./types";

const examples = [
  ["Contributors", "Which contributors changed files matching app.py?"],
  ["Exact changes", "What exactly changed in src/flask/app.py?"],
  ["File history", "Show the history of src/flask/app.py"],
  ["Commit impact", "What files were affected by commit d086db856be1872?"],
  ["Reviewers", "Who should review changes to src/flask/app.py?"],
  ["Decision trace", "Why was the current request-handling design chosen, and was an earlier decision replaced?"],
  ["Memory recall", "What did I previously find about src/flask/app.py?"],
];
type Tab = "overview" | "graph" | "changes" | "evidence";
const tabIcons: Record<Tab, IconName> = { overview: "overview", graph: "graph", changes: "commit", evidence: "code" };

export default function App() {
  const [page, setPage] = useState<"explore" | "memory">("explore");
  const [collapsed, setCollapsed] = useState(false);
  const [question, setQuestion] = useState(examples[0][1]);
  const [snapshots, setSnapshots] = useState<Snapshot[]>([]);
  const [snapshotId, setSnapshotId] = useState("");
  const [snapshotsState, setSnapshotsState] = useState<"loading" | "ready" | "error">("loading");
  const [result, setResult] = useState<QueryResponse | null>(null);
  const [tab, setTab] = useState<Tab>("overview");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [tenant, setTenant] = useState("demo-alpha");
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [savedLabel, setSavedLabel] = useState<string | undefined>();
  const [resultVersion, setResultVersion] = useState(0);
  const epoch = useRef(0);
  const pending = useRef<AbortController | null>(null);
  const pendingSave = useRef<AbortController | null>(null);
  const tabButtons = useRef<(HTMLButtonElement | null)[]>([]);
  const evidence = result?.evidence ?? null;
  const graph = useMemo(() => buildEvidenceGraph(evidence, tenant), [evidence, tenant]);
  const hasChanges = !!evidence && (["file_change_detail", "file_history", "contributor_changes", "commit_impact"].includes(evidence.tool_name) || (evidence.tool_name === "file_contributors" && evidence.derived_results.length > 0));
  const tabs: Tab[] = ["overview", "graph", ...(hasChanges ? ["changes" as const] : []), "evidence"];

  useEffect(() => {
    const controller = new AbortController();
    const initialEpoch = epoch.current;
    listSnapshots(controller.signal).then(available => {
      if (controller.signal.aborted) return;
      setSnapshots(available);
      // Avoid changing the context underneath a question submitted while snapshots load.
      if (epoch.current === initialEpoch && available.length) setSnapshotId(available[0].snapshot_id);
      setSnapshotsState("ready");
    }).catch(() => { if (!controller.signal.aborted) setSnapshotsState("error"); });
    return () => { controller.abort(); pending.current?.abort(); pendingSave.current?.abort(); epoch.current++; };
  }, []);

  function clearContext() {
    epoch.current++;
    pending.current?.abort(); pending.current = null;
    pendingSave.current?.abort(); pendingSave.current = null;
    setResult(null); setLoading(false); setError(null); setSaving(false); setSavedLabel(undefined); setSessionId(null); setTab("overview");
  }
  function switchPage(next: "explore" | "memory") {
    if (next === page) return;
    clearContext(); setPage(next); setQuestion(next === "memory" ? "app.py" : examples[0][1]);
  }

  async function handleSubmit() {
    const trimmed = question.trim();
    if (!trimmed || pending.current) return;
    const current = ++epoch.current;
    const controller = new AbortController();
    pending.current = controller; pendingSave.current?.abort(); pendingSave.current = null;
    setLoading(true); setResult(null); setError(null); setSavedLabel(undefined); setSaving(false); setTab("overview");
    try {
      const response: QueryResponse = page === "memory" ? {
        question: trimmed, intent: "recall_context", answer: "Saved findings matching your search appear below. These are recalled context, not newly verified repository facts.",
        evidence: await recallMemory(tenant, trimmed, snapshotId, controller.signal), model: null, used_fallback: false, limitation: null, execution_mode: null, tool_calls: [], session_id: null,
      } : await queryRepository(trimmed, snapshotId, tenant, sessionId, controller.signal);
      if (epoch.current !== current || controller.signal.aborted) return;
      setResult(response); setSessionId(response.session_id); setResultVersion(value => value + 1);
    } catch (requestError) {
      if (epoch.current === current && !controller.signal.aborted) setError(requestError instanceof Error ? requestError.message : "The request failed.");
    } finally {
      if (epoch.current === current) { setLoading(false); pending.current = null; }
    }
  }

  async function handleSaveFinding() {
    if (!result?.evidence || pendingSave.current || savedLabel) return;
    const current = epoch.current;
    const controller = new AbortController(); pendingSave.current = controller;
    setSaving(true); setError(null);
    const references = new Map<string, { type: string; value: string }>();
    for (const row of [...result.evidence.rows, ...result.evidence.derived_results]) {
      for (const path of [row.file_path, row.affected_file, ...(Array.isArray(row.file_paths) ? row.file_paths : [])]) {
        if (typeof path === "string" && path) references.set(path, { type: "file", value: path });
      }
    }
    try {
      const finding = await createFinding(tenant, { text: result.answer, references: [...references.values()], source_urls: result.evidence.source_urls, snapshot_id: result.evidence.snapshot_id, session_id: result.session_id, idempotency_key: [tenant, result.question, result.evidence.snapshot_id ?? "latest"].join(":") }, controller.signal);
      if (current === epoch.current && !controller.signal.aborted) setSavedLabel(finding.embedding_status === "ready" ? "Saved for semantic recall" : "Saved · lexical recall available");
    } catch (requestError) {
      if (current === epoch.current && !controller.signal.aborted) setError(requestError instanceof Error ? requestError.message : "Could not save the finding.");
    } finally { if (current === epoch.current) { setSaving(false); pendingSave.current = null; } }
  }

  return <WorkspaceShell page={page} onPageChange={switchPage} tenant={tenant} onTenantChange={value => { clearContext(); setTenant(value); }} snapshots={snapshots} snapshotId={snapshotId} onSnapshotChange={value => { clearContext(); setSnapshotId(value); }} snapshotsState={snapshotsState} collapsed={collapsed} onToggle={() => setCollapsed(value => !value)}>
    {snapshotsState === "error" && <p className="notice">Could not load snapshots. Questions can still request the latest complete snapshot. Check that the backend is running on port 8010.</p>}
    <section className="query-workspace" aria-label={page === "memory" ? "Search saved findings" : "Ask a repository question"}>
      <div className="query-heading"><span className="panel-kicker"><Icon name={page === "memory" ? "memory" : "search"} size={15}/>{page === "memory" ? "RECALL A FINDING" : "ASK YOUR REPOSITORY"}</span><span className="keyboard-hint">Ctrl + Enter <kbd>↵</kbd></span></div>
      <QueryComposer question={question} loading={loading} onQuestionChange={setQuestion} onSubmit={handleSubmit} memory={page === "memory"}/>
      {page === "explore" && <div className="examples"><span>Explore</span>{examples.map(([label, value]) => <button key={label} onClick={() => setQuestion(value)} className={question === value ? "active" : ""}>{label}<span aria-hidden="true">↗</span></button>)}</div>}
    </section>
    {error && <div className="error-banner" role="alert"><strong>Something needs attention.</strong><p>{error}</p><span>Check your services and try again. Existing saved findings are unchanged by a failed query.</span></div>}
    {loading && <div className="loading-state" role="status"><span className="loader"/><div><h2>{page === "memory" ? "Looking for saved context…" : "Waiting for repository evidence…"}</h2><p>The response will include the returned records and available sources.</p></div><button className="text-button" onClick={() => { epoch.current++; pending.current?.abort(); pending.current = null; setLoading(false); }}>Cancel request</button></div>}
    {!result && !loading && <section className="welcome-state"><div className="welcome-art" aria-hidden="true"><div className="orbit orbit-one"/><div className="orbit orbit-two"/><div className="orbit orbit-three"/><span className="orbit-center"><Icon name={page === "memory" ? "memory" : "graph"} size={36}/></span><i className="orbit-dot dot-one"/><i className="orbit-dot dot-two"/><i className="orbit-dot dot-three"/></div><p className="eyebrow">{page === "memory" ? "YOUR TEAM’S SAVED CONTEXT" : "A CLEARER VIEW OF YOUR CODEBASE"}</p><h2>{page === "memory" ? "Good findings deserve a second look." : "Start with a question. Follow the connections."}</h2><p>{page === "memory" ? "Save a repository answer as a finding, then search for it here. Only the selected tenant’s findings are requested." : "Get an answer, explore the relationships in 3D, and inspect the evidence behind each connection."}</p><div className="welcome-steps"><span><b>01</b> Ask</span><span className="step-line"/><span><b>02</b> Explore</span><span className="step-line"/><span><b>03</b> Understand</span></div></section>}
    {result && !loading && <section className="results-workspace" key={tenant + ":" + resultVersion}>
      <div className="result-heading"><div><span className="eyebrow">{page === "memory" ? "RECALLED CONTEXT" : "YOUR EVIDENCE TRAIL"}</span><h2>{result.question}</h2></div><span className="basis-badge">{result.intent === "recall_context" ? "Saved context" : result.used_fallback ? "Evidence summary" : "Model synthesis"}</span></div>
      <div className="result-tabs" role="tablist" aria-label="Result views">{tabs.map((item, i) => <button key={item} ref={element => { tabButtons.current[i] = element; }} role="tab" id={"tab-" + item} aria-controls={"view-" + item} aria-selected={tab === item} tabIndex={tab === item ? 0 : -1} onClick={() => setTab(item)} onKeyDown={event => {
        const next = event.key === "ArrowRight" ? (i + 1) % tabs.length : event.key === "ArrowLeft" ? (i - 1 + tabs.length) % tabs.length : event.key === "Home" ? 0 : event.key === "End" ? tabs.length - 1 : -1;
        if (next >= 0) { event.preventDefault(); setTab(tabs[next]); tabButtons.current[next]?.focus(); }
      }}><Icon name={tabIcons[item]} size={16}/>{item[0].toUpperCase() + item.slice(1)}{item === "graph" && graph.nodes.length > 0 && <span className="tab-count">{graph.nodes.length}</span>}</button>)}<span className="snapshot-caption" title={evidence?.snapshot_id ?? "Unspecified snapshot"}>{evidence?.snapshot_id ?? "No snapshot returned"}</span></div>
      <div className="result-view" key={tab} role="tabpanel" id={"view-" + tab} aria-labelledby={"tab-" + tab} tabIndex={0}>
        {tab === "overview" && <><div className="overview-grid"><AnswerPanel result={result} onSaveFinding={handleSaveFinding} saving={saving} saved={!!savedLabel} savedLabel={savedLabel}/><GraphPreview graph={graph} onOpen={() => setTab("graph")}/></div>{evidence && <><MemoryPanel evidence={evidence}/><ReviewerPanel evidence={evidence}/><DecisionPanel evidence={evidence}/><ImpactPathPanel evidence={evidence}/>{evidence.warnings.map(warning => <p className="notice" key={warning}>{warning}</p>)}<section className="panel source-panel"><div className="panel-heading"><span className="panel-kicker">FOLLOW THE SOURCES</span><span className="row-count">{evidence.source_urls.length} returned links</span></div><SourceLinks urls={evidence.source_urls}/></section></>}</>}
        {tab === "graph" && (evidence ? <GraphExplorer graph={graph} evidence={evidence}/> : <div className="panel"><p>No graph evidence was returned for this answer.</p></div>)}
        {tab === "changes" && evidence && <><PatchPanel evidence={evidence}/><ChangeSummaryPanel evidence={evidence}/></>}
        {tab === "evidence" && <><ReasoningTrace result={result}/>{evidence && <><EvidenceTable evidence={evidence}/>{evidence.derived_results.length > 0 && <EvidenceTable evidence={{ ...evidence, rows: evidence.derived_results, columns: [...new Set(evidence.derived_results.flatMap(row => Object.keys(row)))], source_urls: [] }} title="Supporting commit records"/>}<QueryDetails evidence={evidence}/></>}</>}
      </div>
    </section>}
  </WorkspaceShell>;
}
