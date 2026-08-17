# Gate 4 Backend Evidence Ledger

Version: `gate4-backend-evidence-ledger-v1.5.0`

Status: `WORKING CANDIDATE INDEX — NOT A BACKEND FREEZE`

## 1. Ledger boundary

This ledger indexes scope-limited backend evidence on the Gate 4 working
branch. An entry-level PASS applies only to the scope stated in that entry. It
does not set `backend_freeze.status` to `frozen`, establish a formal Gate 4
PASS, freeze the production candidate registry or model artifacts, authorize a
pilot or research run, or make an artifact research-eligible.

The external evidence tree and the hashes recorded here remain the evidence
authority. This ledger is an index, not a replacement for raw artifacts. The
Gate 3 tag, frozen Gate 3 bytes, and historical Gate 3 review records are not
modified by this Gate 4 ledger.

## 2. Candidate `pinned3-20260816T071057Z`

- Evidence ID: `pinned3-20260816T071057Z`
- Evidence class: `capacity_preflight`
- Evidence root:
  `/home/iitsuka/mcs-backend-smoke/ollama-residency-fp16/pinned3-20260816T071057Z`
- Evidence schema:
  `ollama-uuid-pinned-three-endpoint-residency-smoke-v1.0.0`
- Scope result:
  `PASS — UUID-pinned three-endpoint simultaneous residency and cleanup only`
- Artifact state: `candidate / not frozen`
- Gate 4 formal pass: `false`
- Research eligible: `false`
- Source checkout at capture:
  `6a2950b7c7092e693fed3b03e336f67897a993fc`, `dirty=true`
- Corrected summary: `run-summary.json`, SHA-256
  `8de870da8026bab963d910d97df51ac7e0f6f63070b5dc589e11db301f7c46a6`
- Inventory: `files.sha256`, SHA-256
  `e22f09ced22311c40bfe5fd6d6b24b13afffac62299809328f005aa8e8def415`
- Read-only integrity recheck: `140/140 inventory entries PASS`. The evidence
  directory contains 141 files because the inventory does not list itself.

### 2.1 Directly observed deployment

| Endpoint | Exact model tag | Full model digest | Quantization | Physical GPU | GPU UUID | Observed GPU memory |
|---|---|---|---|---:|---|---:|
| `127.0.0.1:11440` | `qwen2.5:7b-instruct-fp16` | `59805ce4a4046be2d8f63231a78daacd2e66f5dccf1a64d0d138ebeeb26ff16c` | `F16` | 0 | `GPU-720e6563-7e95-65c4-659e-189ba0c7bac5` | 14,107 MiB |
| `127.0.0.1:11441` | `llama3.1:8b-instruct-fp16` | `4aacac4194543ff7f70dab3f2ebc169c132d5319bb36f7a7e99c4ff525ebcc09` | `F16` | 6 | `GPU-2964f342-8734-a701-a2c6-4344579b03ee` | 15,185 MiB |
| `127.0.0.1:11442` | `gemma2:9b-instruct-fp16` | `28e6684b085085f78551db7c96a9daa546161b1da9d055ea01b84cb1163013cf` | `F16` | 7 | `GPU-af1ef9b0-329f-ff38-d4dd-062e2beca9e0` | 19,337 MiB |

The three endpoints had distinct server and runner processes. At both retained
three-model checkpoints, every endpoint reported the expected exact tag and
digest, `context_length=4096`, and `size_vram == size`; the observed compute
applications used exactly the three selected GPU UUIDs. Each endpoint returned
one generic native `/api/chat` response with HTTP 200 and `done=true`. The
three models remained resident across the two sequentially captured
checkpoints without observed eviction.

Here, full GPU residency means the recorded Ollama placement and
`size_vram == size`. It does not mean that Ollama used no host-side mapped
buffer or no host RAM.

Cleanup evidence records model unloads, closure of temporary ports
`11440`--`11442`, disappearance of the three temporary server PIDs, continued
operation of the existing `127.0.0.1:11434` process, an empty final compute-app
list, and the recorded one-MiB idle baseline on all eight GPUs. No machine
shutdown, reboot, `systemctl` action, or restart of the existing Ollama service
was part of this preflight.

### 2.2 Mechanical derivation and correction chain

