# Gate 4A FP16 Three-Endpoint Prompt Smoke Specification

Version: `gate4a-fp16-three-endpoint-prompt-smoke-v1.0.0`

Status: `PLANNED AUXILIARY SMOKE — NOT EXECUTED — NOT AUTHORIZATION TO RUN`

## 1. Purpose and formal boundary

This auxiliary smoke tests whether each of the three exact FP16 Ollama models
can return parseable output for one current Phase 1 prompt and one current
Phase 3 prompt through the native Ollama `/api/chat` client path. It expands
the already observed capacity/residency envelope by the smallest useful unit:
three agents, one simulation step, and six logical model calls.

This is not Gate 4A-1, Gate 4A-2, Gate 4A-3, Gate 4A-4, a backend evidence
freeze, a Gate 3 matrix cell, a pilot, or a research run. Its evidence must
persist:

```text
execution_mode = reference_ollama
gate4_formal_pass = false
research_eligible = false
backend_freeze.status = not_frozen
```

An auxiliary-smoke PASS does not change any formal Gate 4 status or authorize
the next workload. Failed, aborted, and not-started calls are retained and are
never replaced in the same evidence directory.

## 2. Required prerequisite

The sole capacity prerequisite is the candidate indexed in
`docs/GATE4_BACKEND_EVIDENCE_LEDGER.md`:

```text
evidence_id = pinned3-20260816T071057Z
schema = ollama-uuid-pinned-three-endpoint-residency-smoke-v1.0.0
corrected_summary_sha256 =
  8de870da8026bab963d910d97df51ac7e0f6f63070b5dc589e11db301f7c46a6
inventory_sha256 =
  e22f09ced22311c40bfe5fd6d6b24b13afffac62299809328f005aa8e8def415
```

Before any GPU work, a read-only preflight must recompute both named hashes and
must obtain 140/140 PASS from the prerequisite inventory. It must also confirm
that the corrected summary records `overall_status=passed`,
`gate4_formal_pass=false`, and `research_eligible=false`. A mismatch stops the
attempt before temporary processes or model loads begin. This prerequisite is
a scope-limited candidate, not frozen backend evidence.

## 3. Prompt and simulation envelope

The smoke uses the current unmodified prompt source:

```text
engine/prompts.py SHA-256 =
  f414ab30a963636d80239644c2d3770672c77d5b8bdde027de2eb15a0d08bc3d
```

No prompt text, model identity, bloc identity, desired result, or parse hint may
be added to the agent prompts. Model output remains untrusted text and no
generated instruction, code, or URL is executed or fetched.

The dedicated smoke configuration contains exactly three blocs and one agent
per bloc, in canonical bloc order:

| Agent ID | Bloc | Gate 3 replicate-0 HET slot | Model family |
|---:|---|---|---|
| 0 | `alpha` | `qwen` | Qwen |
| 1 | `beta` | `gemma` | Gemma |
| 2 | `neutral` | `llama` | Llama |

This copies only the Gate 3 zero-based replicate-0 rotation
`alpha=qwen, beta=gemma, neutral=llama`. It deliberately does not claim to be a
Gate 3 HET cell, because a formal matrix cell has four agents per bloc.

The remaining fixed smoke inputs are:

```text
simulation steps = 1
agents = 3
edge_policy = full
provider = ollama
transport = ollama_native
endpoint path = /api/chat
Phase 1 logical calls = 3
Phase 3 logical calls = 3
total logical calls = 6
llm_defaults.temperature = 0.2
llm_defaults.max_tokens / native num_predict = 256
llm_defaults.max_concurrency = 1
llm_overrides.num_ctx = 4096
native top-level keep_alive = -1
stream = false
```

`temperature=0.2` is a value declared in advance only for this auxiliary
smoke. It is not a frozen pilot, confirmatory, production, or general protocol
value. The complete effective config, including the world seed, world geometry,
places, agent context limits, timeout, failure thresholds, unique run ID, and
all explicit defaults, must be saved and hash-pinned before the first request.
No later model output may be used to retrofit those inputs.

Global concurrency one preserves canonical request order. All three Phase 1
requests must settle before Phase 2 delivery. All three Phase 3 requests must
settle before Phase 4 movement. Phase 2 and Phase 4 make no model calls.
Within each model phase, canonical agent order is Qwen, Gemma, then Llama.

## 4. Exact endpoint and artifact contract

