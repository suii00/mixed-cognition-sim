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
| `het-full` | Model condition; edge policy | HET rotation; `full`; `docs/EIGHT_CELL_MATRIX_SPEC.md` | Full communication-edge control for HET | `het-within-bloc` at the same replicate/world seed |
| `het-within-bloc` | Model condition; edge policy | HET rotation; `within_bloc_only`; matrix spec | Cross-bloc-edge ablation for HET | `het-full` at the same replicate/world seed |
| `qqq-full` | Model condition; edge policy | QQQ; `full`; matrix spec | Full communication-edge control for QQQ | `qqq-within-bloc` at the same replicate/world seed |
| `qqq-within-bloc` | Model condition; edge policy | QQQ; `within_bloc_only`; matrix spec | Cross-bloc-edge ablation for QQQ | `qqq-full` at the same replicate/world seed |
| `ggg-full` | Model condition; edge policy | GGG; `full`; matrix spec | Full communication-edge control for GGG | `ggg-within-bloc` at the same replicate/world seed |
| `ggg-within-bloc` | Model condition; edge policy | GGG; `within_bloc_only`; matrix spec | Cross-bloc-edge ablation for GGG | `ggg-full` at the same replicate/world seed |
| `lll-full` | Model condition; edge policy | LLL; `full`; matrix spec | Full communication-edge control for LLL | `lll-within-bloc` at the same replicate/world seed |
| `lll-within-bloc` | Model condition; edge policy | LLL; `within_bloc_only`; matrix spec | Cross-bloc-edge ablation for LLL | `lll-full` at the same replicate/world seed |

- Experimental unit: one complete, immutable simulation run.
- Pairing/blocking unit: one replicate/world seed shared by all eight cells.
- Condition assignment procedure: fixed canonical cell order. HET rotates model
  slots across `alpha`, `beta`, and `neutral` by replicate index modulo three;
  QQQ/GGG/LLL assign one slot homogeneously. Production model profiles remain
  `NOT YET FROZEN`.
- World/scenario held constant: within a replicate, the world seed, duration,
  half-space, places, and all non-manipulated config fields are identical and
  checked by `paired_control_hash` and `initial_state_input_hash`.
- Initial-state procedure held constant: all eight cells use the same world
  generation inputs; the CPU regression fixture also compares actual initial
  positions. Production seed values remain `NOT YET FROZEN`.
- Prompt semantics/hash held constant: `engine/prompts.py` is unchanged; SHA-256
  `f414ab30a963636d80239644c2d3770672c77d5b8bdde027de2eb15a0d08bc3d`.
- Sampling parameters held constant: copied from one hash-pinned base config
  and included in the paired-control hash; production values are not frozen.
- Communication rules except the declared intervention held constant: geometry,
  place boundary, canonical ordering, and delivery phase are identical. Only
  cross-bloc edge eligibility differs.
- Agent count and step count held constant: bloc order/count is exactly
  `alpha`, `beta`, `neutral`, four agents each (12 total); step count is copied
  unchanged across paired cells but its production value is not yet frozen.
- Runtime/backend/checkpoint policy: `NOT YET FROZEN`; Gate 3 executes only a
  no-network scripted CPU transport and makes no backend/model claim.
- Prompt contains no bloc/model/self-or-other model identity: confirmed by the
  unchanged prompt hash; edge policy is applied structurally during delivery.
- Prompt contains no desired result, qualitative evaluation, optimization target,
  or behavioral hint: confirmed by the unchanged prompt hash.

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

- Phase-parallelism specification: `docs/PHASE_PARALLELISM_SPEC.md`,
  `phase-parallelism-v1.0.0`, SHA-256
  `77c187277544c116de75273e62d7e13412ad932b38bf9a8e2d5c831347fb105a`.
- Concurrency configuration: `llm_defaults.max_concurrency` is a positive
  integer, defaults effectively to `1`, and is persisted in the owned config
  snapshot and config hash. Concurrency 1 and N use the same bounded threaded
  batch executor.
- Phase 1 snapshot: before dispatch, the coordinator copies every position,
  recent memory/message context, places, applicable place, and occupancy and
  constructs every prompt/request from that common step-start snapshot.
