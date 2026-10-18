# RepoBrain hackathon demo

## Verified local preflight

The demo environment has been checked against snapshot
`pallets-flask-d086db856be1`:

- Backend health endpoint: `http://127.0.0.1:8010/api/health` returned HTTP 200.
- Frontend: `http://127.0.0.1:5173` returned HTTP 200.
- Ollama has `llama3.2:3b` and `nomic-embed-text` available.
- The MCP graph tool returned contributors, commit change summaries, patch
  excerpts, source URLs, and dependency witness paths from FalkorDB.
- The checked-in scorecard is regenerated with the command below before each
  presentation. Do not reuse older scores as if they were from a fresh run.

## Start and verify

Start Docker Desktop/FalkorDB and Ollama, then open two PowerShell terminals.
From `D:\Projects\RepoBrain`, run the backend in one:

```powershell
$env:PYTHONPATH='backend;.vendor;.mcp_vendor'
python -m uvicorn app.main:app --host 127.0.0.1 --port 8010
```

In the second terminal:

```powershell
cd D:\Projects\RepoBrain\frontend
$env:VITE_API_BASE_URL='http://127.0.0.1:8010'
npm run dev -- --host 127.0.0.1
```

Open `http://127.0.0.1:5173`, select snapshot
`pallets-flask-d086db856be1`, and select tenant `demo-alpha`.

Run a fresh comparison before recording:

```powershell
cd D:\Projects\RepoBrain
$env:PYTHONPATH='backend;.vendor;.mcp_vendor'
python -m app.evaluation.cli --mode mcp --include-baseline
```

Show `outputs/evaluation/latest_run.md` only after the command finishes
successfully. It compares RepoBrain with the local model without repository
context on the defined golden questions; it is a small, project-specific test
set, not a general benchmark.

## Three-minute demo

1. **Ask a contributor question (40 seconds).** Ask: `Which contributors
   changed files matching app.py?` Show the `file_contributors` MCP call,
   snapshot ID, evidence rows, and source URLs. FalkorDB traverses
   `Snapshot -[:CONTAINS_COMMIT]-> Commit -[:CHANGED]-> File` and
   `Commit -[:AUTHORED_BY]-> Person`; this is the graph proof, not a vector
   search or model guess.
2. **Show what changed (35 seconds).** Ask: `What exactly changed in
   src/flask/app.py?` Open a commit row and its patch excerpt/source link. The
   current snapshot includes commit subjects and bounded unified patches for
   matching commits. Explain that a commit subject and line patch are evidence;
   a model-generated summary is interpretation.
3. **Demonstrate multi-hop impact (45 seconds).** Ask: `What files may be
   affected if src/flask/app.py changes?` Open the 3D graph or list view and
   point to a witness path and hop count. State explicitly that these are
   statically extracted Python import relationships, not runtime dependency
   proof.
4. **Prove persistent, isolated memory (35 seconds).** Save a finding about
   the result for `demo-alpha`; ask a paraphrase such as `What did I previously
   discover about Flask's application entry point?` Then switch to `demo-beta`
   and show that Alpha's finding is not returned.
5. **Close with measurable evidence (25 seconds).** Show the fresh scorecard
   and one query's evidence/provenance panel: selected tool, graph rows,
   snapshot, sources, and any warnings. Call out the size of the test set and
   do not claim a universal accuracy improvement.

## Recording and submission checklist

- Record the browser and visible query/evidence panels from start to finish.
  Keep the terminal or evaluation scorecard ready for the final proof shot.
- Recheck the public repository URL in a signed-out/incognito browser before
  submitting: <https://github.com/Vish212121/RepoGraph>.
- This project currently has no verified hosted deployment. Use the local app
  for the recording unless you separately deploy it and test the public URL.
- Do not show `.env`, tokens, or local credentials on screen.

## Avoid these claims

- Do not describe static import paths as runtime-verified dependencies.
- Do not say the displayed commit subject is a complete explanation of a code
  change; open the patch and source link.
- Do not claim reviewer or decision workflows have review/discussion data in
  this snapshot without first checking the evidence returned live.
- Do not claim a score until the fresh evaluation command succeeds.
