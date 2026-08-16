# Eight-Cell Matrix Specification

Version: `eight-cell-matrix-v1.0.0`

## 1. Scope

This specification defines the Gate 3 fixed eight-cell experiment bundle,
communication-edge intervention, deterministic planning artifacts, scripted CPU
smoke mode, batch lifecycle, and fail-closed validation boundary. It does not
authorize a pilot or a research run.

## 2. Non-goals

Gate 3 does not freeze production models, a candidate registry, backend
artifacts, pilot seeds, or a run-start approval. It does not test real Ollama,
vLLM, GPU performance, behavioral metrics, topology sweeps, radius sweeps, or
parallel execution of separate runs. It does not change prompts, phase order,
raw-log schema, Metric v2, or Phase-Preserving Parallel Transport semantics.

## 3. Full edge policy

`agents.edge_policy = "full"` preserves the pre-Gate-3 communication rule.
The sender and receiver must be within `communication_radius`. They must both
be outside every place, or both be inside the same named place. Bloc membership
does not affect the boundary. An omitted policy is interpreted as `full` for
backward compatibility.

## 4. Within-bloc-only edge policy

`agents.edge_policy = "within_bloc_only"` first applies the exact same geometry
and place rule as `full`, then requires equal bloc names. It disables cross-bloc
edges while retaining eligible within-bloc edges. It is not a communication-off
condition. Receiver IDs remain unique and in ascending canonical agent-ID order.

## 5. Structural partition

Bloc membership is a structural communication partition only in the
`within_bloc_only` cells. Bloc names, model names, and model identity are never
added to agent prompts. Receiving a message is exposure, not reuse or adoption.

## 6. Fixed cells

Every replicate contains exactly these eight cells:

1. `het-full`
2. `het-within-bloc`
3. `qqq-full`
4. `qqq-within-bloc`
5. `ggg-full`
6. `ggg-within-bloc`
7. `lll-full`
8. `lll-within-bloc`

The cell set and order are normative. HET, QQQ, GGG, and LLL are model
conditions; `full` and `within_bloc_only` are edge policies.

## 7. Canonical order

Replicates execute in plan order. Within each replicate, cells execute in the
order in section 6. Gate 3 has no outer-run parallelism. JSONL planned rows use
the same order, with a zero-based ordinal across the complete matrix.

## 8. Bloc names, order, and counts

The base configuration must contain exactly `alpha`, `beta`, and `neutral`, in
that order, with four agents per bloc. There are twelve agents per run. Bloc
names, order, and counts are paired controls and cannot be plan-controlled.

## 9. Model catalog

The plan contains exactly the slots `qwen`, `gemma`, and `llama`. Each profile
contains `provider`, `model`, and `base_url`, and may contain only
`llm_overrides`, `model_digest`, `quantization`, and `chat_template` in addition.
Provider and base URL must satisfy the simulator's existing validation. Gate 3
tests use placeholders and do not contact them.

## 10. HET rotation

The HET assignment is fixed by zero-based replicate index modulo three:

| Rotation | alpha | beta | neutral |
| ---: | --- | --- | --- |
| 0 | qwen | gemma | llama |
| 1 | gemma | llama | qwen |
| 2 | llama | qwen | gemma |

Index 3 repeats rotation 0. A plan cannot override this mapping.

## 11. Homogeneous assignments

QQQ assigns qwen to all three blocs, GGG assigns gemma to all three, and LLL
assigns llama to all three. The catalog profile is copied into each bloc; model
assignment does not alter bloc names or agent counts.

## 12. Paired world seeds

Each replicate declares one integer `world_seed` (booleans are invalid). All
eight cells in that replicate use it. Replicate IDs are unique. The paired unit
is the set of eight cells for one replicate, not a selection across replicates.

## 13. Plan schema

The plan is UTF-8 JSON with schema
`eight-cell-matrix-plan-v1.0.0`. Duplicate object keys and unknown top-level
fields are rejected. Its exact top-level fields are `schema_version`,
`matrix_id`, `protocol_version`, `metric_version`, `base_config`,
`model_catalog`, `replicates`, `candidate_registry`, and `backend_freeze`.
`metric_version` is `metric-v2.0.0`; protocol cannot be blank or
`unversioned`. The base path is relative, cannot contain `..`, and is pinned by
SHA-256. Matrix and replicate IDs must satisfy the canonical run-ID rules.

Registry and backend records are either `not_frozen` with null evidence, or
`frozen` with respectively a lowercase 64-hex SHA-256 or a non-empty evidence
ID. No production values are committed as part of Gate 3.

## 14. Plan hash

The caller supplies the SHA-256 of the exact plan file bytes. Validation stops
before batch publication if it differs. `plan.json` is a canonical copy; the
source-byte hash remains recorded separately in plan and batch manifests.

## 15. Config generation

For each planned run, the generator records matrix, cell, model condition,
replicate ID/index, rotation, execution mode, run ID/name, seed, protocol,
metric, research eligibility, and effective edge policy. Execution-affecting
defaults are explicit. Generated configs are canonical JSON and immutable after
publication.

## 16. Permitted config differences

Within a replicate, only run ID/name, cell ID, model condition, rotation,
execution mode, edge policy, and the per-bloc provider/model/base URL/overrides/
digest/quantization/chat-template profile may differ. Seed, duration, world,
places, communication and memory settings, sampling, concurrency, thresholds,
protocol, metric, bloc structure, and prompt hash remain paired controls.

