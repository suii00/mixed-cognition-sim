# Gate 4 Ollama Endpoint-Reuse Specification

Version: `gate4-ollama-endpoint-reuse-v1.1.0`

Status: `CPU IMPLEMENTED CANDIDATE — REAL WORKLOAD NOT EXECUTED — NO EXECUTION APPROVAL`

## 1. Purpose and claim boundary

This auxiliary workload tests one narrowly defined backend property: after an
exact FP16 model is unloaded from each of three UUID-pinned, loopback-only
Ollama endpoints, the same still-running server process can reload the same
model on the same GPU and answer the current Phase 3 prompt. It follows the
retained three-model prompt-smoke observation but is not Gate 4A-1, Gate 4A-2,
Gate 4A-3, Gate 4A-4, a backend freeze, a pilot, or a research run.

Every result fixes:

```text
execution_mode = reference_ollama
gate4_formal_pass = false
research_eligible = false
backend_freeze.status = not_frozen
```

The workload may report `PASS`, `PASS_WITH_WARNINGS`, `FAIL`, `ABORTED`, or
`MANUAL_REVIEW_REQUIRED`. None of those values changes formal Gate 4 status.
Model output is untrusted text. Generated instructions, code, and URLs are not
executed or fetched.

## 2. Layer separation

The evidence chain is deliberately split:

```text
endpoint-reuse approval
  -> approval-bound orchestrator
  -> endpoint-reuse workload validator
  -> generic Gate 4 publisher
  -> standalone independent bundle verifier
```

The workload validator derives the backend result from captured bytes. The
generic publisher remains structure-only and therefore records
`operational_backend_result=NOT_EVALUATED`; it proves atomic, complete,
hash-bound publication, not endpoint success. The independent verifier proves
the generic publisher commitments S/I/R by a separate read-only code path.

The pre-existing nonconforming `prompt6-20260816T082431Z` bundle is never
edited, corrected, republished, or promoted by this workload.

## 3. Required approval artifact

The only executable approval schema is
`gate4-ollama-endpoint-reuse-approval-v1.0.0`. The approval is canonical JSON,
has no unknown fields, and is supplied with its expected SHA-256. The CLI has
no execution-setting overrides.

The exact top-level fields are:

```text
schema_version
approval_id
approval_reference
approved
evidence_bundle_id
approved_final_path
source_commit_sha
source_dirty
publisher_spec_sha256
publisher_sha256
independent_verifier_sha256
workload_spec_sha256
workload_validator_sha256
orchestrator_sha256
evidence_root
endpoints
num_ctx
num_predict
temperature
parallel_per_endpoint
maximum_generation_calls
maximum_wall_seconds
request_timeout_seconds
cleanup_timeout_seconds
stability_wait_seconds
idle_memory_threshold_mib
required_cleanup
existing_ollama_port
existing_ollama_pid_before
ollama_binary
server_user
allowed_warning_patterns
stop_conditions
```

`approval_id` and `evidence_bundle_id` are the same safe unique identifier.
`approved_final_path` is exactly
`<evidence_root>/published/<evidence_bundle_id>`. The evidence root and final
path are canonical absolute paths. `source_commit_sha` is a full 40-character
Git SHA and `source_dirty=false`. `approved=true` and `required_cleanup=true`.

The endpoint list has exactly these ordered roles and ports:

| Order | Role | Port | Model |
|---:|---|---:|---|
| 1 | `qwen` | 11440 | `qwen2.5:7b-instruct-fp16` |
| 2 | `llama` | 11441 | `llama3.1:8b-instruct-fp16` |
| 3 | `gemma` | 11442 | `gemma2:9b-instruct-fp16` |

Every endpoint supplies one full 64-hex model digest and one exact NVIDIA GPU
UUID. The three UUIDs and model digests are distinct. The fixed request
contract is:

```text
num_ctx = 4096
num_predict = 256
temperature = explicit finite approval value
parallel_per_endpoint = 1
maximum_generation_calls = 6
stream = false
top-level keep_alive = -1
```

`maximum_wall_seconds`, request/cleanup timeouts, stability wait, and an idle
memory threshold are positive bounded values fixed before execution. Warning
patterns are preapproved shell-style full-string globs; an observed warning
cannot be added after the run.

The closed v1 bounds are:

| Field | Inclusive range |
|---|---:|
| `maximum_wall_seconds` | 1--3600 |
| `request_timeout_seconds` | 1--300 |
| `cleanup_timeout_seconds` | 1--300 |
| `stability_wait_seconds` | 1--120 |
| `idle_memory_threshold_mib` | 1--1024 |

The v1 temporary-server identity is exactly `server_user=ollama` and
`ollama_binary=/usr/local/bin/ollama`.

