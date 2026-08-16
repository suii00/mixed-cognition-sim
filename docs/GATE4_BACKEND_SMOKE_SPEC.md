# Gate 4 Backend Smoke Specification

Version: `gate4-backend-smoke-v1.0.0`

Status: `PLANNED — NOT EXECUTED — NOT AUTHORIZATION TO RUN`

## 1. Purpose and gate order

Gate 4 establishes real-backend evidence without treating a backend smoke as a
pilot, confirmatory run, or research result. The required order is:

```text
Gate 3 frozen tag
  -> Gate 4A-1 Ollama single-model single-request smoke
  -> Gate 4A-2 Ollama QQQ one-cell run smoke
  -> Gate 4A-3 Ollama HET one-cell run smoke
  -> Gate 4A-4 Ollama one-replicate eight-cell sequential smoke
  -> Ollama reference-backend evidence freeze
  -> Gate 4B vLLM adapter and the same staged smoke sequence
```

No later stage may supply missing evidence for an earlier stage. A failed,
aborted, negative, or stopped stage is retained and blocks progression until a
new, uniquely identified attempt is approved. Gate 4B is deferred until the
Gate 4A evidence bundle has been independently checked and frozen.

## 2. Claim and eligibility boundary

Gate 4A may directly observe the selected Ollama server, model artifacts,
requests, responses, resource allocation, and simulator artifacts. Hashes,
counts, and validator classifications mechanically derived from those bytes
must be labeled as such. Interpretation, including a suspected cause of a
failure or resource difference, must remain distinct from direct observation.

Gate 4A and Gate 4B make no claim of behavioral robustness, backend
equivalence, output determinism, output quality, adoption, propagation, or
causality. Generated response bytes are not required to agree across attempts,
concurrency values, model families, Ollama and vLLM, or server restarts.

Every Gate 4 smoke artifact must persist `research_eligible = false`. A smoke
PASS is backend and orchestration evidence only. It does not freeze the
production candidate registry, authorize a pilot or research run, or promote a
run to research evidence. The production protocol remains `NOT READY` and pilot
authorization remains `NO` until their separate gates are completed.

## 3. Frozen invariants

Gate 4 preserves all of the following unless a separately approved, versioned
amendment says otherwise:

- `engine/prompts.py` bytes and SHA-256
  `f414ab30a963636d80239644c2d3770672c77d5b8bdde027de2eb15a0d08bc3d`;
- no bloc name, model name, or self/other model identity in an agent prompt;
- the four phase barriers, snapshots, canonical agent ordering, delivery rule,
  and movement semantics;
- the existing JSON extraction behavior and failure taxonomy;
- the scientific raw JSONL schema and `metric-v2.0.0` meaning;
- model output as untrusted text that is never executed and whose URLs are not
  fetched; and
- fresh run IDs, exclusive output directories, immutable raw logs, and
  retention of null, negative, failed, and aborted evidence.

Gate 4A uses the frozen reference path:

```text
provider = ollama
transport = ollama_native
endpoint = /api/chat
implementation = engine.sim.call_ollama
```

The Ollama OpenAI-compatible endpoint is not substituted during Gate 4A.

## 4. Authorization and GPU boundary

Before any GPU workload, the operator must record the approved execution
envelope, time limit, stop rules, output root, source commit and dirty state,
and the GPU UUID. `nvidia-smi` must be run and saved immediately before server
startup. A long, paid, remote, or all-eight-GPU run requires its own explicit
approval; this specification is not that approval.

Gate 4A-1 uses one of physical GPUs 0, 1, 6, or 7 so that GPUs 2--5 remain
available for communication-heavy work. Selection is made from the direct
`nvidia-smi -L` observation and is persisted by GPU UUID, not assumed from an
index. No Gate 4 stage may occupy all eight GPUs without explicit approval.

## 5. Fresh evidence bundle and no-overwrite rule

Each attempt has a unique immutable `evidence_id` and exclusively creates:

```text
<backend_smoke_root>/ollama-reference/<evidence_id>/
```

