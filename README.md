# mixed-cognition-sim

Multi-LLM agent simulation for studying emergent behavior in mixed-cognition populations.

## Credit

This project builds on the paradigm introduced by [ryukih/llm-agents-simulation](https://github.com/ryukih/llm-agents-simulation), which established a fire-evacuation observation task for LLM agents. The present implementation is written from scratch based on an independent design specification, with no code reuse from the original repository.

## Overview

Agents inhabit a 2D grid world with named locations. Each agent is backed by a different LLM model (routed via Ollama), grouped into "blocs." Agents are unaware of their own model or bloc assignment. The simulation runs a synchronous 4-phase loop per step:

1. **Phase 1**: Each agent decides what message to send
2. **Phase 2**: Messages are delivered to nearby agents (Euclidean distance + same-region constraint)
3. **Phase 3**: Each agent decides an action (move/stay) and writes a memory note
4. **Phase 4**: Movement is executed (1 cell, clamped to grid bounds)

## Requirements

- Python 3.10+
- Ollama running locally (or at a configured endpoint)
- Dependencies: `requests`, `pyyaml`

```bash
pip install -r requirements.txt
```

## Usage

```bash
python main.py --config configs/smoke_local.yaml
```

Output is written to `output_<run_name>/`.

## Config Schema

```yaml
simulation:
  duration: 15          # number of steps
  half_space_size: 25   # grid ranges [-S, +S]
  seed: 42              # RNG seed
  run_name: smoke_local # output directory suffix

blocs:
  - name: alpha
    model: "qwen2.5:3b"
    base_url: "http://localhost:11434"
    num_agents: 2
    # llm_overrides: {}  # optional per-bloc LLM parameter overrides

agents:
  communication_radius: 8       # Euclidean distance for message delivery
  memory_limit: 20              # max stored memories
  memory_size: 5                # memories shown in prompt
  message_history_limit: 10     # max stored received messages
  message_context_size: 3       # messages shown in prompt

places:
  - name: left_bar
    center_x: -15
    center_y: 0
    half_size: 5
    capacity: 6

llm_defaults:
  temperature: 0.2
  max_tokens: 1024
  timeout_s: 120
```

## Log Schema

All logs are in `output_<run_name>/`:

- **messages.jsonl**: `{step, sender_id, sender_bloc, sender_model, receiver_ids, message, reasoning}` -- delivered messages only
- **phase1_raw.jsonl**: `{step, agent_id, bloc, model, parsed, raw_output}` -- all Phase 1 outputs for diagnostics
- **memory_reasoning.jsonl**: `{step, agent_id, bloc, model, position, action, direction, memory, reasoning}`
- **run_meta.json**: config snapshot, seed, timestamps, parse error rate
- **parse_errors.jsonl**: `{step, agent_id, phase, raw_output}` -- failed JSON parses

## Vocabulary Metrics

```bash
python tools/vocab_metrics.py output_smoke_local
```

Produces `vocab_report.md` (per-bloc distinctive words + crossover events) and `vocab_events.csv`.