- Evidence that all Phase 1 decisions finish before any delivery: all requests
  are submitted and settled before canonical result commit; Event-blocked
  delivery-barrier and all-prompts-before-dispatch fixtures in
  `tests/test_phase_parallelism.py` observe no delivery, message log, or Phase 3
  request while a Phase 1 worker remains blocked.
- Phase 2 delivery boundary: sequential sender/receiver ID order using the
  Phase 1 step-start position snapshot and the unchanged communication/place
  rule; delivery starts only after all Phase 1 results commit.
- Gate 3 matrix/edge specification, Gate 4 documentation-corrected working
  copy: `docs/EIGHT_CELL_MATRIX_SPEC.md`, `eight-cell-matrix-v1.1.1`, SHA-256
  `fe35f3caeb0b1fc6aeb70f334bfcd05e39a7a79612cbf44e69093e02d3617e1f`.
  The Gate 3 frozen specification bytes and hash remain recorded in section 12
  and at tag `gate3-frozen-20260816`.
- Effective edge policy: `agents.edge_policy` accepts exactly `full` or
  `within_bloc_only`, defaults effectively to `full`, is saved in the owned
  effective config, and contributes to the config hash. Legacy saved configs
  without the field are reconstructed as `full` by the strict validator.
- `full` policy: the Gate 2 distance/place boundary is unchanged and ignores
  bloc membership. This is the paired communication-edge control.
- `within_bloc_only` policy: the same distance/place boundary is applied first,
  then sender and receiver bloc names must match. Cross-bloc edges are disabled,
  while eligible same-bloc communication remains; this is not a
  communication-off condition. Bloc is a structural partition only in this
  ablation, and no bloc or model identity enters prompts.
- Communication-policy regression evidence: omitted versus explicit `full`
  produces byte-identical scientific raw logs and equal state; valid `full` and
  `within_bloc_only` runs pass strict validation; recomputed-manifest fixtures
  with an injected cross-bloc receiver or an omitted expected same-bloc
  receiver fail. Receiver IDs remain canonical.
- Phase 3 snapshot: only after all deliveries, the coordinator copies every
  position, recent memory/message context, place, and occupancy and constructs
  every Phase 3 prompt/request before dispatch.
- Evidence that all Phase 3 decisions finish before memory or movement:
  all requests settle and terminal errors are checked before any Phase 3 state
  or primary-log commit; Event-blocked snapshot/movement fixtures observe
  pre-commit memory and positions while another worker has already completed.
- Phase 4 movement boundary: sequential movement in ascending agent ID using
  only fully committed Phase 3 action/direction results and the unchanged clamp
  rule.
- Deterministic result/log ordering: completion order and internal agent-list
  order are non-semantic; prompt construction, request submission, result/log
  commit, delivery, progress output, and movement use ascending agent ID.
- Coordinator-only mutation: workers receive immutable value requests and
  worker-local telemetry. Lifecycle/counter/log/agent/movement instrumentation
  confirms all shared mutation occurs on the calling coordinator thread.
- Failure semantics: every submitted request settles. Parse failure remains a
  non-terminal logged fallback; a transport failure aborts without partial
  phase commit; an unexpected worker exception takes priority, remains its
  original type, and fails without partial phase commit. The lowest agent ID in
  the selected error class fixes lifecycle context.
- Deterministic equivalence boundary: for the three-agent, two-step scripted
  fixture, concurrency 1 and 3 have byte-identical scientific raw JSONL plus
  equal agent/RNG/counter/manifest/request-transcript state. No equivalent claim
  is made for actual LLM output.
- Ollama reference transport: unchanged `engine.sim.call_ollama`, resolved at
  invocation and supplied only worker-local telemetry. Real network/model calls
  were prohibited in implementation tests.
- vLLM transport/API contract and backend smoke: deferred; no vLLM conformance
  or runtime claim is recorded by Gate 2 implementation evidence.
- Required version consequence: changes to snapshots, phase commit/barriers,
  error selection, ordering, telemetry, concurrency interpretation,
  worker/coordinator ownership, or backend contract require a
  phase-parallelism spec version update and regression evidence. Existing
  protocol, prompt, raw-schema, and metric version rules remain applicable.

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

