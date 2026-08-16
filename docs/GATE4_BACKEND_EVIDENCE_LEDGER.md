# Gate 4 Backend Evidence Ledger

Version: `gate4-backend-evidence-ledger-v1.2.0`

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
  `gate4-backend-evidence-publication-v1.0.0`, SHA-256
  `b204214fc9ee063d6a5fad956a2a59ac161f923986f524e9921055cca47eeed1`.
- Repository-owned publisher: `tools/gate4_evidence_publisher.py`, SHA-256
  `743ec7c4f6a492105aed2d67dc27e0c95b89389cf033d1b76360bbdb1dc9e85e`.
- Independent parser/verifier:
  `tools/verify_gate4_evidence_bundle.py`, SHA-256
  `9338bc43cbe0fe53f1893c7c5dc9b522faed5dee62762b88bd0b64bddf4fdcf4`;
  it does not import the publisher and requires caller-supplied S/I/R
  commitments when those pins are available.
- CPU result: `46/46 PASS` for the publisher and independent-verifier suites,
  which jointly cover all targeted schema, canonical-byte, no-follow,
  collision, interruption,
  correction, inventory, TOCTOU, independent-S/I/R, and interoperability
  fixtures. These are CPU fixtures, not backend observations.
- Generic-profile boundary:
  `operational_backend_result=NOT_EVALUATED`,
  `claim_scope=[publication_structure_only]`, `gate4_formal_pass=false`,
  `research_eligible=false`, and `backend_freeze.status=not_frozen` are
  fail-closed. The generic publisher cannot label arbitrary raw data PASS,
  FAIL, ABORTED, or warning-free.

The structural publisher is therefore a CPU-tested candidate, but the GPU
workflow is not yet publication-ready. Before endpoint reuse or another model
request, a versioned workload-specific validator must derive its operational
result and warnings from raw bytes, and the workload orchestrator must validate
the exact approval before the first GPU workload, bind its hash into
capture-start metadata, and compare actual call count, elapsed time, and GPU
UUIDs with the approved limits. None of those missing integrations may be
inferred from the standalone publisher. Endpoint reuse, 12-agent cells, and
the eight-cell smoke remain unexecuted after the prompt6 candidate.