The creation operation must fail if that exact directory exists. `mkdir -p`,
suffix recovery, reuse, append, resume, replacement, and overwrite are
prohibited for an evidence leaf. A retry uses a new evidence ID and retains the
prior leaf.

The evidence leaf contains a versioned plan, exact config inputs, command and
exit-status records, server launch environment, server log, API artifacts,
simulator run or batch directories, validator reports, and a final
`backend_evidence_manifest.json`. The manifest schema is
`gate4-backend-evidence-manifest-v1.0.0`. It records the SHA-256 and byte count
of every evidence file, the source commit and dirty state, protocol/spec/prompt
and config hashes, run and matrix IDs, GPU UUIDs, model identities, start and
end UTC times, stage status, stop reason, and checker result.

Shell pipelines must preserve the producing command's failure status; a
successful `tee` must not hide a failed `nvidia-smi`, `ollama`, or `curl`.
Manifest publication occurs only after the complete file set and hashes have
been verified. An interrupted leaf remains unpublished but retained.

Raw API response envelopes, including duration, load duration, token counts,
completion state, and model identity when returned, are backend evidence. They
must be saved as immutable non-scientific sidecars without changing generated
text or the scientific raw schema. If the current transport cannot capture a
required response field, that field is recorded as unavailable; it must not be
reconstructed or silently inferred.

## 6. Gate 4A common Ollama server contract

Gate 4A-1 starts a manual Ollama server on a distinct localhost-only port and
uses the following exact contract, with the selected UUID substituted:

```bash
CUDA_VISIBLE_DEVICES=GPU-xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx \
OLLAMA_VULKAN=0 \
OLLAMA_HOST=127.0.0.1:11440 \
OLLAMA_NO_CLOUD=1 \
OLLAMA_NUM_PARALLEL=1 \
OLLAMA_MAX_LOADED_MODELS=1 \
OLLAMA_CONTEXT_LENGTH=4096 \
OLLAMA_KEEP_ALIVE=-1 \
ollama serve
```

`OLLAMA_VULKAN=0` is mandatory for this reference server contract. On the
directly observed Ollama `0.32.13` installation, leaving Vulkan discovery
enabled exposed all GPUs despite the intended single-GPU boundary. The launch
environment, actual server version, process identity, port, and selected GPU
UUID must be recorded rather than assuming that observation generalizes to
another Ollama version.

The contract is intentionally limited to one GPU, one loaded model, one
parallel request, 4,096 context tokens, and local-only service. The config must
also persist `num_ctx = 4096` in `llm_overrides`; the server environment alone
is not sufficient provenance. Temperature and `num_predict` are explicit, and
the effective request options are saved. The server-level keep-alive setting
and any top-level request `keep_alive` value are recorded separately;
`keep_alive` must not be hidden inside generation `options`.

Later stages may change `OLLAMA_NUM_PARALLEL` or
`OLLAMA_MAX_LOADED_MODELS` only where that stage declares the change. Every
other server setting remains fixed or is recorded as an explicit deviation.

## 7. Gate 4A common preflight evidence

Before the first model request, save at least:

- `nvidia-smi -L` and a full `nvidia-smi` snapshot;
- `ollama --version`;
- `GET /api/version` from the dedicated server;
- `GET /api/tags` from the dedicated server;
- source Git SHA, complete dirty state, dependency versions, hostname, OS,
  Python version, CUDA/driver observation, and the launch environment; and
- the exact Gate 4 stage plan, config, prompt hash, and their SHA-256 values.

Before using a model in a simulation stage, save `POST /api/show` for that exact
model name. The exact response bytes and mechanically extracted model digest,
format, parameter size, quantization, parameters, and chat template bytes/hash
are recorded. The digest and template used by a config are fixed before the
run; later output must not be used to retrofit the config.

After each load or run, save `GET /api/ps`, `ollama ps`, and `nvidia-smi`.
Evidence must identify allocated context, VRAM, GPU/CPU placement, and whether
an unexpected GPU was used. Missing evidence is not a PASS.

## 8. Gate 4A-1: Ollama single model and single request

Gate 4A-1 uses:

```text
model = qwen2.5:3b
GPU count = 1
loaded model count = 1
logical request count = 1
max concurrency = 1
num_ctx = 4096
provider = ollama
transport = ollama_native
execution_mode = reference_ollama
research_eligible = false
```

The request uses the current prompt source, explicit temperature and
`num_predict`, and the current `engine.sim.call_ollama` path. It is not replaced
by a generic prompt or OpenAI-compatible request. Parse retry behavior remains
unchanged and any extra HTTP attempt is recorded distinctly from the one
logical request.

Gate 4A-1 passes only when the request completes, the expected digest and
template agree with the preflight evidence, `num_ctx` is 4,096, the model is
fully GPU-resident on only the selected UUID, the output parses successfully,
the response and resource sidecars are complete, and no stop condition occurs.

The attempt stops immediately after evidence preservation on any of:

- CPU offload or partial CPU/GPU placement;
- use of an unselected GPU;
- HTTP 503, OOM, Ollama process crash, or terminal transport failure;
- parse failure or an unexpected parse retry under the zero-retry acceptance
  rule;
- unexpected model digest, template, quantization, or allocated context;
- raw/evidence manifest inconsistency, output collision, or strict-validator
  failure; or
- missing provenance required by this specification.

No later 4A stage starts until 4A-1 evidence has been checked.

## 9. Gate 4A-2: QQQ one-cell run smoke

Gate 4A-2 is one `qqq-full` run, not an incomplete eight-cell batch:

```text
model condition = QQQ
model = qwen2.5:3b
edge policy = full
agents = 12
steps = 1
expected logical calls = 24
max_concurrency = 1
execution_mode = reference_ollama
research_eligible = false
```

It passes only if the run completes all four phases, strict run validation is
valid, Phase 1 and Phase 3 each account for twelve logical calls, Phase 2
delivery begins after the Phase 1 barrier, all Phase 3 decisions precede Phase
4 movement, and the following counters are all zero:

```text
transport_failures
generation_retries
syntax_parse_attempt_failures
syntax_parse_failures
schema_validation_failures
```

The expected normal-path HTTP attempt count is therefore 24. A recovered retry
does not satisfy this reference acceptance rule even if final parsing succeeds.

After the concurrency-1 PASS, repeat the same declared condition separately at
`max_concurrency = 2`, then separately at `max_concurrency = 4`. Each value has
its own config hash, run ID, and fresh output directory. All fields other than
the declared concurrency and identity/provenance fields remain paired.

The comparison covers the logical call set, prompt hashes, phase semantics,
completion, wall time, queueing, telemetry, and raw schema. Generated text is
not required to be byte-identical.

## 10. Gate 4A-3: HET one-cell run smoke

Before the HET run, load and check each model separately under the single-model
contract:

```text
qwen2.5:3b
gemma3:4b
llama3.2:3b
```

For each model, preserve digest, quantization, exact chat template and hash,
allocated context, VRAM, `/api/ps`, `ollama ps`, and evidence of full GPU
residency. A failure for any individual model stops the stage.

Only after all three individual checks pass may the stage consider
`OLLAMA_MAX_LOADED_MODELS=3`; any required server restart and its environment
are recorded. The HET run uses:

```text
model condition = HET
edge policy = full
agents = 12, four per model family
steps = 1
expected logical calls = 24
max_concurrency = 1
execution_mode = reference_ollama
research_eligible = false
```

The model-to-bloc assignment follows the Gate 3 rotation. The run applies the
same barrier, strict-validation, zero-failure, zero-retry, and evidence rules as
Gate 4A-2.

If three models cannot remain fully GPU-resident, CPU offload is not an accepted
fallback. Stop and preserve the negative evidence. A later approved amendment
may assign model families to separate GPU-bound Ollama servers and ports; that
deployment mapping becomes an explicit backend condition and must not be
silently substituted into this attempt.

## 11. Gate 4A-4: one-replicate eight-cell reference smoke

Gate 4A-4 is the first full Gate 3 matrix shape executed on the real reference
backend:

```text
replicates = 1
cells = 8 in the frozen canonical order
steps per run = 1
outer-run parallelism = 1
execution_mode = reference_ollama
research_eligible = false
```

Cells execute sequentially. Intra-phase concurrency remains the explicitly
declared and persisted value. The batch passes only when all of the following
are mechanically observed:

```text
planned = 8
started = 8
completed = 8
strict-valid = 8
reference-Ollama smoke PASS = 8
failed = 0
aborted = 0
not_started = 0
transport_failures = 0
generation_retries = 0
syntax_parse_attempt_failures = 0
syntax_parse_failures = 0
schema_validation_failures = 0
```

Every planned row, config, run directory, raw manifest, strict result, smoke
result, model artifact, and failed/negative artifact is retained in the batch
evidence. A partial batch is not forced through the research validator as a
PASS. This stage is a reference-backend smoke, not a pilot.

## 12. Ollama reference-backend evidence freeze

After 4A-1 through 4A-4 pass, an independent checker verifies the complete
evidence trees read-only, recomputes every manifest/hash/count, confirms the
source and prompt pins, confirms expected model identities and GPU placement,
and records all retained failed or superseded attempts.

The checked bundle receives an immutable evidence ID and frozen manifest hash.
The runs, configs, raw logs, API responses, and prior manifests are not edited
to insert that later freeze ID. Future plans may reference the frozen evidence;
the runs that generated it may not circularly claim it as pre-existing frozen
evidence.

Freezing this reference-backend smoke does not by itself freeze production
models or the production candidate registry and does not change
`research_eligible = false` for any Gate 4A run.

## 13. Gate 4B: vLLM adapter and smoke

Gate 4B remains `DEFERRED / BLOCKED ON OLLAMA EVIDENCE FREEZE` until section 12
is complete. Its transport contract is:

```text
provider = vllm
transport = openai_compatible
endpoint = /v1/chat/completions
```

The adapter requires an explicit request/response and error contract, provider
validation, configuration provenance, response-to-existing-telemetry mapping,
and regression tests before a real vLLM request. Because this changes the
backend request contract, the Phase-Preserving Parallelism specification must
be versioned and re-pinned. If execution-mode, plan, or manifest fields change,
the matrix specification and affected schemas must also be versioned and
regression-tested.

The vLLM evidence bundle records the exact checkpoint/revision, served model
name, tokenizer revision, vLLM version and launch arguments, dtype,
quantization, tensor-parallel layout, GPU UUIDs, generation configuration, and
the exact chat-template bytes and SHA-256. Chat-template absence or mismatch is
a stop condition, not a value inferred after generation.

After adapter regressions pass, Gate 4B repeats the same staged expansion:

1. one model and one request;
2. one QQQ full cell, twelve agents, one step;
3. individual-model checks followed by one HET full cell; and
4. one replicate, eight cells, one step, sequential outer execution.

Gate 4B compares the same simulation phase semantics, prompt source, sampling
intent, logical request set, raw schema, strict/smoke eligibility behavior, and
completeness of backend-specific artifacts. Ollama and vLLM response text need
not match. All Gate 4B runs remain `research_eligible = false`.

## 14. Version and regression consequences

- A change to prompt semantics requires Su's explicit approval, a new prompt
  hash, and the applicable protocol update.
- A change to phase snapshots, barriers, ordering, failure selection,
  concurrency meaning, telemetry taxonomy, or backend request contract requires
  a Phase-Preserving Parallelism specification version update and regression
  evidence.
- A change to execution-mode propagation, cell/order semantics, plan fields, or
  batch evidence requires the applicable matrix, plan, and batch-manifest
  version updates and fail-closed validator regressions.
- A new non-scientific backend sidecar uses its own versioned schema. Adding or
  changing scientific raw fields or `run_meta.json` contract requires the
  applicable log-schema and strict-validator update.
- `metric-v2.0.0` remains unchanged only while its raw inputs and meanings remain
  unchanged.
- Documentation hashes cited by the protocol must be recalculated after any
  byte change; frozen Gate 0--3 tags and historical review records are retained.