Gate 1 frozen metric evidence:

- Metric version: `metric-v2.0.0`
- Normative specification: `docs/METRIC_V2_SPEC.md`
- Specification SHA-256:
  `226582354cd777663f5dda0944c66630ba2d7ee30a4cd9bf1ba3b847e895108d`
- Implementation commit:
  `76be8729a5d3c805bfddaba7a590b80047c6e1b1`
- Frozen commit SHA:
  `932f53112189c8e1b6125974bf7ad03ab37e5d4c`
- Freeze tag: `gate1-frozen-20260816`
- Independent checker result for the superseded candidate
  `b7dcf1b877bda3ae83be2d2331719a60cb41432e`: `FAIL`. Metric semantics,
  provenance, registry controls, deterministic output, and normal collision
  handling passed, but interrupted sequential publication could expose a
  completed-marked partial final leaf and block retry.
- Correction scope: derived-result publication lifecycle only. The corrected
  implementation uses a process-death-safe per-run file lock, private staging,
  file `fsync`, manifest revalidation, and atomic publication. Independent
  recheck at the frozen commit passed with no new Critical, High, Medium, or Low
  findings.
- Independent QA report:
  `docs/reviews/gate1_independent_qa_20260816.md`
- Gate 1 implementation: `PASS`.
- Gate 1 independent checker: `PASS`.
- Gate 1 status: `PASS / FROZEN`.
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
- Gate 3 batch path and artifacts: `<output_root>/batch_<matrix_id>/` contains
  atomic `batch_meta.json`, canonical `plan.json`, `planned_runs.jsonl`,
  `plan_manifest.json`, one `configs/<run_id>.json` per planned run,
  `runs/output_<run_id>/` raw run directories, and final
  `batch_manifest.json`.
- Batch no-overwrite rule: the matrix ID claims its batch directory by an
  exclusive create before any transport call. There is no suffix, append,
  overwrite, replacement, or resume; collision requires a new matrix ID.
- Batch lifecycle and manifest: status is `running`, `completed`, `failed`, or
  `aborted` and metadata is atomically replaced. `completed` requires all
  planned runs completed, strict and smoke-profile PASS, plan/config/run hashes
  consistent, and both manifests complete. Plan execution mode is persisted in
  the plan, planned rows, configs, saved run configs, batch metadata, manifest
  top level, and manifest run rows. Batch metadata pins the plan manifest and
  final batch manifest hashes. Eligibility summaries are derived from validated
  evidence and checked after derivation; they are not eligibility inputs.
- Failed/aborted/not-started retention: the failing raw run and every planned
  row are preserved; later rows remain explicitly `not_started`. Validators are
  read-only. The Gate 3 batch manifest covers orchestration/integrity evidence;
  production plans, seeds, registries, backends, and empirical outcomes remain
  unfrozen.
- Null/negative empirical-outcome treatment: not exercised by scripted smoke;
  the production analysis/batch rule remains `<UNFILLED>`.

