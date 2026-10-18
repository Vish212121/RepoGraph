# RepoBrain Evaluation Scorecard

This report scores graph proof, not fluent wording alone. A graph-proof pass requires the expected tool, evidence facts, source coverage, required relationship evidence, and expected warnings.

## System comparison

| System | Cases | Graph proof | Evidence facts | Sources | Tool selection | Relationship proof | p50 latency | p95 latency |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| repobrain | 8 | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | 7306.81 ms | 17291.41 ms |
| baseline-no-graph | 8 | 0.0% | 0.0% | 0.0% | 0.0% | 0.0% | 2263.08 ms | 5940.91 ms |

## Case-level proof

| Case | System | Tool | Evidence | Sources | Relationship | Graph proof |
| --- | --- | --- | --- | --- | --- | --- |
| file-contributors-app | repobrain | ✓ | ✓ | ✓ | ✓ | ✓ |
| history-app | repobrain | ✓ | ✓ | ✓ | ✓ | ✓ |
| contributor-files | repobrain | ✓ | ✓ | ✓ | ✓ | ✓ |
| snapshot-overview | repobrain | ✓ | ✓ | ✓ | ✓ | ✓ |
| impact-app | repobrain | ✓ | ✓ | ✓ | ✓ | ✓ |
| reviewers-app | repobrain | ✓ | ✓ | ✓ | ✓ | ✓ |
| decision-automatic-options | repobrain | ✓ | ✓ | ✓ | ✓ | ✓ |
| file-change-detail-app | repobrain | ✓ | ✓ | ✓ | ✓ | ✓ |
| file-contributors-app | baseline-no-graph | — | — | — | — | — |
| history-app | baseline-no-graph | — | — | — | — | — |
| contributor-files | baseline-no-graph | — | — | — | — | — |
| snapshot-overview | baseline-no-graph | — | — | — | — | — |
| impact-app | baseline-no-graph | — | — | — | — | — |
| reviewers-app | baseline-no-graph | — | — | — | — | — |
| decision-automatic-options | baseline-no-graph | — | — | — | — | — |
| file-change-detail-app | baseline-no-graph | — | — | — | — | — |

## Interpretation

- **Verified facts** are accepted only when they appear in returned tool evidence with the required source coverage.
- **Derived graph results** require their configured relationship or hop proof; impact analysis, for example, must expose a witness path.
- **Model prose** is measured separately and cannot turn an unsupported baseline response into a graph-proof pass.