The corrected summary derives `residency_status=passed`,
`cleanup_status=passed`, and `overall_status=passed` from the retained raw
artifacts. It declares:

```text
derivation_correction.supersedes = run-summary-v1-invalid.json
reason = v1 idle parser used memory.total column index 2 instead of
         memory.used column index 3
raw_artifacts_changed = false
```

The superseded derivative `run-summary-v1-invalid.json` has SHA-256
`95bef8a9db1c46e060b83b4347e5adc97e88b7848bd7874ddba0caf48c3e37db`.
Both derivatives are retained and inventory-pinned. The superseded file does
not itself contain `status` or `superseded_by`; the relationship is declared by
the corrected `run-summary.json` and this ledger. The superseded derivative
must not be used as the current status record.

### 2.3 Claim boundary and outstanding work

This candidate establishes only the recorded three-endpoint capacity,
UUID-isolated simultaneous model residency, one generic completed request per
endpoint, and cleanup envelope. It did not exercise or verify:

- the current Phase 1 or Phase 3 simulation prompts;
- `engine.sim.call_ollama`, JSON compatibility for those prompts, or complete
  simulator retry and failure telemetry;
- simulation barriers, delivery, movement, or a strict simulation run;
- simultaneous generation, `max_concurrency > 1`, queue behavior, or sustained
  operation;
- twelve-agent execution, deterministic replica routing, load balancing,
  failure isolation, or the seven-replica 2/2/3 topology;
- any eight-cell batch, Gate 4A-1 through Gate 4A-4, or the Ollama
  reference-backend evidence freeze;
- vLLM conformance, pilot readiness, production model-artifact freeze, or
  research eligibility.

The candidate used the three FP16 tags and three-endpoint deployment recorded
above plus a generic `Reply with exactly OK.` request. It is therefore an
auxiliary preflight, not a silent substitution for the model, prompt, agent
count, or deployment conditions in `docs/GATE4_BACKEND_SMOKE_SPEC.md`.

## 3. Candidate `prompt6-20260816T082431Z`

- Evidence directory ID: `prompt6-20260816T082431Z`
- Simulation run ID: `prompt6-fp16-20260816T082929Z`
- Core evidence ID:
  `prompt6-7180259ce316f240956c19fb502d0dea3f9ff8157b989421484bc326fde9d2fd`
- Evidence class: `fp16_three_endpoint_current_prompt_auxiliary_smoke`
- Evidence root:
  `/home/iitsuka/mcs-backend-smoke/ollama-prompt-smoke-fp16/prompt6-20260816T082431Z`
- Summary schema:
  `ollama-fp16-three-endpoint-prompt6-summary-v1.0.0`
- Operational backend result:
  `PASS_WITH_WARNINGS — six-call simulation prompt path, post-run residency,
  and effective cleanup only`
- Evidence publication conformance:
  `NONCONFORMING / NOT FORMALLY ACCEPTED — retained evidence-contract
  deviations in section 3.4`
- Formal Gate 4A result: `NOT PASSED / NOT FROZEN`
- Artifact state: `candidate / not frozen`
- Gate 4 formal pass: `false`
- Research eligible: `false`
- Source checkout at capture:
  `6a2950b7c7092e693fed3b03e336f67897a993fc`, `dirty=true`
- Summary: `run-summary.json`, SHA-256
  `ae60cb93858b1d354b669996a12ffa02d15b8889fd04a879deefbc3849db40eb`
- Inventory: `files.sha256`, SHA-256
  `236ce80c376ace991064e2cba3fbefc009a3d6f4ec5bc73ef4ae3336974ab3d5`
- Read-only integrity recheck: `235/235 inventory entries PASS`; the path set
  excluding the self-excluded inventory is exactly 235 files.

The attempt was approved in advance for exactly three selected GPUs, six
logical generation calls, a 15-minute ceiling, explicit stop conditions, and
the fresh evidence root above. Its immutable pre-execution source snapshot
pins `docs/GATE4A_FP16_THREE_ENDPOINT_PROMPT_SMOKE_SPEC.md` version
`gate4a-fp16-three-endpoint-prompt-smoke-v1.0.0`, SHA-256
`0e24765e78b858a0cbf27e6f66a0cc745aa188c3fb52ab1dafa51559352c6cee`,
and the then-current ledger SHA-256
`63a536000beadb79cecefd5d411229fa1d17bc1a35026b17edaf50c534594f57`.
This post-execution ledger entry does not rewrite either captured byte set.

