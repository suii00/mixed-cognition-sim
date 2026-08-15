# Phase-Preserving Parallel Transport Specification

## 1. Version and scope

Specification version: `phase-parallelism-v1.0.0`.

This specification defines bounded threaded execution of the blocking LLM
transport in simulation Phase 1 and Phase 3. Its purpose is throughput only.
It preserves the simulator's phase barriers, prompt inputs, scientific raw-log
schema, state-transition rules, lifecycle accounting, and deterministic
coordinator commit order.

The conformance claim is limited to deterministic scripted transports. It does
not claim that a real model backend produces identical text under different
request concurrency.

## 2. Non-goals

This version does not:

- change `engine/prompts.py` or prompt semantics;
- change the Phase 1, delivery, Phase 3, or movement interpretation;
- change communication radius, place-boundary, self-delivery, trimming, clamp,
  parse-fallback, or raw-log rules;
- parallelize delivery or movement;
- add process pools, `asyncio`, cancellation, early abort, or phase overlap;
- add an arbitrary callable to production configuration;
- define vLLM request behavior, model batching equivalence, matrix execution,
  a production registry, a pilot, or a research result;
- change Metric v2.

## 3. Concurrency configuration

The execution setting is:

```yaml
llm_defaults:
  max_concurrency: 1
```

`max_concurrency` MUST be a positive integer. Booleans, zero, negative values,
floats, strings, and null are invalid. Omission has the effective value `1`.
Concurrency 1 and N MUST use the same batch executor and code path; only the
executor's maximum worker count differs. A phase with fewer requests than the
configured limit MUST create no more workers than requests. An empty request
batch MUST be valid and create no executor.

The setting limits simultaneous transport calls within one Phase 1 or Phase 3
batch. It does not permit two phases or two steps to overlap.

## 4. Effective config provenance

`Simulation` MUST deep-copy its input config, validate and insert the effective
`llm_defaults.max_concurrency`, and pass that owned effective config to
`RunLifecycle.create`. It MUST NOT mutate the caller's config object. The saved
config snapshot and its canonical config hash therefore identify the actual
concurrency setting, including the default value `1` when it was omitted.

## 5. Request contract

Each worker request is an immutable identity/value envelope containing:

- `request_id`;
- `step`;
- `phase` (`phase1` or `phase3`);
- `agent_id`;
- model and base URL;
- the fully constructed prompt;
- temperature, maximum tokens, and timeout;
- a deep copy of `llm_overrides`.

The canonical request identity format is:

```text
step-<six digits>:<phase>:agent-<six digits>
```

A request MUST NOT contain `Simulation`, mutable `Agent`, `RunLifecycle`, world,
open log handle, shared counter, or shared telemetry objects. Request IDs and
agent IDs MUST be unique within a phase batch.

## 6. Worker result contract

A worker returns only:

- the unchanged request identity fields;
- parsed result or null;
- raw output;
- worker-local telemetry;
- no error, a terminal transport error, or an unexpected exception.

Exceptions are returned as result data so every submitted future can settle.
The coordinator re-raises the deterministically selected original exception
only after the executor has shut down.

## 7. Worker-local telemetry

Each worker owns a collector for:

- `http_attempts`;
- `generation_retries`;
- `transport_failures`;
- `syntax_parse_attempt_failures`.

The reference LLM client callback records only in that collector. After the
entire batch settles, the coordinator adds each canonical result's telemetry to
the lifecycle. The coordinator adds one `logical_llm_calls` per submitted
request. It derives final `syntax_parse_failures` and
`Simulation.parse_error_count` only from error-free results whose `parsed`
value is null.

## 8. Coordinator-only mutation

Worker threads MUST NOT:

- mutate lifecycle state or call lifecycle counter/context methods;
- mutate simulation counters;
- write raw JSONL or print phase progress;
- add memory or received messages;
- assign an agent position;
- mutate config, world, agent, or snapshot state.