The workload approval is copied byte-for-byte into the attempt. A separate
canonical `approval.json` is a deterministic projection into the generic
publisher's `gate4-gpu-run-approval-v1.0.0` schema. The validator checks the
projection; it is not a second source of authorization.

## 4. Source and artifact preflight

Before any GPU or endpoint action, the orchestrator must verify:

- the supplied approval bytes are canonical and their SHA-256 equals the
  mandatory CLI pin;
- the source tree is clean and HEAD equals the approved commit;
- the publication specification, publisher, independent verifier, workload
  specification, workload validator, and orchestrator hashes equal the
  approval;
- the evidence root and final path equal the approved paths;
- the generation budget is exactly six and the three endpoints are exact;
- no attempt directory, final bundle, or receipt already owns the approval ID.

The real backend preflight then saves and checks:

- `nvidia-smi -L`, GPU state, and compute applications;
- non-interactive `sudo -n` availability for the fixed `ollama` account and
  the exact Ollama CLI version command;
- exact selected UUIDs, idle utilization, approved memory threshold, and no
  selected-GPU compute process;
- ports 11440--11442 unused before temporary startup;
- exact model tags, full digests, F16 quantization, and templates;
- the existing port 11434 API version, empty `/api/ps`, PID identity, and
  process command without stopping or changing it.

Any mismatch stops before the first generation. `nvidia-smi` is a mandatory
outside-sandbox preflight for a real run.

## 5. Workload and six-call budget

The workload uses a complete three-agent, one-step `Simulation.run()` with the
current unchanged prompt source and canonical model order Qwen, Llama, Gemma.
It injects an observational native transport only; Phase snapshots, delivery,
movement, prompt meaning, JSON extraction, and scientific raw logs are not
changed.

The normal sequence is:

```text
Phase 1: Qwen, Llama, Gemma                 3 generation calls
Phase 2: normal delivery barrier
before first Phase 3 transport invocation:
  unload Qwen, Llama, Gemma                administrative calls
  verify all three /api/ps sets are empty
Phase 3: Qwen, Llama, Gemma reload         3 generation calls
Phase 4: normal movement barrier
wait the approved stability interval
re-snapshot all three still-loaded endpoints
final administrative unload and cleanup
```

Unload calls, API probes, process probes, and cleanup operations are counted
separately and never as generation calls. There is no preload generation and
no generation retry. Gate 2 may submit the complete phase for settlement, but
the workload config permits only one in-flight transport worker and a separate
approval execution gate controls every actual backend generation.

The approval-bound generation count is the number of actual
`backend.generate(...)` invocations. It is not the number of submitted
Simulation requests, successful response records, HTTP attempts, retries, or
administrative unloads. Immediately before the backend call, the thread-safe
gate atomically rejects an existing terminal stop, an expired wall deadline,
the wrong next phase/role, an already-active generation, or an exhausted
six-call budget, and then reserves one ordinal. The only successful sequence
is:

```text
phase1:qwen
phase1:llama
phase1:gemma
phase3:qwen
phase3:llama
phase3:gemma
```

The first timeout, transport/backend exception, contract failure, deadline,
budget failure, or invalid sequence latches a one-way terminal reason before
the error leaves the transport. Already queued workers still settle under the
frozen Gate 2 rule, but they record `generation_suppressed` in the transcript
and cannot call the backend. A successful workload has exactly six started
and six completed generations; a failed workload may have fewer but never
more than six actual backend invocations.

Before the first Phase 3 request can unload anything, the same gate atomically
requires: no terminal stop, transcript state `initial_generation_passed`,
exactly three started and three successfully completed Phase 1 generations in
Qwen/Llama/Gemma order, no Phase 3 start, at least three remaining call slots,
and a live wall deadline. A failed precondition leaves both the between-phase
unload count and the Phase 3 generation count unchanged. Only after those
checks may the three administrative unloads start; all three unload responses
must then be verified before Phase 3 reservation is enabled.

## 6. Required state and evidence

The workload transcript has a monotonically increasing sequence and may
advance only through:

```text
planned
preflight_passed
servers_started
initial_generation_passed
models_unloaded
unload_verified
reload_generation_passed
reload_verified
cleanup_passed
```

Publication and verification happen after the captured source closes. An
exclusive external receipt records the subsequent states
`evidence_published` and `evidence_verified`; no file is appended to the final
bundle.

The attempt retains the exact approval, its hash, capture-start metadata,
effective config, transcript, every generation-attempt record, six successful
request/response records, native envelopes, unload responses, per-call and
post-wait stability snapshots, raw API/CLI/GPU/process observations, warning
log, Simulation run directory, strict report, cleanup observation, terminal
result, and workload-validation report. Every owned JSON file is canonical and
every artifact is written exclusively. Failed, aborted, cleanup-failed,
publication-failed, and verification-failed outcomes remain bound to their
unique attempt/receipt paths.