### 3.1 Directly observed prompt-path result

The captured runner invoked and completed one full `Simulation.run()` lifecycle
for the declared three-agent, one-step configuration. It produced exactly three
Phase 1 and three Phase 3 calls in canonical agent order. All six calls used the
unchanged `engine/prompts.py` bytes, native `/api/chat`, explicit
`num_ctx=4096`, top-level `keep_alive=-1`, `temperature=0.2`,
`num_predict=256`, and global concurrency one. The retained evidence records:

```text
run status = completed
expected/completed steps = 1/1
expected/observed agents = 3/3
logical calls = 6
HTTP attempts / HTTP 200 / done=true = 6 / 6 / 6
parsed non-null objects = 6/6
generation retries = 0
transport failures = 0
syntax parse-attempt failures = 0
final syntax parse failures = 0
schema-validation failure counter = 0
strict validator = valid, errors=[]
strict validator unverifiable findings retained = 9
```

The run contains three `phase1_raw.jsonl` rows and the two expected
`messages.jsonl` rows. Agent 0 returned an empty message, so its absence from
the delivery log is expected. The strict validator reconstructed the delivery
boundary from the Phase 1 decisions, world positions, communication radius,
and full edge policy; both retained message records matched it. The exact Phase
3 prompts also contain the delivered messages, directly showing that Phase 2
delivery preceded the Phase 3 snapshot. Three `memory_reasoning.jsonl` rows
record the Phase 3 action and memory values, and the captured execution output
contains one Phase 4 movement line for each agent before the completed-run
message. Terminal `run_meta.json` records `status=completed`, `aborted=false`,
and full step/agent coverage, and the subsequent in-process strict validation
records `valid=true` and `errors=[]`.

Per-call monotonic timestamps show no overlap and place the first Phase 3 call
after the last Phase 1 call. The six raw HTTP bodies equal the retained decoded
native envelopes, and each envelope's content equals its retained raw model
output. The additional parsed-object shape diagnostic reported no mismatch.
That diagnostic is not a substitute for engine-level semantic schema
validation, which remains unsupported and explicitly unverifiable. Gemma's
two raw outputs used Markdown JSON fences; the unchanged parser extracted the
objects successfully. Therefore this entry does not claim that every raw
response was bare JSON.

### 3.2 Directly observed post-run placement

Before unload, all three exact FP16 models were simultaneously present on the
three UUID-pinned endpoints:

| Endpoint | Exact model tag | Physical GPU | GPU UUID | Runtime size and placement |
|---|---|---:|---|---:|
| `127.0.0.1:11440` | `qwen2.5:7b-instruct-fp16` | 0 | `GPU-720e6563-7e95-65c4-659e-189ba0c7bac5` | 14,519,401,184 B, `size_vram == size`, Ollama CLI `100% GPU` |
| `127.0.0.1:11441` | `llama3.1:8b-instruct-fp16` | 6 | `GPU-2964f342-8734-a701-a2c6-4344579b03ee` | 15,664,708,320 B, `size_vram == size`, Ollama CLI `100% GPU` |
| `127.0.0.1:11442` | `gemma2:9b-instruct-fp16` | 7 | `GPU-af1ef9b0-329f-ff38-d4dd-062e2beca9e0` | 19,308,824,493 B, `size_vram == size`, Ollama CLI `100% GPU` |

Every `/api/ps` row had the expected full digest, F16 quantization, and context
4096. Distinct runner PID, parent server PID, and NVIDIA compute-process rows
bound each model endpoint to its declared UUID. At the retained checkpoint,
GPUs 1--5 had no compute process and reported the recorded one-MiB idle value.
Full GPU placement here means Ollama's layer placement plus
`size_vram == size`; it does not mean zero host-mapped buffers, zero host RAM,
or zero CPU activity.

### 3.3 Cleanup qualification