Raw runs are immutable inputs. Input validation and all derived bytes are built
before publication. A final leaf exists only after all required files and their
manifest have been verified. Residual `.staging` leaves are unpublished,
ineligible, ignored by retry, and not automatically removed by analysis.
`derived_manifest.json` hashes the other required derived files; it is not a
replacement for the Gate 3 run/batch manifest. Conversely, the Gate 3 smoke
manifest does not authorize or complete the unfrozen production analysis plan.

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
| Untrusted model-output non-execution | Shell/Python/URL-like message fixture | Text is tokenized only; no command, code, file creation, or URL fetch | `test_untrusted_message_is_only_text_and_executes_nothing`; 39/39 targeted PASS at implementation commit `76be872...` | PASS at frozen `932f531...` |
| Additive/backward compatibility | Full unit suite plus protected-path diffs | Existing MVP remains unchanged and all existing tests pass | 117/117 PASS; `engine`, `tools/vocab_metrics.py`, and `output_mvp_demo` diffs empty; prompt SHA unchanged | PASS at frozen `932f531...` |
| Exposure differs from reuse | Delivery-only, same-step, prior-use, multiple-exposure fixtures | Delivery-only is eligible non-reuse; same/prior use excluded; later receiver Phase 1 self-use yields at most one reuse | `tests/test_metric_v2.py`; 39/39 targeted PASS | PASS at frozen `932f531...` |
| Future-information exclusion | Fixed-registry future-text and unsafe discovery-provenance fixtures | Unregistered later text cannot become a candidate or change registered events/status; unsafe registry rejected | `test_unregistered_future_text_does_not_change_registered_events`; registry validation fixtures | PASS at frozen `932f531...` |
| Derived-output collision/provenance | Sequential collision, spawn-process Barrier race, raw-line hash, and raw-directory hash fixtures | Exactly one process owns a fresh result; busy/existing publications collide; raw/final files remain immutable; references match source bytes | `tests/test_metric_v2.py`; process race one success/one collision; raw before/after hashes equal | PASS at frozen `932f531...` |
| Interrupted derived publication | Failure after each of four data writes, during manifest write, after manifest verification, and abrupt spawned-child termination | Final leaf absent until atomic publish; residual staging is ineligible and does not block retry; OS lock releases on process death; retry yields five manifest-valid files | Seven interruption fixtures in `tests/test_metric_v2.py`; all raw hashes unchanged; 39/39 targeted PASS | PASS at frozen `932f531...` |
| Fixed candidate registry validation | Registry schema/hash and invalid-registry fixtures | Expected SHA required; duplicates, empty tokens, exclusion conflicts, wrong version, unknown top-level fields, and unsafe discovery flags rejected before publication | Registry validation tests in `tests/test_metric_v2.py` | PASS at frozen `932f531...` |
| Deterministic derived serialization | Two-derived-root byte equality and manifest fixtures | All five required files deterministic; manifest counts and hashes match exact bytes | `test_different_derived_roots_are_byte_identical`; `test_analysis_metadata_and_manifest_are_complete` | PASS at frozen `932f531...` |
| Worker purity / coordinator-only mutation | Worker-local telemetry blocking fixture and shared-mutation instrumentation | Workers touch no lifecycle, simulation counter, log, agent state, or movement path; coordinator reflects settled facts | `tests/test_phase_parallelism.py`; 19/19 targeted PASS at implementation commit `4f893b3...` | PASS at frozen `34c6b80...` |
| Phase 1 batch barrier | All-prompts-before-dispatch, blocked-delivery, reverse-completion, and terminal-failure fixtures | Common step-start snapshot; every request settles before canonical Phase 1 commit or any delivery; terminal failure publishes no Phase 1 result | `tests/test_phase_parallelism.py`; deterministic CPU scripted transports | PASS at frozen `34c6b80...` |
| Phase 3 batch barrier | Post-delivery snapshot, blocked-memory/movement, parse, and terminal-failure fixtures | Common post-delivery snapshot; every result settles before memory/log commit; all Phase 3 commits precede movement; terminal failure publishes no Phase 3 result | `tests/test_phase_parallelism.py`; existing lifecycle barrier fixtures retained | PASS at frozen `34c6b80...` |
| Concurrency 1/N scripted equivalence | Three-agent, two-step deterministic scripted scenario at concurrency 1 and 3 | Four scientific raw files byte-identical; agent/RNG/counter/observed/manifest state and exact request transcript equal | `test_concurrency_one_and_n_are_deterministically_equivalent` | PASS at frozen `34c6b80...` |
| Deterministic result ordering | Reverse worker completion and reversed internal agent-list fixtures | Request/result identity remains mapped; raw logs, lifecycle observation, progress, delivery receiver IDs, state, and movement commit in agent-ID order | `test_reverse_completion_commits_canonical_order`; `test_agent_list_order_is_not_semantic` | PASS at frozen `34c6b80...` |
| Transport-failure phase atomicity | Phase 1/3 blocked multi-request failures and multiple-error fixtures | All requests and telemetry settle; no primary log/state partial commit; deterministic minimum failing agent; executor threads release | Gate 2 targeted suite at `4f893b3...` | PASS at frozen `34c6b80...` |
| Unexpected-worker-failure handling | Mixed transport/unexpected and multiple-unexpected fixtures | Unexpected error wins over transport, original type is re-raised, minimum unexpected agent fixes context, no partial commit or thread leak | Gate 2 targeted suite at `4f893b3...` | PASS at frozen `34c6b80...` |
| Effective concurrency provenance | Omitted/explicit/invalid settings, caller-ownership, persisted snapshot, and config-hash fixtures | Effective positive integer is owned and persisted; invalid types/values rejected; different concurrency changes config hash | Gate 2 targeted suite at `4f893b3...` | PASS at frozen `34c6b80...` |
| Communication edge-policy validation | Default/explicit/invalid config, backward-compatible full, within-bloc delivery, and recomputed-manifest tamper fixtures | Effective policy is owned, persisted, and hashed; full preserves the old boundary; within retains same-bloc and rejects cross-bloc delivery | `tests/test_communication_policy.py`; 5/5 PASS at `c782356...` | PASS at frozen `24b1ceb...` |
| Fixed eight-cell generation | One-replicate canonical generation and exact cell/order fixtures | Exactly HET/QQQ/GGG/LLL × full/within in the normative eight-row order | `tests/test_eight_cell_runner.py`; implementation `c782356...` | PASS at frozen `24b1ceb...` |
| HET model-to-bloc rotation | Replicate indices 0, 1, 2, and 3 plus homogeneous assignment fixtures | HET uses the fixed modulo-three rotation; QQQ/GGG/LLL use one slot for all blocs | `test_fixed_cells_rotations_homogeneous_and_paired_hashes` | PASS at frozen `24b1ceb...` |
| Paired seed/config invariants | Eight generated configs, paired hashes, world-input hashes, and constructed initial positions | Seed, non-manipulated config, prompt hash, world inputs, and actual initial positions agree across each paired replicate | `test_paired_configs_produce_identical_initial_positions`; paired-hash assertions | PASS at frozen `24b1ceb...` |
| Deterministic plan/config bundle | Same plan rendered under two temporary roots | Canonical plan, rows, configs, and plan manifest are byte-identical and contain no runtime path or timestamp | `test_static_bundle_is_byte_identical_across_roots` | PASS at frozen `24b1ceb...` |
| Eight-cell scripted CPU smoke | 12 agents, one temporary replicate, deterministic no-network transport | 8/8 complete and strict/smoke valid; full has cross-bloc delivery; within has same-bloc and zero cross-bloc delivery | `test_eight_cell_smoke_manifest_policies_and_sequential_collision` | PASS at frozen `24b1ceb...` |
| Batch manifest completeness | Successful and injected-failure batches | Every planned row, status, config/run/raw/validator evidence, and manifest pin is retained; incomplete batches never report completed | runner and research-validator targeted suites at `c782356...` | PASS at frozen `24b1ceb...` |
| Batch collision/no-overwrite | Sequential byte-hash check and concurrent CLI process claim | Repeat transport calls remain zero and bytes unchanged; concurrent claims yield exactly one owner and one collision | sequential and concurrent collision fixtures | PASS at frozen `24b1ceb...` |
| Smoke-profile run validation | Strict validation, assignment/policy/pairing checks, shared batch authority, read-only complete-tree hashes, and CLI exits | Valid scripted run/batch exits 0 with `research_eligible=false`; canonical batch contradictions and tampering exit 3 for both scopes | `tests/test_research_validator.py`; 18/18 PASS in 37.473 s in independent QA | PASS at frozen `24b1ceb...`; prior FAILs retained |
| Complete execution-mode evidence chain | Plan, planned row, config, saved run config, batch metadata, manifest top, manifest row, and validator-result fixtures with ordinary hashes recomputed | Plan is authoritative; every completed layer is present and unanimous; missing/invalid/conflicting evidence exits 3 | execution-mode propagation, seven-layer conflict, and seven-layer missing-field fixtures at `7b4b3e8...` | PASS at frozen `24b1ceb...`; prior Medium retained |
| Research-profile fail-closed eligibility | Scripted control, zero-network synthetic positive control, approval-only and consistently-unfrozen controls, stale summaries, plan/metadata freeze conflict, and unselected invalid-run fixtures | Scripted and missing evidence exit 2; consistent synthetic logic exits 0/true; all contradictions exit 3; another required run can block the selected run | independent QA: 10 fixtures, all eight run IDs, 0 implication violations | PASS at frozen `24b1ceb...`; prior Medium/High retained |
| Shared public run/batch research authority | Every planned run ID in positive, plan-freeze conflict, consistently-unfrozen, stale batch-summary, missing-approval, and unselected-invalid fixtures | Public run research PASS implies public batch research PASS; batch exit 3 never permits run exit 0; run eligibility is selected-run eligibility AND batch eligibility | independent QA: 187 read-only tree-hash checks, 0 changed trees, 0 network calls | PASS at frozen `24b1ceb...`; prior High retained |
| Research-validator process exits/help | Public batch/run CLI fixtures for exits 0/2/3/64, shared plan-freeze conflict, and top-level argparse help | Printed classification matches process exit; conflicting batch/run both exit 3; `--help` exits 0, writes stdout help, and leaves stderr empty | independent QA process checks at `24b1ceb...` | PASS at frozen `24b1ceb...`; prior Low retained |

