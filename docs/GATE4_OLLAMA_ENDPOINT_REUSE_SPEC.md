# Gate 4 Ollama Endpoint-Reuse Specification

Version: `gate4-ollama-endpoint-reuse-v1.2.1`

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
`gate4-ollama-endpoint-reuse-approval-v1.1.1`. This patch version retains the
v1.1 field shape and adds machine-enforced retired-identity semantics. The
approval is canonical JSON,
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
allowed_warning_events
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
approval uses no substring, regular-expression, shell glob, or whole-line
wildcard matching. An observed event cannot be added after the run.

`allowed_warning_events` is an ordered array of exactly six closed objects.
Each object has exactly:

```text
role
level
source_file
source_line
message
attributes
maximum_occurrences
```

For each approved role and GPU UUID, the two fixed identities are:

```text
runner.go:722 / WARN / user overrode visible devices
  attributes = {"CUDA_VISIBLE_DEVICES": <that role's exact UUID>}

runner.go:726 / WARN /
  if GPUs are not correctly discovered, unset and try again
  attributes = {}
```

Every `maximum_occurrences` is one. Role, level, source file and line, message,
attribute key set, and attribute values are compared exactly. Wildcard
characters, unknown fields, duplicate identities, changed role/UUID binding,
extra attributes, missing entries, and occurrence bounds other than one are
rejected before an attempt. Absence of an approved event is acceptable.

The historical `gate4-ollama-endpoint-reuse-approval-v1.0.0` schema and its
`allowed_warning_patterns` field are rejected by v1.2.1 tooling. Independently
of schema version, SHA, source commit, endpoints, or warning contents, the
executable retired-identity registry rejects
`gate4a-endpoint-reuse-fp16-20260817T124139Z` if it appears as either
`approval_id` or `evidence_bundle_id`. The registry binds the original approval
SHA-256
`b97d603b2e34c0e7157398a916ae6485e60bc6304746cb2189a1db11187756d4`,
status `rejected`, and reason code `warning_policy_overbroad`.

Retirement is evaluated before closed-schema validation, evidence-root or
attempt creation, backend preflight, GPU/API action, or publication. Converting
the historical content to a newer schema cannot revive the identity. The
rejected files remain immutable history and are never an executable registry
source; Markdown is not parsed for enforcement. A future approval must use a
new unique ID.

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

Repository and evidence paths are lexical absolute paths. Missing evidence
components are created without following symlinks; every existing component
is opened from `/` with `O_DIRECTORY|O_NOFOLLOW`. Pinned descriptors for the
repository, attempt/publication/receipt roots, and exclusively created attempt
remain live through validation and publication. A symbolic-link component or
a later device/inode mismatch fails closed. Linux descriptor-relative and
no-follow operations are required by this v1.1 contract.

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
post-wait stability snapshots, raw API/CLI/GPU/process observations, raw server
logs, structured warning events with physical-line hashes, Simulation run
directory, strict report, cleanup observation, terminal
result, workload-validation report, and non-self-referential validation
commitment. Every owned JSON file is canonical and
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

The validator derivation is pure and read-only: it never trusts an existing
`workload-validation.json`. It independently recomputes the approval hash,
validates all indexed artifact hashes, and requires:

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

### 7.1 Physical-line collection and structured diagnostics

The server redirects stdout and stderr into one retained byte log per role.
Collection splits that byte stream only at physical line delimiters. Adjacent
lines are never concatenated, and an embedded line break is never a matchable
event value. The physical line number is counted across all lines, including
ordinary INFO lines that remain in the raw log.

Each WARN/ERROR/FATAL/PANIC or malformed diagnostic-like physical line is
represented by one closed structured event with exactly:

```text
parse_status
role
stream
line_sequence
timestamp
level
source_file
source_line
message
attributes
raw_line_base64
raw_line_sha256
malformation_reason
diagnostic_indicators
```

`role` comes from the server context and `stream` is the fixed
`combined_stdout_stderr`; neither is parsed from model or log text. The raw
field is the exact delimiter-free physical line bytes in base64, and its
SHA-256 is recomputed. The workload validator independently reparses the
indexed `server-logs/<role>.log` bytes and requires exact event-list equality.

