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

Mandatory inter-run immutability invariants:

- An existing explicit `run_id` must fail before any LLM call; it must not be
  renamed, suffixed, appended to, or partially replaced.
- Automatically generated run IDs must be unique.
- A rejected repeat attempt must leave every pre-existing run file byte-identical.
- Concurrent claims for the same run ID must produce exactly one owner and one
  or more collision failures.
- A `Simulation` instance may claim execution ownership only once. Concurrent
  non-owner calls and repeats after completed, aborted, or failed outcomes must
  fail before any LLM call without changing files or mutable simulation state.
- Only the owning run may atomically update its documented lifecycle metadata
  (`running` to `completed`, `aborted`, or `failed`).

## 8. Frozen metric specification references

The metric specification must preserve these mandatory invariants:

- Delivery alone is `exposure`, never `reuse` or `adoption`.
- `reuse` requires the receiver's own generated output at a strictly later step.
- Later data may not select vocabulary or thresholds used to classify earlier events.
- `reasoning` is model-generated explanation, not verified internal reasoning truth.

Gate 1 corrected implementation-candidate evidence (not frozen):

- Metric version: `metric-v2.0.0`
- Normative specification: `docs/METRIC_V2_SPEC.md`
- Specification SHA-256:
  `226582354cd777663f5dda0944c66630ba2d7ee30a4cd9bf1ba3b847e895108d`
- Implementation commit:
  `76be8729a5d3c805bfddaba7a590b80047c6e1b1`
- Independent checker result for the superseded candidate
  `b7dcf1b877bda3ae83be2d2331719a60cb41432e`: `FAIL`. Metric semantics,
  provenance, registry controls, deterministic output, and normal collision
  handling passed, but interrupted sequential publication could expose a
  completed-marked partial final leaf and block retry.
- Correction scope: derived-result publication lifecycle only. The corrected
  candidate uses a process-death-safe per-run file lock, private staging,
  file `fsync`, manifest revalidation, and atomic publication. Independent
  recheck of the corrected candidate is pending.
- Gate 1 independent checker: `FAIL` (latest completed check was against the
  superseded candidate above).
- Gate 1 freeze: `NOT DONE`.
- Candidate registry schema: `candidate-registry-v1.0.0`
- Derived schema: `metric-derived-v1.0.0`
- Normalization: `nfkc-casefold-token-sequence-v1`
- Test-fixture-only registry SHA-256:
  `42b7bac1b4038f21e4fccf90ef5bc25b8fdeba6f5e237f5658e2dc3d8393e913`
  (not a production registry and not empirical evidence)

| Metric/event | Specification reference | Allowed raw inputs | Excluded inputs | Temporal rule | Counting unit/denominator | Censoring rule |
|---|---|---|---|---|---|---|
| Innovation | `docs/METRIC_V2_SPEC.md` §6; `metric-v2.0.0` | `phase1_raw.jsonl: parsed.message` | raw output, reasoning, delivery-as-receiver-use, memory/Phase 3, prompt/config strings | Minimum self-use step; unique or simultaneous origin | One event per present registered expression; absent expressions retained in summary | Not applicable; absent through expected final step remains absent |
| Exposure | `docs/METRIC_V2_SPEC.md` §7; `metric-v2.0.0` | `messages.jsonl: step,sender_id,receiver_ids,message`, cross-checked to sender Phase 1 message | reasoning, memory, prompt/config strings | Delivery after Phase 1 at its recorded step | One event per registered expression and receiver delivery | All observed deliveries through expected final step retained |
| Reuse | `docs/METRIC_V2_SPEC.md` §8; `metric-v2.0.0` | Exposure records plus receiver's later `phase1_raw.jsonl: parsed.message` | delivery as use, same/prior self-use, raw output, reasoning, memory/Phase 3 | Receiver self-use must be strictly later than first exposure | One status per exposed expression/receiver pair; all eligible reused and eligible non-reused pairs form the overall denominator | Eligible non-reuse retained with `censor_step = expected_steps`; zero denominator gives JSON `null` |
| Second hop | `docs/METRIC_V2_SPEC.md` §9; `metric-v2.0.0` | Unique innovation, first-hop reuse, same-step relay delivery, and target's later Phase 1 reuse events | simultaneous origin, ambiguous first parent, prior/same-step target use, third or later hops | `S` origin → later `R` reuse/delivery → later `T` reuse; `S/R/T` distinct | One event per fully attributable `S/R/T` chain; secondary descriptive count | No event when any required link is absent or ambiguous |
| Behavioral association | Deferred; not implemented by `metric-v2.0.0` | None | Spatial/action output and all causal or behavioral inference | Not applicable | No denominator or claim | Not applicable |

