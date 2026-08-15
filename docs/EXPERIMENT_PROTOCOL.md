# Experiment Protocol

> **Template status: UNFILLED — NOT FROZEN — NOT AUTHORIZATION TO RUN**
>
> Complete and independently check every applicable `<UNFILLED>` field before
> starting the corresponding pilot or confirmatory runs. This template does not
> itself select conditions, seeds, metrics, thresholds, models, or conclusions.

## 0. Protocol identity and freeze state

- Experiment ID: `<UNFILLED>`
- Title: `<UNFILLED>`
- Protocol version: `<UNFILLED>`
- Status (`draft`, `pilot-frozen`, `confirmatory-frozen`, `superseded`): `<UNFILLED>`
- Author: `<UNFILLED>`
- Independent checker: `<UNFILLED>`
- Approver: `<UNFILLED>`
- Created at (UTC): `<UNFILLED>`
- Pilot freeze at (UTC): `<UNFILLED>`
- Confirmatory freeze at (UTC): `<UNFILLED>`
- Confirmatory-data access boundary: `<UNFILLED>`
- Source commit SHA and dirty state: `<UNFILLED>`
- Config artifact path and SHA-256: `<UNFILLED>`
- Prompt artifact/hash and, if semantics changed, Su's explicit approval
  reference; otherwise `unchanged`: `<UNFILLED>`
- Log schema version: `<UNFILLED>`
- Metric specification path/version/hash: `<UNFILLED>`
- Candidate/exclusion registry path/version/hash, or `not applicable`: `<UNFILLED>`

## 1. Research question and claim boundary

- Research question: `<UNFILLED>`
- Pre-registered hypothesis: `<UNFILLED>`
- Null/negative outcome interpretation: `<UNFILLED>`
- Claims explicitly out of scope: `<UNFILLED>`

| Claim ID | Planned statement | Evidence class | Operational evidence required | Required contrast | Prohibited stronger wording |
|---|---|---|---|---|---|
| `<UNFILLED>` | `<UNFILLED>` | `<UNFILLED>` | `<UNFILLED>` | `<UNFILLED>` | `<UNFILLED>` |

Evidence class must be one of: `direct observation`, `mechanical derivation`,
`interpretation/inference`, or `hypothesis/proposal`.

## 2. Pre-registered observable chain

- Observable phenomenon and operational definition: `<UNFILLED>`
- Domain 1: `<UNFILLED>`
- Domain 2 (or more): `<UNFILLED>`
- One time-ordered chain: `<UNFILLED> → <UNFILLED> → <UNFILLED>`
- Raw record and field supporting each link: `<UNFILLED>`
- Manipulable intervention point: `<UNFILLED>`
- Control condition: `<UNFILLED>`
- Evidence separating the chain from co-occurrence or a post-hoc narrative: `<UNFILLED>`
- Boundary between simulation-supported inference and external extrapolation: `<UNFILLED>`

## 3. Conditions, contrasts, and invariants

| Condition ID | Manipulated variable(s) | Value/config reference | Control role | Planned paired contrast |
|---|---|---|---|---|
| `<UNFILLED>` | `<UNFILLED>` | `<UNFILLED>` | `<UNFILLED>` | `<UNFILLED>` |

- Experimental unit: `<UNFILLED>`
- Pairing/blocking unit: `<UNFILLED>`
- Condition assignment procedure: `<UNFILLED>`
- World/scenario held constant: `<UNFILLED>`
- Initial-state procedure held constant: `<UNFILLED>`
- Prompt semantics/hash held constant: `<UNFILLED>`
- Sampling parameters held constant: `<UNFILLED>`
- Communication rules except the declared intervention held constant: `<UNFILLED>`
- Agent count and step count held constant: `<UNFILLED>`
- Runtime/backend/checkpoint policy: `<UNFILLED>`
- Prompt contains no bloc/model/self-or-other model identity: `<UNFILLED>`
- Prompt contains no desired result, qualitative evaluation, optimization target,
  or behavioral hint: `<UNFILLED>`

## 4. Pilot and confirmatory run plan

### 4.1 Pilot set

- Discovery/calibration purpose only: `<UNFILLED>`
- Seed list or immutable seed-list artifact/hash: `<UNFILLED>`
- Conditions and planned run count: `<UNFILLED>`
- Quantities permitted to be calibrated: `<UNFILLED>`
- Outputs prohibited from use as confirmatory evidence: `<UNFILLED>`