Before UTF-8 decoding, a deterministic ASCII-oriented byte classifier scans
only that delimiter-free physical line. ASCII case folding leaves unrelated
non-ASCII and invalid bytes unable to erase surrounding diagnostic tokens. The
authoritative raw bytes and SHA-256 are retained whether decoding succeeds or
fails. The centralized bounded vocabulary recognizes `ERROR`, `FATAL`,
`PANIC`, request failure/failed, watchdog, stale memory with space/hyphen/
underscore separators, unable-to-refresh-free-memory, out-of-memory with
space/hyphen/underscore separators, `OOM`, CUDA error, Xid, segfault, and
crash. Token boundaries prevent matches inside unrelated words.

The logfmt-like parser then consumes the complete line. It requires one unique
`time`, `level`, `source`, and `msg` token, rejects malformed quoting,
unstructured trailing text, duplicate core keys or attributes, invalid UTF-8,
missing timezone, unknown level, and invalid/nonpositive source line. Other
unique key/value tokens become explicit attributes; no remainder is ignored.
INFO and DEBUG remain in the raw log but are not warning-allowlist candidates.

Classification order is raw capture and hash, raw-byte diagnostic extraction,
strict UTF-8 decoding, closed structured parsing, malformed-input handling,
fatal severity/indicator handling, and only then exact WARN identity matching.
An invalid UTF-8 line with a fatal indicator is `FAIL`; invalid UTF-8 without a
recognized fatal indicator is `MANUAL_REVIEW_REQUIRED`. Every invalid UTF-8
line is retained and non-publishable, and none can be an accepted warning.

Severity derives from the single parsed `level` field only after raw-byte
preclassification. Parsed ERROR/FATAL/PANIC, or any structured/malformed record
carrying ERROR, FATAL, PANIC, request-failure, watchdog, stale-memory,
unable-to-refresh-free-memory, OOM/out-of-memory, crash, segfault, CUDA-error,
or Xid evidence, is `FAIL`. A duplicate/mixed severity line is malformed and
`FAIL` whenever a fatal indicator is present. A malformed nonfatal warning-like
line is `MANUAL_REVIEW_REQUIRED`. A parsed WARN is accepted only when its
structured identity exactly equals one of the six approved events and its
occurrence bound is not exceeded. An otherwise unknown WARN, wrong role/UUID/
source/message, extra attribute, or excess occurrence is
`MANUAL_REVIEW_REQUIRED`. None is publication eligible.

An approved WARN on a later physical line may itself be recorded as accepted,
but it can never hide or downgrade an earlier failing line; any error makes the
overall result `FAIL`.

For each endpoint, the initial and reload snapshots must preserve the exact
server PID, port, model tag, full digest, F16 quantization, context 4096, GPU
UUID, and one-GPU runner placement. API `size_vram==size>0` and endpoint CLI
placement `100% GPU` are required. Unload snapshots contain no model and no
unexpected eviction occurs. After `stability_wait_seconds`, a second reload
snapshot must retain the same server and runner PID, digest, context, placement,
and UUID.

Cleanup uses explicit booleans, never error-string matching:

```text
backend_cleanup_passed
final_unloads_complete
temporary_ports_closed
temporary_server_pids_absent
temporary_runner_pids_absent
all_gpus_idle
no_compute_processes
existing_service_unchanged
```

`checks.cleanup=PASS` only when all eight are true. Every final unload must
have HTTP 200, `done=true`, `done_reason=unload`, and an empty post-unload model
set. Temporary models, runners, server PIDs, and ports must be absent; selected
GPUs must return to utilization zero and the approved idle-memory threshold;
no compute process may remain; and the existing port 11434 PID, process start
time, command, version, and empty `/api/ps` must be unchanged. The orchestrator
unloads only test-owned models and sends SIGTERM only to a revalidated exact
temporary server PID. It does not escalate automatically to SIGKILL. It never calls
`systemctl`, `service`, `shutdown`, or `reboot`, and never stops PID 373012 or
any approved existing-service PID.