- Candidate/threshold discovery data and procedure: production discovery is
  `NOT YET FROZEN`; the implementation accepts only an externally fixed,
  hash-pinned registry and performs no target-run discovery.
- Normalization/exclusion artifact version and hash: registry schema
  `candidate-registry-v1.0.0`; production artifact/hash `NOT YET FROZEN`.
- Ambiguous/tied/simultaneous-origin rule: simultaneous origin is retained but
  excluded from source-attributed chains; mixed first-exposure relation is
  retained but excluded from relation-specific rates; multiple first-parent
  senders prevent second-hop attribution.
- Semantic-match rule or `not used in primary metric`: `not used in primary metric`.
- Frozen registry/threshold artifact and hash: `NOT YET FROZEN`.
- Future-information regression-test reference:
  `tests/test_metric_v2.py::MetricV2Tests::test_unregistered_future_text_does_not_change_registered_events`
  and unsafe discovery-provenance registry fixtures at implementation commit
  `76be8729a5d3c805bfddaba7a590b80047c6e1b1`.
- Behavioral association is deferred. No causal or behavioral claim is
  produced by `metric-v2.0.0`.

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

- Fresh, versioned derived-output path and no-overwrite rule:
  `derived/<metric_version>/<run_id>/`; a non-blocking per-run OS file lock
  serializes publishers. The owner writes a unique
  `derived/<metric_version>/.staging/<run_id>-<temporary-id>/` leaf on the same
  filesystem, flushes and `fsync`s all five files, verifies the staged file set
  and manifest, then atomically renames it to the final leaf. Existing or busy
  publication is a collision without suffix, append, reuse, replacement, or
  overwrite; a derived root resolving inside the raw run is rejected.
- Derived artifact list/schema: `metric-derived-v1.0.0` with
  `analysis_meta.json`, `events.jsonl`, `receiver_expression_status.jsonl`,
  `summary.json`, and `derived_manifest.json`.
- Mapping from each empirical claim/event to run ID, config hash, source commit,
  raw record/hash, and metric version: analysis metadata preserves run ID,
  source Git SHA, config/prompt/protocol/metric provenance, registry/spec hashes,
  and the raw manifest; events preserve one-based raw line number, exact-line
  SHA-256 including newline, exact-message SHA-256, and deterministic event IDs.
- Deterministic ordering/reproduction check: canonical compact JSON with sorted
  keys and fixed event/pair ordering; different derived roots are byte-identical
  in `test_different_derived_roots_are_byte_identical`.
- Batch manifest including completed, null, negative, failed, and aborted runs: `<UNFILLED>`

Raw runs are immutable inputs. Input validation and all derived bytes are built
before publication. A final leaf exists only after all required files and their
manifest have been verified. Residual `.staging` leaves are unpublished,
ineligible, ignored by retry, and not automatically removed by analysis.
`derived_manifest.json` hashes the other required derived files; it is not a
replacement for the still-unfilled multi-run batch manifest.

## 12. Pre-run readiness gates

### Gate 0 frozen baseline

- Status: `PASS / FROZEN`
- Frozen commit SHA: `86fad23bc1cddf624550c044348566dc5c212bc7`
- Branch at freeze: `fix/gate0-one-shot`
- Prompt SHA-256: `f414ab30a963636d80239644c2d3770672c77d5b8bdde027de2eb15a0d08bc3d`
- Verification:
  - Windows development host: 78/78 unit tests PASS
  - Linux `gpu-sv-010`: 78/78 unit tests PASS
  - `python3 -m compileall -q engine tests tools main.py`: PASS
  - `git diff --check`: PASS
  - verification worktree: clean
- GPU/model execution during verification: none
- Research runs performed at this gate: none
- Reopen rule: Gate 0 is reopened only if a concrete run-integrity regression is demonstrated.