Administrative unloads ran in the predeclared Gemma, Llama, Qwen order. All
three returned HTTP 200, `done=true`, and `done_reason=unload`. Final evidence
shows ports 11440--11442 closed, their temporary server and runner PIDs absent,
an empty compute-application list, all eight GPUs back at the recorded one-MiB
idle value, and the pre-existing port-11434 Ollama service continuing with the
same PID, start time, version, and empty model set. Cleanup effectiveness is
therefore `true`.

The final logs also retain post-unload GPU-discovery/free-memory diagnostic
warnings: four for Gemma, seven for Llama, and seven for Qwen in the summary's
selected post-unload categories. Including two expected startup UUID-visibility
warnings per endpoint, the complete `level=WARN` totals are six, nine, and nine
respectively. The post-unload warnings occurred after successful model unloads
and after the post-run residency checkpoint. There was no retained
`level=ERROR`, panic, OOM, CUDA execution error, or failed core request. The
artifacts do not establish the warnings' cause, and endpoint reuse after
unload was not tested. Cleanup is therefore recorded as
`passed_with_warnings`, not as warning-free.

One cleanup checkpoint after the Llama unload observed a transient
`/usr/local/bin/ollama` PID 509627 using 10 MiB on selected GPU 7. Its ancestry
was not captured, so its exact attribution is not established. It disappeared
by the next and final checkpoints and does not contradict effective final
cleanup. Manual temporary-server exit codes were not recorded; closure is
supported by absent PIDs/listeners and connection refusal.

### 3.4 Independent publication-conformance findings

The content-derived `run-summary.json` self-classifies the operational result
as `pass_with_warnings`, and its numerical/direct-observation fields agree with
the retained raw evidence. Independent read-only review nevertheless found the
following deviations from the immutable pre-execution specification:

1. Section 9 declared summary schema
   `ollama-fp16-three-endpoint-prompt-smoke-evidence-v1.0.0`; the published
   summary instead declares
   `ollama-fp16-three-endpoint-prompt6-summary-v1.0.0`.
2. The summary records `scope_status.formal_gate4_pass=false`, not the exact
   top-level field spelling shown in the specification. It does not contain the
   required `backend_freeze.status=not_frozen` field. The core manifest and all
   post-execution records still deny formal Gate 4 and research promotion, so
   this is a contract/schema gap rather than evidence of promotion.
3. The retained derivation script writes the summary before generating and
   verifying the inventory, whereas section 9 required summary publication
   only after the inventory check. The completed inventory itself independently
   verifies 235/235 files and includes the summary hash.
4. The evidence bundle's approval shorthand records six calls, GPU indices
   0/6/7, the 15-minute ceiling, and stop conditions, but does not itself spell
   out the exact output root or three full GPU UUIDs. The task transcript and
   retained launch/process evidence provide external context, but bundle-local
   authorization provenance is incomplete.
5. The summary uses `passed_with_warnings`, while the pre-execution acceptance
   list named the literal cleanup status `passed`. This is an undeclared
   reporting-status extension, albeit one that preserves rather than hides the
   observed diagnostics.
6. Section 9 required a strict-validator report and exit status. Validation ran
   in-process and its retained report records `valid=true` and `errors=[]`, while
   the enclosing prompt-smoke runner exited zero. The bundle does not contain a
   separate validator-process exit-status artifact, so it does not satisfy that
   exact publication requirement. This is not evidence that strict validation
   was skipped.

The inventory SHA-256 is recorded independently in this post-execution ledger,
not inside the self-excluding evidence tree. The dirty source state and nine
strict-validator unverifiable findings remain retained. These findings do not
alter the six successful calls or observed placement/cleanup facts, but they
prevent classification as a fully specification-conformant published evidence
package. Existing evidence files are not edited to repair the deviations.

### 3.5 Claim boundary and outstanding work

This candidate supports the operational observations from one fully completed
`Simulation.run()` lifecycle for only the declared three-agent, one-step,
six-call current-prompt smoke at concurrency one; its captured post-run
three-endpoint residency; and effective cleanup with the warnings above. The
structured scientific raw files do not retain post-Phase 4 final positions or
final in-memory agent state, and the strict validator does not independently
validate those final states. This limitation does not mean that Phase 4 was not
executed: its three movement lines are retained in the captured execution
output. The candidate is not a fully specification-conformant publication and
does not establish:

- a formal Gate 4A stage, backend freeze, pilot, or research eligibility;
- a 12-agent QQQ, GGG, LLL, or HET cell, or an eight-cell batch;
- structured-raw or strict-validator confirmation of post-Phase 4 final
  positions or final in-memory agent state;
- concurrency above one, simultaneous generation, throughput, or long-duration
  stability;
- the seven-replica Qwen/Llama/Gemma 2/2/3 deployment, routing, load balancing,
  or failure isolation;
- post-unload endpoint reuse; or
- vLLM adapter or conformance evidence.

The pre-execution auxiliary specification remains an immutable plan artifact
whose status text says `PLANNED ... NOT EXECUTED`. Execution status is supplied
only by the separate raw evidence, content-derived summary, inventory, and this
post-execution ledger entry; the specification itself is not edited after the
run.

## 4. Evidence-publisher implementation status

This section records implementation/test status only; it is not empirical
backend evidence and does not authorize another GPU run.

- Publication contract:
  `docs/GATE4_EVIDENCE_PUBLICATION_SPEC.md`, version
  `gate4-backend-evidence-publication-v1.1.0`, SHA-256
  `8201013f77d98cc0c63559fe31a7c3c8d4dc90b4d1eda0f245d0e56f77ba7b6c`.
- Repository-owned publisher: `tools/gate4_evidence_publisher.py`, version
  `gate4-evidence-publisher-v1.1.0`, SHA-256
  `83bb7a19f945023e3de0ad7a470eab82123d34d7b1e213b69aaaab4ff8298734`.
- Independent parser/verifier:
  `tools/verify_gate4_evidence_bundle.py`, report schema
  `gate4-independent-verification-report-v1.1.0`, SHA-256
  `c31fe2f06eba5f86086092e6dc3e2682c9c1be5c5eb76d24664a6e0fac6f5e5b`;
  it does not import the publisher and requires caller-supplied S/I/R and final
  directory identity when those pins are available.
- CPU result: `47/47 PASS` in 1.505 seconds for the publisher and independent-
  verifier suites. They cover the closed schemas, canonical bytes, component-
  wise no-follow traversal, source/root/final directory identities, collisions,
  interruption, correction, inventory, TOCTOU, independent S/I/R, and
  interoperability. These are CPU fixtures, not backend observations.
- Generic-profile boundary:
  `operational_backend_result=NOT_EVALUATED`,
  `claim_scope=[publication_structure_only]`, `gate4_formal_pass=false`,
  `research_eligible=false`, and `backend_freeze.status=not_frozen` remain
  fail-closed. The generic publisher cannot label arbitrary raw data PASS,
  FAIL, ABORTED, or warning-free.

The structural publisher is therefore a corrected CPU-tested implementation
candidate. It does not itself authorize or classify a backend workload. The
endpoint-reuse content layer has the separate correction record below; its real
workload remains unexecuted and unapproved. Twelve-agent reference cells and
the eight-cell smoke also remain unexecuted after the prompt6 candidate.

## 5. Endpoint-reuse tooling correction

This section is implementation/test evidence only. It is not an Ollama,
NVIDIA, model, residency, endpoint-reuse, or cleanup observation.

### 5.1 Retained checker FAIL at `9d737cd...`

The branch, local HEAD, tracking SHA, and remote SHA were all
`9d737cd8adaa7c334f065932ea6772ff53363d1b`, the worktree was clean, and no
tooling tag existed. The then-current endpoint-reuse suite passed `13/13` in
2.236 seconds and the complete suite passed `256/256` in 25.698 seconds, but
the supplied self-contained and adversarial fixtures classified that tooling
state as `CHECKER FAIL / tooling freeze prohibited`. Passing the existing suite
did not override the independently reproduced contradictions:

1. after Qwen raised `TimeoutError`, queued Llama and Gemma workers still began
   backend generation, for three actual calls;
2. the six-generation budget was not enforced at the dispatch boundary, and an
   early Phase 3 request could unload endpoints before its phase precondition
   failed;
3. persisted `workload-validation.json` bytes could say `FAIL / ineligible`
   while recomputation, publication, independent verification, and the external
   receipt said `PASS / eligible`;
4. byte-identical alternate source/final directory inodes and a symlink-root
   interpretation could differ across validator, publisher, and verifier
   handoffs; and
