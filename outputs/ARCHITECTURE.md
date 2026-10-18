# RepoBrain Architecture Contract

Status: Living implementation contract — updated through semantic tenant memory and evaluation proof

This document freezes the implementation boundary for the RepoBrain hackathon MVP.

## Product definition

RepoBrain is an evidence-backed engineering agent for one public Python repository. It uses FalkorDB to reason over code dependencies, change history, maintainers, reviews, and architectural decisions.

The graph is required for the three hero workflows. The LLM may interpret questions and select tools, but it must not invent repository facts or relationships.

## Target repository

Initial target: `pallets/flask`

Selection rationale:

- Public Python project.
- Meaningful source structure for import and dependency analysis.
- Long-lived commit history.
- Maintainer and review activity suitable for reviewer recommendations.
- Public issues and pull requests suitable for decision tracing.

The ingestion milestone must pin a concrete repository commit SHA. The live demo must display that SHA and the graph snapshot timestamp.

## MVP capabilities

### 1. Impact analysis

Input: a file path and a bounded hop count.

Output:

- Dependent files.
- Minimum graph distance.
- Witness graph paths.
- Warnings for inferred or stale dependencies.

### 2. Reviewer recommendation

Input: a bounded list of changed file paths.

Output:

- Ranked reviewers.
- File coverage.
- Commit and review evidence.
- Score components.
- Excluded bots and excluded pull-request authors.

### 3. Decision tracing

Input: a topic or design keyword.

Output:

- Matching decisions.
- Supporting pull request, issue, or comment evidence.
- Supersession chain when explicitly supported.
- Confidence and uncertainty warnings.

### 4. Persistent semantic memory

The MVP persists:

- Sessions.
- Questions.
- Findings.
- References from findings to repository entities.
- Local Ollama embeddings stored on `Finding` nodes in FalkorDB.
- Hybrid semantic and lexical recall with snapshot-staleness warnings.

Memory must survive a restart and must be isolated between the two demo tenants.

## Deferred features

These features are intentionally outside the first implementation boundary:

- Arbitrary repository support.
- Full autonomous external actions.
- A general-purpose second agent.
- Change clustering.
- Onboarding-path generation.
- Bus-factor analysis.
- Issue triage.
- Live refresh during the primary demo.
- Sophisticated procedural-memory optimization.

## Evaluation proof

RepoBrain is evaluated against an LLM-only baseline using deterministic evidence
checks. A graph-proof pass requires the expected tool, source-backed evidence,
and configured relationship or witness-path checks. Answer wording alone is not
enough to earn a graph-proof pass.

They may be reconsidered only after the three hero workflows and their tests pass.

## System architecture

```text
GitHub repository
        |
        v
Cached raw records and repository snapshot
        |
        v
Ingestion and graph builder
        |
        v
FalkorDB graph
        |
        +--> impact-analysis tool
        +--> reviewer tool
        +--> decision-tracing tool
        +--> memory tools
                         |
                         v
                   MCP tool server
                         ^
                         |
                   MCP client in agent host
                         ^
                         |
                    FastAPI backend
                         ^
                         |
                    React/Vite frontend
```

## Graph model

### Nodes

```text
Repository
Person
Commit
File
PullRequest
Issue
Review
Comment
Decision
Evidence
Session
Question
Finding
ToolCall
```

### Relationships

```text
(Person)-[:AUTHORED]->(Commit)
(Commit)-[:TOUCHED {added, deleted, change_type}]->(File)
(Person)-[:OPENED]->(PullRequest)
(Person)-[:REVIEWED]->(PullRequest)
(Review)-[:ON]->(PullRequest)
(PullRequest)-[:INCLUDES]->(Commit)
(PullRequest)-[:CLOSES]->(Issue)
(Comment)-[:ON]->(PullRequest)
(Comment)-[:ON]->(Issue)
(Comment)-[:MENTIONS]->(File)
(File)-[:DEPENDS_ON {evidence, confidence}]->(File)
(File)-[:CO_CHANGES_WITH {weight, window}]->(File)
(Decision)-[:DECIDED_IN]->(PullRequest)
(Decision)-[:SUPPORTED_BY]->(Evidence)
(Decision)-[:SUPERSEDES]->(Decision)
(Finding)-[:ABOUT]->(File)
(Question)-[:USED_TOOL]->(ToolCall)
(ToolCall)-[:RETURNED]->(Evidence)
```

### Stable identifiers

Use the following identifiers wherever available:

- GitHub repository ID.
- GitHub user ID, with login as a display property.
- Commit SHA.
- Normalized repository-relative file path.
- Pull-request number.
- Issue number.
- Evidence ID.
- Snapshot ID.

Display names must not be used as identity keys.

### Provenance properties

Source-derived nodes and evidence records should preserve:

```text
source_url
source_id
snapshot_id
fetched_at
content_hash
```

User-owned memory nodes should preserve:

```text
tenant_id
created_at
updated_at
```

## Tenant model

The MVP uses one FalkorDB graph so memory can connect directly to repository entities. User-owned nodes carry `tenant_id`; every memory read and write must filter by that property.

The client must not select a graph name or arbitrary tenant ID. The backend maps a validated demo identity to an internal tenant ID.

## Tool contract

Tools are semantic and typed. The agent is not given arbitrary Cypher execution.

```text
analyze_impact(file_path, max_hops, limit)
suggest_reviewers(changed_files, limit)
trace_decision(topic, limit)
recall_context(tenant_id, query, limit)
create_finding(tenant_id, text, references)
update_finding(tenant_id, finding_id, status, version)
```

Every tool result must contain:

```text
result_type
facts
derived_results
evidence
witness_paths
query_template
parameters
snapshot_id
warnings
```

## Answer policy

The final answer must distinguish:

- Verified facts: directly supported by source data.
- Derived results: computed by Cypher or a graph algorithm.
- Inferred conclusions: generated by the model from returned evidence.

If the graph has no evidence, the agent must say so. It must not fill gaps with general knowledge or fabricated repository details.

## Operational constraints

- Pin the FalkorDB image.
- Pin the MCP SDK version.
- Use parameterized Cypher.
- Use read-only queries for analysis tools.
- Bound hop counts, result sizes, tool calls, and execution time.
- Make memory writes idempotent.
- Prevent overlapping refresh jobs.
- Treat GitHub text as untrusted input.