The thread that invokes `Simulation.run` is the coordinator. Only that thread
applies telemetry/counters, selects terminal errors, writes logs, prints phase
progress, observes agents, delivers messages, commits memories, and moves
agents.

## 9. Canonical ordering

The canonical agent order is ascending `agent_id`, independent of the internal
`self.agents` list order. The batch order key is:

```text
step, phase order, agent_id, request_id
```

Prompt construction, request submission, result return, result commit, sender
and receiver delivery, movement, progress output, parse-error records, and raw
JSONL records MUST follow canonical order. Future completion order has no
scientific meaning.

## 10. Phase 1 snapshot and batch

At step start, before dispatching any Phase 1 request, the coordinator copies:

- every position;
- each agent's recent memories and received messages;
- places and the applicable place;
- place occupancy derived from the copied positions;
- the world-bound value used by prompt construction.

It then constructs every Phase 1 prompt and request before starting the first
worker. It submits the complete canonical request set, waits for every future,
shuts down the executor, applies all worker facts, and evaluates terminal
errors. Only an error-free batch may commit `phase1_raw.jsonl`, Phase 1
parse-error records, observed-agent state, and canonical progress output.

## 11. Phase 2 delivery barrier

Phase 2 remains sequential and cannot begin until every Phase 1 result has
settled and every Phase 1 result has been committed. Delivery uses the Phase 1
step-start position snapshot, not mutable later positions. Senders and receivers
are considered in ascending ID order. Existing communication, place, self-send,
message/reasoning, and received-message trimming semantics remain unchanged.

## 12. Phase 3 snapshot and batch

Only after all delivery commits, the coordinator copies every current position,
recent memory, recent received message, place, and occupancy. It constructs all
Phase 3 prompts and requests from that common post-delivery/pre-action snapshot
before dispatch.

It submits the complete canonical request set, waits for every future, shuts
down the executor, applies worker facts, and evaluates terminal errors. Only an
error-free batch may interpret results, append Phase 3 parse errors, add memory,
write `memory_reasoning.jsonl`, or observe agents. Memory and reasoning commits
are in ascending agent ID order and retain the snapshot position.

## 13. Phase 4 movement barrier

Phase 4 remains sequential. It begins only after all Phase 3 results and all
Phase 3 memory/reasoning commits are complete. It applies only the already
interpreted action/direction pairs, in ascending agent ID order, using the
existing direction and clamp rules. No worker can move an agent.

## 14. Parse failure semantics

A final parse failure is non-terminal and does not short-circuit the batch.

For Phase 1, null `parsed` and raw output are written to `phase1_raw.jsonl` and
`parse_errors.jsonl`; no message is delivered for that result.

For Phase 3, null `parsed` is written to `parse_errors.jsonl` and committed to
`memory_reasoning.jsonl` as `stay`, empty direction, empty memory, and empty
reasoning. It adds no memory and causes no movement. Other agents' successful
results retain the barrier.

## 15. Terminal transport failure semantics

If one or more workers returns `LLMTransportError`, the coordinator MUST:

1. let every submitted request settle and close the executor;
2. reflect every request and all worker-local telemetry;
3. select the lowest failing agent ID, unless an unexpected error exists;
4. set deterministic step/phase/agent lifecycle context;
5. commit no primary result log or agent state for that phase;
6. re-raise the selected transport error so the run becomes `aborted` with
   reason `transport_failure`.

For a Phase 1 failure, that step has no Phase 1 raw commit, delivery, Phase 3,
movement, or completed-step increment. For a Phase 3 failure, already committed
Phase 1 and delivery remain, but that step has no Phase 3 memory/reasoning
commit, memory mutation, movement, or completed-step increment.

## 16. Unexpected worker exception semantics