- Gate 1 status: `PASS / FROZEN`.
- Gate 1 frozen commit:
  `932f53112189c8e1b6125974bf7ad03ab37e5d4c`.
- Gate 1 freeze tag: `gate1-frozen-20260816`.
- Gate 1 implementation commit:
  `76be8729a5d3c805bfddaba7a590b80047c6e1b1`.
- Gate 1 independent checker: `PASS`; full suite 117/117 PASS in 7.423 s
  unittest time (7.986 s wall), targeted Metric v2 suite 39/39 PASS in
  4.952 s unittest time (5.133 s wall), `compileall` PASS, and
  `git diff --check` PASS. The full report is retained at
  `docs/reviews/gate1_independent_qa_20260816.md`.
- Gate 2 status: `PASS / FROZEN`.
- Gate 2 frozen commit:
  `34c6b802958781b9a8d25420742e092a8a0bee3c`.
- Gate 2 freeze tag: `gate2-frozen-20260816`.
- Gate 2 implementation commit:
  `4f893b3926db37e508b49dadbf47f1372bec3ed6`.
- Gate 2 specification: `docs/PHASE_PARALLELISM_SPEC.md`,
  `phase-parallelism-v1.0.0`, SHA-256
  `77c187277544c116de75273e62d7e13412ad932b38bf9a8e2d5c831347fb105a`.