5. a final unload with `done=false` made the overall result fail but could leave
   `checks.cleanup=PASS` because cleanup status depended on error text.

The same review retained a non-blocking classification defect: a concurrent
approval-ID loser could expose raw `FileExistsError` rather than the documented
controlled collision. No repository file, real approval, Ollama/API endpoint,
NVIDIA device, sudo policy, process, or GPU was changed or exercised by that
checker run.

### 5.2 Corrected implementation candidate

The bounded correction is split across these reviewable implementation commits:

- `05546a1174179fc04636dbfa263301a04bb8e203`,
  `fix: enforce approval-bound endpoint execution stops`;
- `6835508e3c20a2f3d7576746dcc76583eb944550`,
  `fix: bind Gate 4 validation and directory identities`.

The corrected contract and implementation pins are:

- endpoint-reuse specification
  `gate4-ollama-endpoint-reuse-v1.1.0`, SHA-256
  `8ce1eb7c7e1c18d4476532864e245e026d2ffc8c9b4b55d847d71bf2c9404d73`;
- orchestrator `tools/gate4_endpoint_reuse_orchestrator.py`, SHA-256
  `6674a73d4ff7e62e9549801a5382226b95b1c8199e0cb80c2fb9dd29dca98023`;
- independent workload validator
  `tools/validate_gate4_ollama_endpoint_reuse.py`, SHA-256
  `c58bc4118838ac6671870042f92b407f58e9687740fdeee1ce26a6ae38214d1c`;
- shared no-follow identity primitive `tools/gate4_fs_identity.py`, SHA-256
  `6a2e77af9490dcd9de7123ff3600f75b396207bdd4bef1acc2b34a02018360ae`.

The observation, result, artifact-index, workload-validation,
workload-validation-commitment, and external-receipt schemas are version 1.1.0.
At that correction checkpoint, the endpoint approval remained the closed
v1.0.0 schema and no approval artifact had yet been created. The generic
summary, generic approval, and capture-
manifest schemas also remain v1.0.0 because their shapes did not change.

The workload-local `ApprovalExecutionGate` preserves the frozen Gate 2 rule
that every submitted phase request settles, but atomically reserves immediately
before each actual `backend.generate` call. The actual generation count is the
number of those backend invocations, irrespective of successful records,
logical Simulation submissions, HTTP attempts, retries, or administrative
unloads. The first timeout, deadline expiry, transport/unexpected exception,
generation-contract error, invalid sequence, or exhausted budget latches a
one-way terminal reason; queued workers settle without starting a new backend
generation. Before any first Phase 3 unload, the same gate requires the exact
three successful Phase 1 roles, matching transcript state, no terminal latch,
no prior Phase 3 start, three remaining generation slots, and an unexpired
deadline.

Workload validation now has a pure read-only derivation and a separate
non-self-referential commitment to the exact canonical persisted validation
bytes. Source attempt, publisher staging, and published final validation must
all match the independently derived bytes, SHA, operational result, eligibility,
and fixed formal/research boundaries. Descriptor-derived `{device,inode}`
identities bind the source and publication root into the publisher receipt, the
final identity into the publisher-independent verifier and final workload
validation, and both identities into the external receipt. Symlink roots or
components and later inode substitutions fail closed. Cleanup is the conjunction
of eight explicit evidence booleans; no status is derived from error text.
Attempt, final, and receipt claim races use the controlled collision class.

### 5.3 CPU results and remaining boundary

The corrected implementation tree produced these synthetic CPU results:

```text
endpoint-reuse suite              28/28 PASS   3.759 s
publisher + independent verifier  47/47 PASS   1.505 s
prompt6 regression                10/10 PASS   0.257 s
complete repository suite        272/272 PASS 27.596 s
compileall                         PASS
git diff --check                  PASS
```

The retained timeout fixture now records one actual backend generation
(`qwen:TimeoutError`), zero Llama/Gemma generation starts, cleanup called, and
no publication. The seventh direct call is suppressed with the actual count
remaining six. Early Phase 3 records zero unloads and zero backend generations.
Source, staging, final, reverse persisted-result, alternate-inode, and symlink
mismatches are rejected. A final unload with `done=false` yields overall FAIL,
publication ineligibility, `checks.cleanup=FAIL`, and
`final_unloads_complete=false`. The concurrent same-ID fixture produces exactly
one owner and one controlled collision; a late publisher final-leaf collision
is normalized to the same public class.