### 4.2 Confirmatory set

- Seed list or immutable seed-list artifact/hash: `<UNFILLED>`
- Evidence of disjointness from pilot seeds: `<UNFILLED>`
- Conditions and planned run count: `<UNFILLED>`
- Rule prohibiting changes after confirmatory-data access: `<UNFILLED>`

### 4.3 Per-run execution envelope

- Agents and steps per run: `<UNFILLED>`
- Planned logical generations per run and total: `<UNFILLED>`
- Run ID and fresh output-directory scheme: `<UNFILLED>`
- Time/cost ceiling: `<UNFILLED>`
- Stop/abort rule: `<UNFILLED>`
- GPU allocation and required preflight artifact: `<UNFILLED>`
- Approval reference for long, paid, remote, or all-8-GPU execution,
  or `not applicable`: `<UNFILLED>`

## 5. Runtime and model provenance

| Role | Provider/backend | Exact checkpoint/revision | Digest | Quantization | Chat template | Generation config | Sampling parameters |
|---|---|---|---|---|---|---|---|
| `<UNFILLED>` | `<UNFILLED>` | `<UNFILLED>` | `<UNFILLED>` | `<UNFILLED>` | `<UNFILLED>` | `<UNFILLED>` | `<UNFILLED>` |

- Dependency/environment capture procedure: `<UNFILLED>`
- Determinism claim and tested scope (world state versus model output): `<UNFILLED>`
- Backend/batch-order test reference: `<UNFILLED>`

## 6. Phase and communication semantics gate

- Evidence that all Phase 1 decisions finish before any delivery: `<UNFILLED>`
- Evidence that all Phase 3 decisions finish before any movement: `<UNFILLED>`
- Snapshot used to construct each phase's decisions: `<UNFILLED>`
- Communication boundary definition and regression test: `<UNFILLED>`
- Deterministic result/log ordering rule: `<UNFILLED>`
- Required protocol-version consequence of phase, communication, prompt, schema,
  or metric changes: `<UNFILLED>`

## 7. Raw data integrity and run eligibility

- Required raw files and schema reference: `<UNFILLED>`
- Raw event natural key/event ID rule: `<UNFILLED>`
- Required run metadata fields: `<UNFILLED>`
- Raw manifest/hash procedure: `<UNFILLED>`
- Validation command/version: `<UNFILLED>`
- Completed-run inclusion rule: `<UNFILLED>`
- Null/negative run treatment: `<UNFILLED>`
- Failed/aborted run retention and analysis treatment: `<UNFILLED>`
- Transport/parse/schema-failure thresholds: `<UNFILLED>`
- Missing-data rule: `<UNFILLED>`
- Rule prohibiting raw-log editing, appending, or overwriting: `<UNFILLED>`
- Attestation/evidence that model output is treated as untrusted data and that
  instructions, code, and URLs in it are never executed: `<UNFILLED>`
- Regression evidence that each new scenario, model, intervention, or metric is
  additive and does not break existing experiments: `<UNFILLED>`

## 8. Frozen metric specification references

The metric specification must preserve these mandatory invariants:

- Delivery alone is `exposure`, never `reuse` or `adoption`.
- `reuse` requires the receiver's own generated output at a strictly later step.
- Later data may not select vocabulary or thresholds used to classify earlier events.
- `reasoning` is model-generated explanation, not verified internal reasoning truth.

| Metric/event | Specification reference | Allowed raw inputs | Excluded inputs | Temporal rule | Counting unit/denominator | Censoring rule |
|---|---|---|---|---|---|---|
| Innovation | `<UNFILLED>` | `<UNFILLED>` | `<UNFILLED>` | `<UNFILLED>` | `<UNFILLED>` | `<UNFILLED>` |
| Exposure | `<UNFILLED>` | `<UNFILLED>` | `<UNFILLED>` | `<UNFILLED>` | `<UNFILLED>` | `<UNFILLED>` |
| Reuse | `<UNFILLED>` | `<UNFILLED>` | `<UNFILLED>` | `<UNFILLED>` | `<UNFILLED>` | `<UNFILLED>` |
| Second hop | `<UNFILLED>` | `<UNFILLED>` | `<UNFILLED>` | `<UNFILLED>` | `<UNFILLED>` | `<UNFILLED>` |
| Behavioral association | `<UNFILLED>` | `<UNFILLED>` | `<UNFILLED>` | `<UNFILLED>` | `<UNFILLED>` | `<UNFILLED>` |

