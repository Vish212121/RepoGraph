# RepoBrain Evaluation Plan

Status: Living evaluation contract — deterministic graph-proof scoring implemented

## Evaluation objective

Demonstrate that FalkorDB changes the quality and explainability of repository answers compared with an LLM-only or text-only baseline.

The evaluation must measure both correctness and evidence quality. A fluent answer without valid repository evidence does not count as success.

## Evaluation set

The checked-in smoke suite contains eight snapshot-bound questions. Expand it
to 30–50 questions only after each new case has a manually checked source and
relationship expectation.

Include:

- Direct dependency questions.
- Two-hop and three-hop dependency questions.
- Questions with no matching dependency.
- Reviewer questions involving multiple files.
- Questions where bots appear in the history.
- Decision questions with strong source evidence.
- Decision questions with ambiguous or conflicting evidence.
- Memory recall after restart.
- Cross-tenant isolation cases.

Each question has a structured expected-evidence record containing:

```text
question_id
snapshot_id
expected_answer_facts
expected_evidence_facts
expected_tool
minimum_source_urls
minimum_hops
required_relationships
expected_warnings
```

## Baselines

### Baseline A: LLM-only

Provide the model with the user question and repository name, but no graph results.

Expected weakness: it may provide generic or unsupported repository claims.

### Baseline B: text retrieval

Retrieve matching file names, commit messages, or discussion text without multi-hop graph traversal.

Expected weakness: good lexical matches but poor relationship reasoning.

### System under test

Use RepoBrain’s MCP tools backed by FalkorDB.

## Metrics

### Impact analysis

- Evidence-fact accuracy for expected dependent files.
- Witness-path validity.
- Correct minimum hop distance.
- Required relationship evidence.

### Reviewer recommendation

- Precision@k for expected maintainers.
- File-coverage accuracy.
- Evidence coverage.
- Bot-exclusion accuracy.

### Decision tracing

- Evidence-fact accuracy.
- Source coverage.
- Tool-selection accuracy.
- Unsupported-claim rate.

### Memory

- Semantic recall accuracy after restart.
- Correct stale-state behavior.
- Cross-tenant leakage rate, which must be zero.

### Operations

- p50 and p95 latency.
- Graph-proof accuracy.
- Relationship-proof coverage.
- Graph-unavailable behavior.

## Required ablation result

At least three questions must require relationships that a text-only baseline cannot reliably answer. The current smoke suite includes contributor-history, reviewer-recommendation, decision-tracing, and multi-hop impact cases with explicit relationship expectations.

```text
Person -> Commit -> File -> DEPENDS_ON -> File
```

The demo should show that the graph-backed system returns a concrete path and the baseline does not.

## Acceptance thresholds

The exact numerical thresholds will be filled after the first ingestion run because repository structure affects the difficulty of the test set.

The following are non-negotiable:

- No fabricated source URLs.
- No answer that cites an entity absent from tool results.
- Zero cross-tenant memory reads.
- Every hero answer includes evidence.
- Every graph path contains valid node and relationship identifiers.
- Empty or unavailable graph produces an explicit failure state.

## Review artifacts

The implementation milestone should produce:

- A machine-readable evaluation fixture.
- JSON and Markdown baseline comparison reports.
- Example successful answers.
- Example missing-evidence answers.
- Example contradiction handling.
- A short performance summary.
