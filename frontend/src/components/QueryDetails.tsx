import { useState } from "react";

import type { Evidence } from "../types";

export default function QueryDetails({ evidence }: { evidence: Evidence }) {
  const [open, setOpen] = useState(false);
  return (
    <article className="query-details">
      <button onClick={() => setOpen((current) => !current)} aria-expanded={open}>
        <span><span className="panel-kicker">QUERY DETAILS</span><small>Inspect the read-only Cypher shape and safe parameters</small></span>
        <span className={open ? "chevron open" : "chevron"}>⌄</span>
      </button>
      {open && (
        <div className="query-content">
          <div>
            <span className="trace-label">CYPHER</span>
            <pre>{evidence.query}</pre>
          </div>
          <div>
            <span className="trace-label">PARAMETERS</span>
            <pre>{JSON.stringify(evidence.parameters, null, 2)}</pre>
          </div>
        </div>
      )}
    </article>
  );
}