- Gate 2 implementation evidence: targeted suite 19/19 PASS in 0.483 s
  unittest time (0.725 s wall); lifecycle suite 33/33 PASS in 1.142 s
  unittest time (1.373 s wall); provenance suite 28/28 PASS in 0.120 s
  unittest time (0.345 s wall); full suite 136/136 PASS in 8.381 s
  unittest time (8.691 s wall); `compileall`, `git diff --check`, and protected
  Gate 1 path comparisons PASS.
- Gate 2 prompt SHA-256:
  `f414ab30a963636d80239644c2d3770672c77d5b8bdde027de2eb15a0d08bc3d`
  (unchanged).
- Gate 2 Metric v2 specification SHA-256:
  `226582354cd777663f5dda0944c66630ba2d7ee30a4cd9bf1ba3b847e895108d`
  (unchanged).
- Gate 2 independent checker: `PASS`; full suite 136/136 PASS in 7.978 s
  unittest time (8.614213 s wall), targeted Gate 2 suite 19/19 PASS in
  0.419 s unittest time (0.673850 s wall), `compileall` PASS, and
  `git diff --check` PASS. Independent probes also passed for strict-validator
  compatibility, worker purity, phase barriers, deterministic failure
  selection, counter taxonomy, thread release, and scripted concurrency 1/N
  equivalence. No Critical, High, Medium, or Low findings were reported.
- Gate 2 independent QA report:
  `docs/reviews/gate2_independent_qa_20260816.md`.
- Gate 2 verification used no GPU, real LLM, Ollama/vLLM service, external
  network request, or research run.
- Gate 3 status: `PASS / FROZEN`.
- Gate 3 frozen commit:
  `24b1ceba917f9853779b788d5ccab88c9c227c7b`.