| Gate | Required command/test artifact | Required result | Actual evidence | Checker |
|---|---|---|---|---|
| Phase barriers | Phase 3 shared-snapshot, transport-failure, parse-failure, iteration-order fixtures | All Phase 3 decisions precede any Phase 4 movement; transport abort applies no pending movement | `tests/test_run_lifecycle.py`; verified at `86fad23...`; 78/78 PASS on Windows and Linux | `<checker>` |
| Run collision/no-overwrite | Sequential repeat and same-ID process-race fixtures | Repeat exits nonzero before LLM with all existing hashes unchanged; exactly one process wins the race | `tests/test_run_lifecycle.py`; verified at `86fad23...` | `<checker>` |
| Run lifecycle/abort | completed/aborted/failed lifecycle fixtures and atomic-finalize fixtures | Terminal state is explicit and failed/aborted runs cannot silently appear completed | `tests/test_run_lifecycle.py`; `tests/test_validate_run.py`; verified at `86fad23...` | `<checker>` |
| Same-instance one-shot execution | completed/aborted/failed rerun fixtures and concurrent-thread ownership fixture | Repeats fail before LLM with files/state/RNG/lifecycle unchanged; exactly one concurrent `run()` owns execution | `tests/test_run_lifecycle.py`; verified at `86fad23bc1cddf624550c044348566dc5c212bc7`; 78/78 PASS on Windows and Linux | `<checker>` |
| Untrusted model-output non-execution | Shell/Python/URL-like message fixture | Text is tokenized only; no command, code, file creation, or URL fetch | `test_untrusted_message_is_only_text_and_executes_nothing`; 39/39 targeted PASS at corrected implementation commit `76be872...` | PASS at audited `b7dcf1b...`; corrected candidate recheck pending |
| Additive/backward compatibility | Full unit suite plus protected-path diffs | Existing MVP remains unchanged and all existing tests pass | 117/117 PASS; `engine`, `tools/vocab_metrics.py`, and `output_mvp_demo` diffs empty; prompt SHA unchanged | PASS at audited `b7dcf1b...`; corrected candidate recheck pending |
| Exposure differs from reuse | Delivery-only, same-step, prior-use, multiple-exposure fixtures | Delivery-only is eligible non-reuse; same/prior use excluded; later receiver Phase 1 self-use yields at most one reuse | `tests/test_metric_v2.py`; 39/39 targeted PASS | PASS at audited `b7dcf1b...`; corrected candidate recheck pending |
| Future-information exclusion | Fixed-registry future-text and unsafe discovery-provenance fixtures | Unregistered later text cannot become a candidate or change registered events/status; unsafe registry rejected | `test_unregistered_future_text_does_not_change_registered_events`; registry validation fixtures | PASS at audited `b7dcf1b...`; corrected candidate recheck pending |
| Derived-output collision/provenance | Sequential collision, spawn-process Barrier race, raw-line hash, and raw-directory hash fixtures | Exactly one process owns a fresh result; busy/existing publications collide; raw/final files remain immutable; references match source bytes | `tests/test_metric_v2.py`; process race one success/one collision; raw before/after hashes equal | Normal path PASS at audited `b7dcf1b...`; corrected candidate recheck pending |
| Interrupted derived publication | Failure after each of four data writes, during manifest write, after manifest verification, and abrupt spawned-child termination | Final leaf absent until atomic publish; residual staging is ineligible and does not block retry; OS lock releases on process death; retry yields five manifest-valid files | Seven interruption fixtures in `tests/test_metric_v2.py`; all raw hashes unchanged; 39/39 targeted PASS | FAIL at audited `b7dcf1b...`; corrected candidate recheck pending |
| Fixed candidate registry validation | Registry schema/hash and invalid-registry fixtures | Expected SHA required; duplicates, empty tokens, exclusion conflicts, wrong version, unknown top-level fields, and unsafe discovery flags rejected before publication | Registry validation tests in `tests/test_metric_v2.py` | PASS at audited `b7dcf1b...`; corrected candidate recheck pending |
| Deterministic derived serialization | Two-derived-root byte equality and manifest fixtures | All five required files deterministic; manifest counts and hashes match exact bytes | `test_different_derived_roots_are_byte_identical`; `test_analysis_metadata_and_manifest_are_complete` | PASS at audited `b7dcf1b...`; corrected candidate recheck pending |

- Gate 1 corrected implementation candidate: completed at
  `76be8729a5d3c805bfddaba7a590b80047c6e1b1`; targeted tests 39/39 PASS
  in 6.341 s and full suite 117/117 PASS in 7.296 s on the Windows CPU
  development host; `compileall` and `git diff --check` PASS. The corrected
  candidate has not yet passed independent rechecking and is not a freeze
  record.
- Gate 1 independent checker: `FAIL`.
- Gate 1 freeze: `NOT DONE`.
- Readiness verdict (`NOT READY` until every required gate has evidence):
  `NOT READY`. Gate 1 corrected implementation candidate awaits independent
  recheck; production registry, experimental conditions, pilot seeds,
  communication intervention, parallel transport/backend smoke, matrix runner,
  and run-start approval also remain outstanding.
- Pilot authorization: `NO`.
- Approved run-start window: `NO`; explicit approval remains outstanding.

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