An unexpected worker exception MUST NOT be converted to a transport failure.
Every request still settles and all worker facts are accounted. The coordinator
selects the lowest-agent-ID unexpected exception, sets its deterministic
context, commits no phase result/state, and re-raises that same exception. The
outer lifecycle records `failed`, `unhandled_exception`, and the original
exception type.

Error priority is:

```text
unexpected worker exception
> terminal transport error
> parse failure
> normal result
```

Within the selected error class, lowest `agent_id` wins, regardless of completion
order or configured concurrency.

## 17. Deterministic call set and executor lifetime

Every request constructed for a phase is submitted. Discovery of an error MUST
NOT cancel, omit, or early-abort another request. All futures settle. The fixed
worker thread prefix is `gate2-llm`, and executor shutdown completes before
coordinator accounting or exception propagation. Normal, parse-failure,
transport-failure, and unexpected-failure paths MUST leave no such threads.

## 18. Reference transport and deferred backends

The default transport remains `engine.sim.call_ollama`, resolved at worker
invocation time so the established patch seam remains valid. It receives the
request values, a fresh copy of overrides, and worker-local telemetry callback.
Tests may inject an internal callable accepting request and telemetry objects;
production config cannot select Python callables.

vLLM API behavior and real-backend concurrency are deferred. Adding a vLLM
adapter requires an explicit backend request contract and appropriate spec
version change; this version supplies no vLLM conformance claim.

## 19. Equivalence boundary

For a deterministic scripted transport and identical world, seed, agent set,
prompt inputs, and generation values, concurrency 1 and N MUST produce equal:

- exact bytes of the four scientific raw JSONL files;
- positions, memories, received messages, RNG state, and simulation counters;
- lifecycle counters, completed steps, observed agents, and raw manifest;
- request identity, exact prompt, endpoint/model, and generation parameters.

`run_meta.json` itself is not expected to be byte-identical because run ID,
timestamps, concurrency config, and config hash intentionally differ. This
specification makes no real-Ollama or real-model output equality claim.

## 20. Compatibility and versioning

The schemas and meanings of `phase1_raw.jsonl`, `messages.jsonl`,
`memory_reasoning.jsonl`, and `parse_errors.jsonl` are unchanged. Prompt bytes
are governed by the unchanged `engine/prompts.py`. Metric `metric-v2.0.0`
continues to consume the same raw fields and phase order.

Changing any of the following requires a phase-parallelism spec version update
and regression evidence:

- snapshot contents;
- phase commit or barrier rules;
- parse, transport, unexpected-error, or failure-selection rules;
- canonical ordering;
- telemetry taxonomy or accounting;
- concurrency interpretation;
- worker/coordinator ownership;
- backend request contract;
- raw schema or prompt semantics.

Raw-schema, prompt-semantic, phase-semantic, protocol, or metric changes may
also require their separately governed version updates and approvals.

## 21. Required regression fixtures

`tests/test_phase_parallelism.py` covers:

- omitted, explicit, and invalid concurrency plus config ownership/provenance;
- request ownership, duplicate rejection, and empty batches;
- worker-local telemetry before and after settlement;
- coordinator-only mutation instrumentation;
- concurrency bounds and actual overlap without time-based sleeps;
- all-prompt-before-dispatch checks for Phase 1 and Phase 3;
- reverse completion with canonical log, lifecycle, progress, and state commit;
- three-agent/two-step concurrency 1/N byte and state equivalence;
- agent-list order invariance;
- Phase 1 and Phase 3 parse-failure equivalence;
- Phase 1 and Phase 3 terminal failure atomicity and all-request settlement;
- multiple transport errors and deterministic minimum-agent selection;
- unexpected-error preservation, precedence, and deterministic selection;
- delivery, Phase 3 snapshot, and movement barriers using events;
- no Gate 2 worker leak across all four result classes;
- a fail-closed guard against real network access.

The full pre-existing regression suite remains required. Tests MUST NOT rely on
sleep duration, real LLMs, Ollama/vLLM services, GPUs, or external network calls.