All endpoint fixtures inject a CPU backend and guard real network/process/GPU
entry points. They do not establish that live sudo policy, Ollama 0.32.13 API
responses, process ancestry, NVIDIA rows, warning behavior, exact-PID cleanup,
or stability timing will satisfy the contract. No real HTTP request, Ollama
request, `nvidia-smi`, sudo call, temporary server, process signal, or GPU
workload was performed by that tooling-correction test run. The later rejected
approval candidate and warning-policy correction are recorded in section 6.

The current prompt6 runner's ledger pin is refreshed only to follow these
updated repository-ledger bytes. The dependency is one-way: this ledger does
not pin the current runner SHA. The historical prompt6 source snapshot and
bundle remain unchanged; they are not altered, republished, repaired, or
reclassified. Their retained axes remain `PASS_WITH_WARNINGS`,
`NONCONFORMING / NOT FORMALLY ACCEPTED`, and formal eligibility `false`.

Therefore the classification at completion of that limited correction, before
the historical tooling tag and later approval review, was:

```text
Gate 4A tooling corrected implementation candidate: PASS
Combined independent tooling recheck: PENDING
Tooling freeze: NOT DONE
Endpoint-reuse execution approval: NO
Real endpoint-reuse execution: NOT PERFORMED
Formal Gate 4A: NOT PASSED / NOT FROZEN
Backend freeze: not_frozen
Research eligibility: false
```

A future real attempt requires a new explicit approval naming the then-clean
HEAD and exact bounded envelope. This ledger entry does not grant that approval.

## 6. Structured warning-policy correction

This section is CPU implementation and approval-review evidence only. It is
not an Ollama, NVIDIA, model, endpoint-reuse, cleanup, or backend-freeze
observation.

### 6.1 Historical tooling freeze and rejected approval

The annotated tag
`gate4a-endpoint-reuse-tooling-frozen-20260817` peels to
`225ae755f3dff2400d2fa8a60b1d1bb9a3e17071`. That tag remains immutable
historical evidence but is `SUPERSEDED FOR REAL EXECUTION` because the first
approval review found a blocking warning-policy defect. It is not moved,
deleted, or retagged by this correction.

The rejected candidate is retained byte-for-byte outside the repository:

```text
approval ID  = gate4a-endpoint-reuse-fp16-20260817T124139Z
approval SHA = b97d603b2e34c0e7157398a916ae6485e60bc6304746cb2189a1db11187756d4
summary SHA  = 06f8c71a5f5fa8a299e9152b8535305a72da4ac263bfa52e3c29c70e278a821f
review       = FAIL
authorization = NO
execution    = NOT PERFORMED
```

The JSON and summary remain mode 0444 and are not edited, replaced, deleted,
reauthorized, or executed. Their approval ID, bundle ID, and SHA cannot be
reused. Candidate creation previously used read-only GETs against the existing
11434 service to record its identity; it did not invoke the orchestrator,
start temporary endpoints, call generation, unload a model, use sudo, run an
NVIDIA probe, or start a GPU workload.

The review directly identified two linked defects. A raw line containing
`level=WARN` could be classified WARN before a later ERROR/FATAL indicator on
the same captured line, and the approved whole-line `fnmatch` glob beginning
`time=*` allowed `*` to span arbitrary intervening content. An approved suffix
could therefore conceal a preceding unapproved or fatal event. Narrowing the
six glob strings could not repair the contract.

### 6.2 Corrected structured contract

Commit `3d87d22ff2ddd75b0e219b9ac9fda30cccec9ba0`,
`fix: require structured Gate 4 warning events`, replaces whole-line glob
acceptance with a complete physical-line parser and exact structured identity
comparison. Its current pins are:

- endpoint-reuse specification
  `gate4-ollama-endpoint-reuse-v1.2.0`, SHA-256
  `b445f3ee303dd5a1cde98c63489b1bd501d77174ec98f01133b3bfd6fc9a1b4d`;
- executable approval schema
  `gate4-ollama-endpoint-reuse-approval-v1.1.0`;