- Gate 3 freeze tag: `gate3-frozen-20260816`.
- Gate 3 original implementation commit:
  `c782356c596443b595f6383e568eea9e97ae1250`.
- Gate 3 execution-evidence correction commit:
  `6e1d13e3313e0bf35537db5352df61e261e8417e`.
- Gate 3 complete execution-chain and eligibility-consistency correction commit:
  `7b4b3e8d6bf9b45f71ece624b04053f32bcfaefb`.
- Gate 3 shared run/batch eligibility correction commit:
  `88e462c9c079cc874023b4515082c976f0125752`.
- Gate 3 specification: `docs/EIGHT_CELL_MATRIX_SPEC.md`,
  `eight-cell-matrix-v1.1.1`, SHA-256
  `96a4ddefbef7a7c9ab8d5a41cb6d438edd7a18b20c78e8154681ac9c61c44e5a`.
- Gate 3 schema family at the current correction remains: matrix plan
  `eight-cell-matrix-plan-v1.1.0`; batch manifest
  `eight-cell-batch-manifest-v1.1.0`.
- Gate 3 pre-correction baseline at `1cb5e870...`: full suite 160/160 PASS in
  18.839 s unittest time (19.348260 s wall); `compileall` and
  `git diff --check` PASS.
- Gate 3 corrected implementation evidence: research-validator suite 14/14
  PASS in 14.479 s unittest time (14.968267 s wall); eight-cell runner suite
  11/11 PASS in 5.061 s (5.550959 s wall); communication-policy suite 5/5 PASS
  in 0.287 s (0.812491 s wall); Phase-Preserving Parallelism suite 19/19 PASS
  in 0.517 s (1.009642 s wall); Metric v2 suite 39/39 PASS in 5.066 s
  (5.571852 s wall); strict-validator suite 17/17 PASS in 0.756 s
  (1.356936 s wall); full suite 166/166 PASS in 24.317 s (24.831845 s wall).
  `compileall`, `git diff --check`, and starting-SHA protected-path comparisons
  PASS.
- Gate 3 shared-authority correction baseline at `7257fcc...`: full suite
  166/166 PASS in 25.391 s unittest time (25.9575131 s wall), `compileall`
  PASS, `git diff --check` PASS, and clean worktree.
- Gate 3 shared-authority correction evidence at `88e462c...`:
  research-validator suite 18/18 PASS in 35.928 s; eight-cell runner suite
  11/11 PASS in 5.494 s (6.017487 s wall); communication-policy suite 5/5
  PASS in 0.299 s (0.799805 s wall); Phase-Preserving Parallelism suite 19/19
  PASS in 0.550 s (1.137919 s wall); Metric v2 suite 39/39 PASS in 5.251 s
  (5.674729 s wall); strict-validator suite 17/17 PASS in 0.813 s
  (1.333270 s wall); full suite 170/170 PASS in 47.572 s. `compileall`,
  `git diff --check`, and Gate 0--2 protected-path comparisons PASS.
- Gate 3 execution-mode evidence now covers plan, planned rows, generated
  configs, saved run configs, batch metadata, batch-manifest top level,
  batch-manifest run rows, and per-run/batch validator results. The plan is the
  authority; missing or conflicting completed evidence exits 3.
- Gate 3 eligibility evidence is derived before persisted summaries are
  compared. A stale false and an unsupported true both exit 3; summaries cannot
  promote or demote the derivation. A consistent non-scripted fixture missing
  only approval exits 2. The fully positive `reference_ollama` fixture exits 0
  with derived/persisted true only as a synthetic validator-logic control; it
  performs no backend or network call and is not research evidence.
- Gate 3 public run and batch reports now construct the same read-only validated
  batch authority context. It binds the plan, rows, configs, batch metadata,
  batch manifest, every planned run, cross-layer authority findings, derived
  per-run eligibility, derived batch eligibility, and persisted summaries. A
  public run's effective eligibility is its selected-run eligibility AND the
  enclosing batch eligibility.