The observations and terminal result also retain the execution-gate budget,
started and completed generation counts, first terminal reason, next expected
phase/role, completed phase/role sequence, and every pre-generation
suppression. Successful validation requires that state to show six started,
six completed, the exact sequence above, no next expected call, no terminal
reason, and no suppression.

## 7. Workload validator acceptance

The validator is read-only except for one new exclusive
`workload-validation.json` output. It independently recomputes the approval
hash, validates all indexed artifact hashes, and requires:

```text
generation calls = 6 exactly
Phase 1 coverage = 3/3
Phase 3 coverage = 3/3
HTTP status = 200 for every generation
done = true for every native envelope
parsed object present for every generation
generation retry = 0
transport failure = 0
final parse failure = 0
unload verified = 3/3
reload verified = 3/3
distinct server PIDs = 3
distinct expected GPU UUIDs = 3
elapsed time <= approved maximum
```

For each endpoint, the initial and reload snapshots must preserve the exact
server PID, port, model tag, full digest, F16 quantization, context 4096, GPU
UUID, and one-GPU runner placement. API `size_vram==size>0` and endpoint CLI
placement `100% GPU` are required. Unload snapshots contain no model and no
unexpected eviction occurs. After `stability_wait_seconds`, a second reload
snapshot must retain the same server and runner PID, digest, context, placement,
and UUID.

Cleanup passes only when temporary models, runners, server PIDs, and ports are
absent; selected GPUs return to utilization zero, no compute process, and
memory at or below the approved threshold; the existing port 11434 PID and
process start time, command, and version are unchanged and its `/api/ps` is
empty. The orchestrator unloads only test-owned models and sends SIGTERM only
to a revalidated exact temporary server PID. It does not escalate automatically
to SIGKILL. The orchestrator never calls
`systemctl`, `service`, `shutdown`, or `reboot`, and never stops PID 373012 or
any approved existing-service PID.

No warnings yields `PASS`. Only warnings matching a preapproved pattern, with
all other checks passing, yields `PASS_WITH_WARNINGS`. An unknown warning
yields `MANUAL_REVIEW_REQUIRED`. Any ERROR, OOM, crash, generation failure,
placement mismatch, cleanup failure, or evidence inconsistency yields `FAIL`.
Keyboard interruption yields `ABORTED`. `PASS_WITH_WARNINGS` is not a formal
Gate 4A pass under this version.

## 8. Publication and independent verification

Only a workload result of `PASS` or `PASS_WITH_WARNINGS` with successful
cleanup is eligible for generic publication. The source includes at minimum:

```text
approval.json
endpoint-reuse-approval.json
endpoint-reuse-approval.sha256
capture-start.json
effective-config.json
orchestrator-transcript.jsonl
artifact-index.json
orchestrator-result.json
workload-validation.json
```

The generic summary remains structure-only and cannot copy the workload PASS
into `operational_backend_result`. The workload validator is rerun read-only on
the publisher staging leaf at the final pre-rename checkpoint. The publisher
then performs its own fresh checks and atomic rename. After publication, the
orchestrator invokes the independently implemented verifier with the publisher
receipt's exact S/I/R and reruns the workload validator against the published
bytes. Only matching S/I/R plus an identical eligible workload result allow the
external receipt to record `evidence_verified`. Publication and verification
exceptions instead receive `publication_failed` or `verification_failed`
external terminal receipts without formal promotion.

Partial attempts are never published. An existing attempt, final bundle,
receipt, approval ID, or evidence bundle ID causes a collision; it is never
overwritten or resumed.

## 9. Required CPU tests before approval

Synthetic tests use an injected backend and prohibit real HTTP, subprocess,
GPU, Ollama, sudo, and network access. They must cover:

- approval hash, source SHA/dirty state, artifact hash, endpoint, UUID, port,
  model digest, budget, path, and wall-time rejection;
- initial request failure, retry, parse failure, unload failure, server PID
  change, reload UUID/digest/context/offload change, unexpected eviction,
  stability drift, unknown/fatal warning, cleanup failure, interruption, and
  existing-service mutation;
- a first-call timeout with the queued Llama and Gemma workers suppressed,
  fake-clock expiry before the second reservation, direct rejection of a
  seventh generation before backend invocation, and early Phase 3 rejection
  before any unload;
- attempt/final/receipt collision and partial-publication rejection;
- one successful six-call fixture through workload validation, generic
  staging validation, publication, independent S/I/R verification, and final
  workload revalidation; exact unload payload and exact-PID TERM tests; and
- retained `gate4_formal_pass=false`, `research_eligible=false`, and
  `backend_freeze.status=not_frozen` in every outcome.

Passing these CPU tests does not authorize the real endpoint-reuse workload.
The real approval artifact must be created after the implementation and
readiness commits, must name that clean HEAD, and must explicitly fix the call,
time, UUID, warning, and cleanup envelope.