| Bloc | Base URL | Physical GPU | GPU UUID | Exact model tag | Full digest | Template SHA-256 |
|---|---|---:|---|---|---|---|
| `alpha` | `http://127.0.0.1:11440` | 0 | `GPU-720e6563-7e95-65c4-659e-189ba0c7bac5` | `qwen2.5:7b-instruct-fp16` | `59805ce4a4046be2d8f63231a78daacd2e66f5dccf1a64d0d138ebeeb26ff16c` | `eb4402837c7829a690fa845de4d7f3fd842c2adee476d5341da8a46ea9255175` |
| `beta` | `http://127.0.0.1:11442` | 7 | `GPU-af1ef9b0-329f-ff38-d4dd-062e2beca9e0` | `gemma2:9b-instruct-fp16` | `28e6684b085085f78551db7c96a9daa546161b1da9d055ea01b84cb1163013cf` | `109037bec39c0becc8221222ae23557559bc594290945a2c4221ab4f303b8871` |
| `neutral` | `http://127.0.0.1:11441` | 6 | `GPU-2964f342-8734-a701-a2c6-4344579b03ee` | `llama3.1:8b-instruct-fp16` | `4aacac4194543ff7f70dab3f2ebc169c132d5319bb36f7a7e99c4ff525ebcc09` | `948af2743fc78a328dcb3b0f5a31b3d75f415840fdb699e8b1235978392ecf85` |

The endpoint-to-GPU mapping remains the prerequisite mapping: port 11440 is
GPU 0, port 11441 is GPU 6, and port 11442 is GPU 7. Before execution, the
generated config must be mechanically checked against the following
unambiguous mapping:

```text
alpha   -> Qwen  -> 127.0.0.1:11440 -> GPU 0
beta    -> Gemma -> 127.0.0.1:11442 -> GPU 7
neutral -> Llama -> 127.0.0.1:11441 -> GPU 6
```

Each temporary Ollama process is localhost-only and exposes exactly one GPU by
the listed UUID. Its environment includes:

```text
OLLAMA_VULKAN=0
OLLAMA_NO_CLOUD=1
OLLAMA_NUM_PARALLEL=1
OLLAMA_MAX_LOADED_MODELS=1
OLLAMA_CONTEXT_LENGTH=4096
OLLAMA_KEEP_ALIVE=-1
```

`CUDA_VISIBLE_DEVICES` and `OLLAMA_HOST` take the row-specific UUID and port.
The request must also carry `num_ctx=4096` in `options` and `keep_alive=-1` as
a top-level native `/api/chat` field. Server defaults alone are insufficient
request provenance.

Before the first simulation request, `POST /api/show`, process/listening
snapshots, and a host-side `nvidia-smi` must confirm the exact tag, digest, F16
quantization, template hash, endpoint, temporary process, and selected UUID.
`GET /api/ps` and `ollama ps` are also saved, but the newly started endpoints
are expected to be empty at that point. No generic warm-up or model-load
generation is allowed: the six simulation-prompt calls must be the only
inference generations.

The simulation transcript and per-call monotonic timestamps must prove that all
three Phase 1 calls settled before the first Phase 3 call. A read-only resource
checkpoint may additionally be taken at that barrier, but it is not required
for this six-call auxiliary smoke. The mandatory simultaneous resource
checkpoint is the post-run checkpoint in section 8; it must confirm the exact
loaded tags and digests, `context_length=4096`, full GPU residency, and the
expected three UUIDs before any unload begins.

## 5. Client and response capture contract

Every logical call uses the current native Ollama request builder and
`engine.sim.call_ollama` implementation, directly or through an evidence-only
transport wrapper that does not change prompt or parse semantics. The wrapper
may only capture owned copies of the exact request payload, response envelope,
HTTP status, parsed result, request identity, timestamps, and worker-local
telemetry. It must not rewrite generated text or retry a request outside the
current client.

The six request identities are fixed:

```text
step-000001:phase1:agent-000000
step-000001:phase1:agent-000001
step-000001:phase1:agent-000002
step-000001:phase3:agent-000000
step-000001:phase3:agent-000001
step-000001:phase3:agent-000002
```

For every identity, the evidence sidecar records the selected endpoint, exact
model tag, request payload, prompt SHA-256, HTTP status, full native response
envelope, `done`, returned model name, raw generated text, parsed object or
null, and call telemetry. Duration, load duration, prompt/eval token counts,
and done reason are retained when Ollama returns them.

## 6. Acceptance conditions

The auxiliary smoke passes only when all of the following are mechanically
observed:

```text
run status = completed
aborted = false
expected steps = completed steps = 1
expected agents = observed agents = 3
Phase 1 coverage = 3/3 exact request identities
Phase 3 coverage = 3/3 exact request identities
logical calls = 6
HTTP attempts = 6
HTTP 200 = 6/6
done = true = 6/6
parsed object is not null = 6/6
generation_retries = 0
transport_failures = 0
syntax_parse_attempt_failures = 0
syntax_parse_failures = 0
schema_validation_failures = 0
strict validator valid = true
strict validator errors = []
exact tag/digest/template/context checks = 3/3
post-run full-GPU residency checks = 3/3
cleanup status = passed
gate4_formal_pass = false
research_eligible = false
```

The six HTTP attempts and six HTTP 200 responses above are the simulator's
generation telemetry. Read-only `/api/show` and `/api/ps` probes and the later
administrative unload requests are separately classified and counted; they
must not be inserted into the logical-generation or generation-attempt totals.