- Gate 3 shared-authority regressions mechanically observed: plan versus
  metadata registry/backend freeze conflicts yield exit 3 for the batch and
  every selected run; consistently not-frozen evidence yields exit 2 for both;
  stale batch-metadata and batch-manifest top summaries yield exit 3 for every
  run; an invalid unselected run blocks an otherwise individually eligible
  selected run. Every validation leaves the complete fixture tree byte-
  identical, and guarded `requests.post` call count is zero.
- Gate 3 CLI evidence includes process exits 0/2/3/64; normal
  `python -m tools.research_validator --help` exits 0 with help on stdout and
  empty stderr.
- Gate 3 independent checker: `PASS` at
  `24b1ceba917f9853779b788d5ccab88c9c227c7b`; full suite 170/170 PASS in
  48.895 s unittest time (49.219 s wall), targeted research-validator suite
  18/18 PASS in 37.473 s (37.745 s wall), `compileall` PASS, and
  `git diff --check` PASS. Ten independent eight-run fixtures produced zero
  run/batch implication violations, 187 read-only complete-tree checks produced
  zero changed trees, and guarded `requests.post` count was zero. The full
  report is retained at
  `docs/reviews/gate3_independent_recheck_20260816.md`.
- Gate 3 known non-blocking Low at freeze: frozen matrix specification section
  28 abbreviates the plan schema as `eight-cell-plan-v1.1.0`; the canonical
  implementation, artifacts, tests, and protocol use
  `eight-cell-matrix-plan-v1.1.0`. After creating the frozen tag, the Gate 4
  working copy corrected that documentation-only cross-reference and now has
  SHA-256 `fe35f3caeb0b1fc6aeb70f334bfcd05e39a7a79612cbf44e69093e02d3617e1f`.
  The Gate 3 frozen tag retains the audited pre-erratum hash
  `96a4ddefbef7a7c9ab8d5a41cb6d438edd7a18b20c78e8154681ac9c61c44e5a`.
- Gate 3 evidence boundary: the eight-cell smoke used only temporary plans,
  placeholder model profiles, paired test seed 1001, and a scripted CPU
  transport. It performed no GPU, real LLM, Ollama/vLLM service, external
  network request, model download, package installation, or research run.
- Gate 3 independent checker: `FAIL` at audited candidate
  `255e50798bef1ed2f9136c1e78a2ed8e6e7da849`. The Critical finding was that a
  batch-only execution declaration could promote underlying `scripted_smoke`
  runs to research PASS. That SHA is not a freeze candidate. The full report is
  retained at `docs/reviews/gate3_independent_qa_fail_20260816.md`.
- Gate 3 first corrected-candidate independent recheck: `FAIL` at audited
  candidate `1cb5e8702b92537ecc2157588bdb435a81a0b060`. The remaining findings
  were incomplete plan/manifest execution-mode layers and a positive-path
  persisted/derived eligibility inconsistency (Medium), plus argparse help
  exit 64 (Low). That SHA is not a freeze candidate. The full report is retained
  at `docs/reviews/gate3_independent_recheck_fail_20260816.md`.
- Gate 3 second corrected-candidate independent recheck: `FAIL` at audited
  candidate `7257fccda2f4f744d71225429f6a3f7542230af7`. The High finding was that
  public run validation could return research PASS while the enclosing batch
  failed plan/metadata authority or stale batch-summary checks. That SHA is not
  a freeze candidate. The supplied finding is retained at
  `docs/reviews/gate3_independent_recheck_run_batch_fail_20260816.md`.
- Gate 3 final independent recheck: `PASS` at audited candidate
  `24b1ceba917f9853779b788d5ccab88c9c227c7b`. The non-blocking Low
  documentation erratum is retained; no implementation or eligibility finding
  remains open at Gate 3 freeze.
- Gate 3 freeze: `PASS / FROZEN` at tag `gate3-frozen-20260816`.
- Production candidate registry: `NOT YET FROZEN`.
- Backend/model artifacts: `NOT YET FROZEN`.
- Readiness verdict (`NOT READY` until every required gate has evidence):
  `NOT READY`. Gates 1, 2, and 3 are frozen. Production registry, production
  model/backend artifacts, experimental values, pilot seeds, and run-start
  approval remain outstanding.
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