## 17. Paired control hash

`paired_control_hash` is SHA-256 over canonical JSON after removing the allowed
cell manipulation fields in section 16 and adding the prompt file-byte hash.
It must be identical across all eight cells of a replicate.

## 18. Initial-state input hash

`initial_state_input_hash` is SHA-256 over canonical world-generation inputs:
world seed, half-space size, places, and ordered bloc names/counts. It must be
identical across the replicate's eight cells. The regression fixture also
constructs simulations and compares actual initial positions.

## 19. Run ID scheme

The exact scheme is `<matrix_id>-<replicate_id>-<cell_id>`. IDs are deterministic,
unique, canonical, and at most 128 characters. There is no truncation, suffix,
or collision recovery.

## 20. Batch layout

The exclusive root is `<output_root>/batch_<matrix_id>`. It contains
`batch_meta.json`, canonical `plan.json`, `planned_runs.jsonl`,
`plan_manifest.json`, `configs/<run_id>.json`,
`runs/output_<run_id>/` raw run artifacts, and `batch_manifest.json`.

## 21. Batch lifecycle

`batch_meta.json` is atomically replaced and has one of `running`, `completed`,
`failed`, or `aborted`. `completed` requires every planned run to complete,
strict validation and smoke validation to pass, the final manifest to exist,
and all pinned hashes to agree. A process interruption records `aborted`; other
execution failures record `failed`.

## 22. No overwrite

The batch root is claimed by exclusive directory creation before any transport
call. An existing path is a collision. Config, plan, planned-row, manifest, run,
and raw files are never replaced or appended by a later batch attempt.

## 23. No resume

Gate 3 implements no resume. Failed, aborted, and not-started evidence is kept.
The same matrix ID cannot be retried; a new experiment requires a new matrix ID.

## 24. Scripted smoke mode

`scripted_smoke` performs no network operation. Each request records one mock
HTTP attempt. Phase 1 emits a non-empty deterministic message derived only from
step and agent ID. Phase 3 stays with empty direction, memory, and reasoning.
The transport does not execute prompt content or include model/bloc names in its
message. Run and batch metadata set `research_eligible` false.

## 25. Research eligibility boundary

A scripted smoke demonstrates orchestration and artifact integrity only. It is
not research eligible and supplies no behavioral evidence. Missing registry,
backend, model artifact, source-cleanliness, protocol-freeze, plan-freeze, or
run-start-approval evidence remains explicitly unverified.

## 26. Research validator profiles

The `smoke` profile requires structural, strict-run, pairing, assignment,
communication-boundary, and manifest integrity and permits declared research
evidence to be unfrozen. The `research` profile applies the same checks and also
requires clean exact source provenance, a non-scripted backend, frozen backend
and registry evidence, complete model artifact details, frozen protocol and
plan, complete batch evidence, and a run-start approval reference.

## 27. Validator exit codes

Research validation returns 0 for PASS under the selected profile, 2 for
UNVERIFIABLE required research evidence, 3 for contradiction/tampering/strict
failure, and 64 for invocation or validator-configuration errors. Runner exits
0 for completed smoke, 1 for failed/aborted execution, 2 for invalid pinned
input, 3 for batch collision, and 64 for invalid invocation.

## 28. Batch manifest

The final manifest lists every planned row, its status, config identity, run
directory, run-meta manifest, raw manifest, strict result, original strict
unverifiable list, smoke result, and research eligibility. It records counts and
the plan/spec/base/prompt pins. `batch_meta.json` records its file SHA-256.

## 29. Failure retention

On failure, the failing raw run and metadata remain. Later planned rows remain
`not_started`. All planned rows appear in the batch manifest. No analyzer or
validator deletes, edits, or repairs these artifacts.

## 30. Deferred outer-run parallelism

Runs execute sequentially in canonical order. Only the already-specified
intra-phase LLM transport concurrency is available. Parallel batch or cell
execution requires a later specification and version change.

## 31. Deferred backend smoke

Real Ollama/vLLM API contract, ordering, artifact identity, and resource smoke
are deferred. Gate 3 makes no backend equivalence, determinism, speed, or GPU
claim.

## 32. Deferred production registry

The production candidate registry is not frozen by Gate 3. Candidate selection,
thresholds, and production hashes cannot be inferred from smoke fixtures.

## 33. Version bump rule

Changing the cell set/order, rotation, edge semantics, bloc composition, paired
unit, run-ID scheme, plan schema, plan/batch manifest schema, eligibility rule,
or validator exit classification requires a matrix-spec version bump and new
regression evidence.

## 34. Regression fixtures

Required CPU fixtures cover edge-policy validation/default/provenance;
full-policy backward compatibility; within-bloc boundary and strict tampering;
plan/hash/base/catalog/replicate/freeze rejection; all fixed cells and rotations;
paired hashes and initial positions; byte-identical static bundles; sequential
and concurrent collision; eight-cell smoke with network guard; success and
failure manifests; failed/aborted/not-started retention; validator exits
0/2/3/64; config/cell/policy/run-ID/seed/manifest/extra/missing/cross-edge
tampering; and raw-run byte immutability.
