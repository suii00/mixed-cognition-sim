# Gate 3 Independent Recheck — Run/Batch Research Eligibility

## Preservation note

This immutable record preserves the independent FAIL evidence supplied with the
limited correction request. It adds no new independent observation and is not a
post-correction checker report.

## Decision

- **FAIL — Gate 3 independent recheck**
- Audited candidate SHA:
  `7257fccda2f4f744d71225429f6a3f7542230af7`
- Severity: **High**
- Freeze recommendation: **DO NOT FREEZE**
- Overall protocol readiness: **NOT READY**
- Pilot authorization: **NO**

## Audited revision

- Correction implementation parent:
  `7b4b3e8d6bf9b45f71ece624b04053f32bcfaefb`
- Previous failed candidates:
  `1cb5e8702b92537ecc2157588bdb435a81a0b060` and
  `255e50798bef1ed2f9136c1e78a2ed8e6e7da849`
- Gate 2 frozen SHA:
  `34c6b802958781b9a8d25420742e092a8a0bee3c`
- Matrix specification at the audited candidate:
  `eight-cell-matrix-v1.1.0`
- Matrix plan schema: `eight-cell-matrix-plan-v1.1.0`
- Batch manifest schema: `eight-cell-batch-manifest-v1.1.0`

## Directly observed High finding

The corrected candidate validates the complete execution-mode evidence chain
in the public batch-validation path. The public run-validation path does not
validate the same batch-level authority and persisted batch-summary evidence.
The two public commands can therefore materially disagree on one immutable
scientific evidence package.

### Case A — Plan and batch metadata disagree on frozen evidence

The synthetic positive-control plan was changed to:

```text
candidate_registry.status = not_frozen
backend_freeze.status = not_frozen
```

Ordinary plan, file, and manifest hashes were recomputed. Batch metadata
continued to claim that the corresponding evidence was frozen.

Observed result:

```text
batch research validation:
  exit 3
  FAIL
  research_eligible = false

run research validation for a run in the same batch:
  exit 0
  PASS
  research_eligible = true
```

### Case B — Batch eligibility summaries are stale false

The authoritative underlying evidence derived a positive synthetic eligibility
result, while `batch_meta.json` and the batch-manifest top-level summaries were
changed to persisted `false` values.

Observed result:

```text
batch research validation:
  exit 3
  FAIL

run research validation:
  exit 0
  PASS
  research_eligible = true
```

## Impact

A selected run could elevate itself above an enclosing batch that had
contradictory authority evidence, stale persisted summaries, or another invalid
required run. Consequently, public run research PASS did not imply public batch
research PASS.

## Required correction

Public run and batch reports must be produced from one validated batch authority
context covering:

- the canonical plan, planned rows, and generated configs;
- batch metadata and batch manifest;
- every required planned run and lifecycle state;
- plan/metadata registry and backend freeze agreement;
- protocol, metric, matrix, and execution-mode evidence;
- independently derived per-run and batch eligibility;
- persisted per-run and batch summary comparisons.

For the research profile, the final public run eligibility must be:

```text
selected_run_research_eligible AND batch_research_eligible
```

Contradictory evidence must produce `FAIL`/exit 3 for both scopes. Consistently
missing or unfrozen evidence must produce `UNVERIFIABLE`/exit 2 for both scopes.
A consistent scripted smoke remains smoke exit 0 and research exit 2. A fully
consistent synthetic positive control may return research exit 0 only as a
zero-network validator-logic fixture.

## Recommendation

Do not freeze `7257fccda2f4f744d71225429f6a3f7542230af7`. Apply only the shared
run/batch eligibility correction, preserve the plan and manifest schema
identifiers, bump the matrix specification patch version, and submit the new
candidate to an independent recheck.