The zero `schema_validation_failures` counter does not assert that semantic
model-response schema validation exists. The strict validator's complete
`unverifiable` list must be retained, and no unavailable check may be converted
into a PASS. The additional per-call `parsed object is not null` evidence is a
specific acceptance requirement for this smoke.

Generated response bytes need not match across models. Byte identity, output
quality, behavioral equivalence, determinism, adoption, propagation, causality,
or robustness are outside this smoke's acceptance criteria.

## 7. Stop and retention rules

Stop progression after preserving the evidence collected so far if any of the
following occurs:

- prerequisite, source, prompt, config, model digest, template, F16, context,
  endpoint, UUID, or process evidence differs from the declared value;
- CPU offload, use of an unselected GPU, cross-endpoint model load, or eviction;
- any non-200 status, `done != true`, terminal transport failure, HTTP 503,
  OOM, Ollama crash, panic, or GPU Xid;
- any generation retry, syntax parse-attempt failure, final parse failure, null
  parsed result, or extra HTTP attempt;
- incomplete Phase coverage, phase-order violation, aborted simulation, strict
  validation failure, evidence collision, or inventory inconsistency; or
- the approved execution time ceiling is reached.

The phase-preserving executor settles every request already submitted for the
current phase. A condition first observed while that phase is settling does not
cancel its queued requests; instead, no later phase is started. Calls in later
phases are marked `not_started`. Completed and failed request sidecars, run
output, server logs, and resource snapshots are retained under the same attempt
ID. A retry requires a new evidence ID and fresh output directory.

## 8. Post-run residency and cleanup

After all six calls and before unloading anything, preserve a simultaneous
residency checkpoint for all three endpoints. It must show the same exact
tag/digest/template-associated artifact, `context_length=4096`,
`size_vram == size`, selected UUID, and three distinct runner processes as the
preflight. `ollama ps`, `/api/ps`, compute applications, full `nvidia-smi`, and
server-log scans are retained.

Then unload only the three smoke models and verify every temporary endpoint's
`/api/ps` is empty. The operator may terminate only the three temporary Ollama
processes on ports 11440--11442. Final evidence must show those ports closed,
their PIDs absent, all GPU memory returned to the recorded idle baseline, and
the existing port 11434 Ollama process still listening. Machine shutdown,
reboot, `systemctl`, driver changes, and termination or restart of the existing
11434 service are prohibited.

Each `keep_alive=0` unload is an administrative request, not a logical model
generation. Its exact payload, endpoint, HTTP status, response, and ordering
must nevertheless be retained independently from the six inference calls.

## 9. Evidence tree and inventory

The versioned evidence-summary schema is
`ollama-fp16-three-endpoint-prompt-smoke-evidence-v1.0.0`.

The attempt exclusively creates a fresh leaf such as:

```text
/home/iitsuka/mcs-backend-smoke/ollama-prompt-smoke-fp16/<evidence_id>/
```

Creation fails if the leaf already exists. The evidence tree contains at least:

- an execution plan and separate operator-approval reference, including the
  six-call count, three GPU UUIDs, output root, finite time ceiling, and stop
  rules;
- source SHA and complete dirty state, dependency/runtime versions, prompt
  bytes/hash, exact effective config and config hash, and this specification's
  bytes/hash;
- the prerequisite summary, inventory, their expected/recomputed hashes, and
  the 140-entry verification output or immutable references to those exact
  bytes;
- temporary-process launch environments, PIDs, ports, server logs, Ollama/API
  versions, `/api/tags`, `/api/show`, `/api/ps`, `ollama ps`, `nvidia-smi`,
  compute-app, and listening/process snapshots;
- six exact request payloads, six response envelopes and HTTP status records,
  six parsed-result sidecars, request identities, prompt hashes, and telemetry;
- the complete simulation run directory, strict-validator report and exit
  status, post-residency evidence, ordered cleanup transitions, final idle and
  existing-service checks, and all failed or not-started records; and
- a corrected versioned summary plus `files.sha256` inventory. Any superseded
  derivative is retained, hash-listed, and linked by an explicit correction
  relationship and reason.

The final inventory excludes itself, records every other artifact's SHA-256,
is independently checked read-only, and has its own separately recorded
SHA-256. Summary publication occurs only after the inventory check passes. The
summary must retain `gate4_formal_pass=false`, `research_eligible=false`, and
the complete list of unverified claims.

After a separate read-only check, the candidate evidence ID, summary hash,
inventory hash, scoped result, correction history, and not-verified list may be
added to `docs/GATE4_BACKEND_EVIDENCE_LEDGER.md`. The executed evidence and
this pre-execution specification are not edited retroactively to add that later
ledger entry.

## 10. Authorization envelope

This specification is not execution approval. Before starting the three GPU
processes or loading a model, the operator must separately approve exactly six
logical generations on GPUs 0, 6, and 7, the output root above, a finite
wall-clock ceiling, and the stop rules in section 7. The execution record must
capture that approval reference. No approval for this smoke extends to a
twelve-agent cell, seven replicas, eight cells, vLLM, a pilot, or research use.