No diagnostic events yields `PASS`. One or more exact approved structured WARN
events, within each occurrence bound and with all other checks passing, yields
`PASS_WITH_WARNINGS`. A structurally valid but unapproved WARN or malformed
nonfatal warning-like line yields `MANUAL_REVIEW_REQUIRED`. ERROR/FATAL/PANIC,
fatal indicators, generation failure, placement mismatch, cleanup failure, or
evidence inconsistency yields `FAIL`. Keyboard interruption yields `ABORTED`.
`PASS_WITH_WARNINGS` is not a formal Gate 4A pass under this version.

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
workload-validation-commitment.json
```

After pure derivation, the orchestrator exclusively writes canonical
`workload-validation.json`. A separate canonical commitment records its exact
SHA-256, operational result, publication eligibility, fixed Gate/research
boundaries, and original source-attempt `{device,inode}`. The workload artifact
index excludes those two files to avoid self-reference; the generic capture
manifest, generic inventory, and S/I/R include both exact files.

At the source attempt, publisher staging, and published final bundle, the
orchestrator rederives the workload value and requires exact equality with the
persisted canonical bytes and committed SHA, including operational result,
publication eligibility, and fixed Gate/research boundaries. The value retains
the original source identity while each pass separately verifies the currently
opened source, staging, or final identity.

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

The publisher receives exact expected source and publication-root identities;
its receipt returns the source and final published-directory identities. The
standalone verifier independently reopens the lexical final path without
publisher imports and requires that final identity in addition to S/I/R. Final
workload revalidation requires the same identity. A successful external
receipt records both identities plus `workload_validation_sha256`,
`workload_operational_backend_result`, and
`workload_publication_eligible` from the matching final validation.

Partial attempts are never published. An existing attempt, final bundle,
receipt, approval ID, or evidence bundle ID causes a collision; it is never
overwritten or resumed. A concurrent loser receives the controlled
endpoint-reuse collision classification, never raw `FileExistsError`.

## 9. Required CPU tests before approval

Synthetic tests use an injected backend and prohibit real HTTP, subprocess,
GPU, Ollama, sudo, and network access. They must cover:

- approval hash, source SHA/dirty state, artifact hash, endpoint, UUID, port,
  model digest, budget, path, and wall-time rejection;
- initial request failure, retry, parse failure, unload failure, server PID
  change, reload UUID/digest/context/offload change, unexpected eviction,
  stability drift, unknown/fatal warning, cleanup failure, interruption, and
  existing-service mutation;
- all six exact structured warning identities, no-warning PASS, mixed
  ERROR/FATAL plus approved fragments on one line, an approved WARN after an
  ERROR on a second physical line, duplicate severity, appended fatal text,
  malformed quote/key, raw-line hash/trace mismatch, invalid UTF-8 with and
  without fatal ASCII evidence, unknown/request-failure/watchdog/stale-memory
  WARN, all space/hyphen/underscore out-of-memory variants, OOM/crash, wrong
  role/UUID/source/message, extra attributes, and excess occurrence;
- rejection of the historical v1.0 glob approval and static confirmation that
  the warning acceptance path contains no whole-line glob matcher;
- rejection of the historical retired approval and bundle ID under both old
  and current approval schemas before any evidence-root or backend side effect,
  plus a fresh-ID schema-validation-only control;
- a first-call timeout with the queued Llama and Gemma workers suppressed,
  fake-clock expiry before the second reservation, direct rejection of a
  seventh generation before backend invocation, and early Phase 3 rejection
  before any unload;
- attempt/final/receipt collision and partial-publication rejection;
- persisted-validation mutation at source, staging, and final; reverse
  persisted-PASS versus recomputed-FAIL; source/final alternate-inode
  replacement; symlink roots/components; and parent-component identity drift;
- every cleanup subcheck, including final unload `done=false`, and a concurrent
  claim race with exactly one controlled collision;
- one successful six-call fixture through workload validation, generic
  staging validation, publication, independent S/I/R verification, and final
  workload revalidation with all six exact warnings; invalid-UTF8 fatal,
  hyphenated out-of-memory, ERROR/FATAL, and unknown variants that cannot
  publish; exact unload payload and exact-PID TERM tests;
  and
- retained `gate4_formal_pass=false`, `research_eligible=false`, and
  `backend_freeze.status=not_frozen` in every outcome.

Passing these CPU tests does not authorize the real endpoint-reuse workload.
The real approval artifact must be created after the implementation and
readiness commits, must name that clean HEAD, and must explicitly fix the call,
time, UUID, warning, and cleanup envelope.