- orchestrator `tools/gate4_endpoint_reuse_orchestrator.py`, SHA-256
  `d7c17e92607eeb3e8ab59ae4f6d972282327c70fda070627ca1225d95f720915`;
- workload validator `tools/validate_gate4_ollama_endpoint_reuse.py`, SHA-256
  `01df6039ee2701ab831ffca44bd2fe6ee7cc47d10745703d0831448ad7fb5644`;
- unchanged publication specification, publisher, and standalone verifier,
  SHA-256 respectively
  `8201013f77d98cc0c63559fe31a7c3c8d4dc90b4d1eda0f245d0e56f77ba7b6c`,
  `83bb7a19f945023e3de0ad7a470eab82123d34d7b1e213b69aaaab4ff8298734`,
  and `c31fe2f06eba5f86086092e6dc3e2682c9c1be5c5eb76d24664a6e0fac6f5e5b`.

The observation and workload-validation schemas are version 1.2.0 because
they now retain structured events and structured accepted/unknown results.
The result, artifact-index, validation-commitment, and external-receipt schemas
remain version 1.1.0 because their public field structures did not change. The
generic publication projection is unchanged.

Each diagnostic physical line is independently bounded, base64-retained,
SHA-256-bound, assigned a role/context stream and physical line sequence, and
fully parsed as logfmt-like key/value input. The parser rejects embedded line
breaks, duplicate keys, mixed/duplicate severity, malformed quotes, missing or
invalid time/level/source/message, invalid source line, and any ignored trailing
token. The validator reparses the indexed server-log bytes and requires exact
structured event equality; no whole-line wildcard matcher remains.

The approval contains exactly six closed structured warning identities: the
two fixed startup events for each role/UUID. Role, level `WARN`, source file and
line, message, complete attribute set, and value are exact; each maximum
occurrence is one. Absence is allowed. Wrong role/UUID/source/message, an extra
attribute, unknown WARN, request-failure WARN, watchdog WARN, stale/free-memory
WARN, or an excess occurrence is `MANUAL_REVIEW_REQUIRED` and publication
ineligible. Parsed or malformed ERROR/FATAL/PANIC, OOM, crash, segfault,
CUDA-error, or Xid evidence is `FAIL`. A later exact WARN cannot downgrade an
earlier failing physical line. The old approval schema and glob field are
rejected before any attempt.

### 6.3 CPU results and current boundary

The structured correction produced:

```text
endpoint-reuse targeted suite     38/38 PASS
publisher + independent verifier  47/47 PASS
prompt6 regression                10/10 PASS
complete repository suite        282/282 PASS
compileall                         PASS
git diff --check                  PASS
```

The exact-six fixture yields `PASS_WITH_WARNINGS`, publication eligibility,
atomic publication, independent S/I/R verification, and a successful external
receipt while retaining formal/research false. A no-warning fixture yields
`PASS`. Unknown/request-failure/watchdog/stale-memory and excess-occurrence
fixtures are non-publishable. ERROR/FATAL mixed with approved content on the
same or a preceding physical line yields `FAIL` and no publication. Raw-line
hash and server-log trace tampering are rejected. CPU fixtures guard real
network and process entry points.

No GPU, `nvidia-smi`, Ollama/API, sudo, network, temporary server, process
signal, real approval, or endpoint execution was used by this warning-policy
implementation task. The existing rejected approval was only read to confirm
its immutable SHA. No replacement approval or tooling tag has been created,
and nothing has been pushed.

The current prompt6 runner's ledger pin is refreshed only to follow the final
v1.5.0 ledger bytes. This ledger does not pin the current runner SHA, so the
dependency remains one-way. Historical prompt6 bytes and classification are
unchanged.

The exact current classification is:

```text
Gate 4A warning-policy corrected tooling candidate: PASS
Combined independent tooling recheck: PENDING
Replacement tooling freeze: NOT DONE
Old tooling tag: HISTORICAL / SUPERSEDED FOR EXECUTION
Rejected approval: NOT AUTHORIZED / NOT EXECUTED
New approval candidate: NOT CREATED
Formal Gate 4A: NOT PASSED / NOT FROZEN
Backend freeze: not_frozen
Research eligibility: false
```