- Candidate/threshold discovery data and procedure: `<UNFILLED>`
- Normalization/exclusion artifact version and hash: `<UNFILLED>`
- Ambiguous/tied/simultaneous-origin rule: `<UNFILLED>`
- Semantic-match rule or `not used in primary metric`: `<UNFILLED>`
- Frozen registry/threshold artifact and hash: `<UNFILLED>`
- Future-information regression-test reference: `<UNFILLED>`

## 9. Analysis plan

- Primary outcome/estimand: `<UNFILLED>`
- Primary condition contrast: `<UNFILLED>`
- Aggregation level: `<UNFILLED>`
- Uncertainty interval/method: `<UNFILLED>`
- Time-to-event/non-occurrence treatment: `<UNFILLED>`
- Multiple-comparison policy: `<UNFILLED>`
- Secondary outcomes: `<UNFILLED>`
- Sensitivity/robustness analyses: `<UNFILLED>`
- Rule against selecting conditions, runs, or events after viewing outcomes: `<UNFILLED>`

## 10. Judge and human review plan

- External judge used (`yes`/`no`): `<UNFILLED>`
- Judge role and primary-metric boundary: `<UNFILLED>`
- Blinded inputs and hidden condition/model/hypothesis fields: `<UNFILLED>`
- Judge prompt/hash, model revision, retry rule, and raw-response retention: `<UNFILLED>`
- Human audit sampling and agreement/precision procedure: `<UNFILLED>`
- Ambiguous-case treatment: `<UNFILLED>`

## 11. Derived outputs and traceability

- Fresh, versioned derived-output path and no-overwrite rule: `<UNFILLED>`
- Derived artifact list/schema: `<UNFILLED>`
- Mapping from each empirical claim/event to run ID, config hash, source commit,
  raw record/hash, and metric version: `<UNFILLED>`
- Deterministic ordering/reproduction check: `<UNFILLED>`
- Batch manifest including completed, null, negative, failed, and aborted runs: `<UNFILLED>`

## 12. Pre-run readiness gates

| Gate | Required command/test artifact | Required result | Actual evidence | Checker |
|---|---|---|---|---|
| Phase barriers | `<UNFILLED>` | `<UNFILLED>` | `<UNFILLED>` | `<UNFILLED>` |
| Communication boundary | `<UNFILLED>` | `<UNFILLED>` | `<UNFILLED>` | `<UNFILLED>` |
| Run collision/integrity/abort | `<UNFILLED>` | `<UNFILLED>` | `<UNFILLED>` | `<UNFILLED>` |
| Untrusted model-output non-execution | `<UNFILLED>` | `<UNFILLED>` | `<UNFILLED>` | `<UNFILLED>` |
| Additive/backward compatibility | `<UNFILLED>` | `<UNFILLED>` | `<UNFILLED>` | `<UNFILLED>` |
| Exposure differs from reuse | `<UNFILLED>` | `<UNFILLED>` | `<UNFILLED>` | `<UNFILLED>` |
| Future-information exclusion | `<UNFILLED>` | `<UNFILLED>` | `<UNFILLED>` | `<UNFILLED>` |
| Derived-output collision/provenance | `<UNFILLED>` | `<UNFILLED>` | `<UNFILLED>` | `<UNFILLED>` |

- Readiness verdict (`NOT READY` until every required gate has evidence): `<UNFILLED>`
- Approved run-start window: `<UNFILLED>`

## 13. Amendments and deviations

| Amendment ID | UTC time | Section | Change/reason | Data already accessed | New version | Confirmatory impact | Approver |
|---|---|---|---|---|---|---|---|
| `<UNFILLED>` | `<UNFILLED>` | `<UNFILLED>` | `<UNFILLED>` | `<UNFILLED>` | `<UNFILLED>` | `<UNFILLED>` | `<UNFILLED>` |

Changes after confirmatory-data access may not be silently retrofitted. A change
to conditions, metrics, thresholds, exclusions, or analysis requires an explicit
deviation record and, when applicable, a new version and confirmatory dataset.

## 14. Freeze sign-off

- Author sign-off / UTC: `<UNFILLED>`
- Checker sign-off / UTC: `<UNFILLED>`
- Approver sign-off / UTC: `<UNFILLED>`
- Frozen document SHA-256: `<UNFILLED>`
