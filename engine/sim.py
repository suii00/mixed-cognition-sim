import json
import os
import random
from pathlib import Path
from typing import Dict, List, Any, Optional, Tuple

from engine.world import World
from engine.agent import Agent
from engine.llm_client import LLMTransportError, call_ollama
from engine.prompts import build_phase1_prompt, build_phase3_prompt
from engine.provenance import RunLifecycle


class SimulationAbortedError(RuntimeError):
    """A controlled run abort that must produce a non-zero CLI exit."""


class Simulation:
    def __init__(self, config: Dict[str, Any],
                 output_root: Optional[Path] = None,
                 repo_root: Optional[Path] = None):
        self.config = config
        sim_cfg = config["simulation"]
        self.duration = sim_cfg["duration"]
        self.half_space_size = sim_cfg["half_space_size"]
        self.seed = sim_cfg["seed"]
        self.run_name = sim_cfg["run_name"]

        agent_cfg = config["agents"]
        self.communication_radius = agent_cfg["communication_radius"]
        self.memory_limit = agent_cfg["memory_limit"]
        self.memory_size = agent_cfg["memory_size"]
        self.message_history_limit = agent_cfg["message_history_limit"]
        self.message_context_size = agent_cfg["message_context_size"]

        llm = config["llm_defaults"]
        self.temperature = llm.get("temperature", 0.2)
        self.max_tokens = llm.get("max_tokens", 1024)
        self.timeout_s = llm.get("timeout_s", 120)

        self.agents: List[Agent] = []
        self.parse_error_count = 0
        self.total_llm_calls = 0

        self.run_lifecycle = RunLifecycle.create(
            config,
            output_root=output_root,
            repo_root=repo_root,
        )
        self.run_id = self.run_lifecycle.run_id
        self.output_dir = str(self.run_lifecycle.output_dir)

        try:
            self.world = World(self.half_space_size, config["places"])
            self.rng = random.Random(self.seed)
            self._init_agents(config["blocs"])
        except KeyboardInterrupt as error:
            self._best_effort_finalize(
                "aborted", "keyboard_interrupt", type(error).__name__
            )
            raise
        except BaseException as error:
            self._best_effort_finalize(
                "failed", "initialization_failure", type(error).__name__
            )
            raise

    def _best_effort_finalize(
        self,
        status: str,
        reason: str,
        exception_type: Optional[str],
    ) -> None:
        try:
            self.run_lifecycle.finalize_failure(status, reason, exception_type)
        except BaseException:
            # Preserve the original failure. The last valid running meta remains.
            pass

    def _init_agents(self, blocs_cfg: List[Dict]) -> None:
        total_agents = sum(b["num_agents"] for b in blocs_cfg)
        positions = self.world.generate_initial_positions(total_agents, self.rng)

        agent_id = 0
        for bloc in blocs_cfg:
            for _ in range(bloc["num_agents"]):
                agent = Agent(
                    agent_id=agent_id,
                    bloc=bloc["name"],
                    model=bloc["model"],
                    base_url=bloc["base_url"],
                    position=positions[agent_id],
                    memory_limit=self.memory_limit,
                    memory_size=self.memory_size,
                    message_history_limit=self.message_history_limit,
                    message_context_size=self.message_context_size,
                    llm_overrides=bloc.get("llm_overrides"),
                )
                self.agents.append(agent)
                agent_id += 1

    def _get_positions(self) -> Dict[int, Tuple[int, int]]:
        return {a.agent_id: a.position for a in self.agents}

    def _can_communicate(self, a1: Agent, a2: Agent) -> bool:
        dist = self.world.euclidean_distance(
            a1.position[0], a1.position[1],
            a2.position[0], a2.position[1],
        )
        if dist > self.communication_radius:
            return False
        p1 = self.world.get_place_for(a1.position[0], a1.position[1])
        p2 = self.world.get_place_for(a2.position[0], a2.position[1])
        if p1 is None and p2 is None:
            return True
        if p1 is not None and p2 is not None and p1.name == p2.name:
            return True
        return False

    def _call_llm(self, agent: Agent, prompt: str) -> Tuple[Optional[Dict], str]:
        self.total_llm_calls += 1
        self.run_lifecycle.increment("logical_llm_calls")
        try:
            parsed, raw = call_ollama(
                prompt=prompt,
                model=agent.model,
                base_url=agent.base_url,
                temperature=self.temperature,
                max_tokens=self.max_tokens,
                timeout_s=self.timeout_s,
                llm_overrides=agent.llm_overrides,
                telemetry=self.run_lifecycle.record_llm_telemetry,
            )
            if parsed is None:
                self.parse_error_count += 1
                self.run_lifecycle.increment("syntax_parse_failures")
            return parsed, raw
        except LLMTransportError:
            print(f"[FATAL] LLM transport failed for agent {agent.agent_id}")
            raise

    def _log_jsonl(self, filename: str, record: Dict) -> None:
        path = os.path.join(self.output_dir, filename)
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")

    def run(self) -> None:
        try:
            print(f"=== Simulation '{self.run_name}' ({self.run_id}) starting ===")
            print(f"  Duration: {self.duration} steps")
            print(f"  Agents: {len(self.agents)}")
            print(f"  Seed: {self.seed}")

            for step in range(1, self.duration + 1):
                self.run_lifecycle.set_context(step, "step_start", None)
                print(f"\n--- Step {step}/{self.duration} ---")
                self._run_step(step)
                self.run_lifecycle.mark_step_completed(step)
            self.run_lifecycle.set_context(None, "finalize", None)
            self.run_lifecycle.finalize_completed()
        except KeyboardInterrupt as error:
            self._best_effort_finalize(
                "aborted", "keyboard_interrupt", type(error).__name__
            )
            raise
        except LLMTransportError as error:
            self._best_effort_finalize(
                "aborted", "transport_failure", type(error).__name__
            )
            raise SimulationAbortedError(
                "simulation aborted due to a terminal LLM transport failure"
            ) from error
        except BaseException as error:
            self._best_effort_finalize(
                "failed", "unhandled_exception", type(error).__name__
            )
            raise

        print(f"\n=== Simulation '{self.run_name}' ({self.run_id}) completed ===")
        print(f"  Total LLM calls: {self.total_llm_calls}")
        print(f"  Parse errors: {self.parse_error_count}")
        if self.total_llm_calls > 0:
            rate = self.parse_error_count / self.total_llm_calls
            print(f"  Parse error rate: {rate:.2%}")

    def _run_step(self, step: int) -> None:
        positions = self._get_positions()

        # Phase 1: message decision
        phase1_results: Dict[int, Tuple[Optional[Dict], str]] = {}
        for agent in self.agents:
            self.run_lifecycle.set_context(step, "phase1", agent.agent_id)
            place = self.world.get_place_for(*agent.position)
            agent_count = (self.world.count_agents_in_place(place, positions)
                           if place else 0)
            prompt = build_phase1_prompt(
                agent_id=agent.agent_id,
                x=agent.position[0], y=agent.position[1],
                half_space_size=self.half_space_size,
                places=self.world.places,
                place=place,
                agent_count=agent_count,
                memories=agent.get_recent_memories(),
                messages=agent.get_recent_messages(),
            )
            parsed, raw = self._call_llm(agent, prompt)
            phase1_results[agent.agent_id] = (parsed, raw)

            self._log_jsonl("phase1_raw.jsonl", {
                "step": step,
                "agent_id": agent.agent_id,
                "bloc": agent.bloc,
                "model": agent.model,
                "parsed": parsed,
                "raw_output": raw,
            })
            self.run_lifecycle.observe_agent(agent.agent_id)

            if parsed is None:
                self._log_jsonl("parse_errors.jsonl", {
                    "step": step,
                    "agent_id": agent.agent_id,
                    "phase": 1,
                    "raw_output": raw,
                })

            print(f"  Phase 1: Agent {agent.agent_id} ({agent.bloc}) done")

        # Phase 2: message delivery
        for sender in self.agents:
            self.run_lifecycle.set_context(step, "phase2", sender.agent_id)
            parsed, _ = phase1_results[sender.agent_id]
            if parsed is None:
                continue
            message_text = parsed.get("message", "")
            if not message_text:
                continue
            reasoning = parsed.get("reasoning", "")

            receiver_ids = []
            for receiver in self.agents:
                if receiver.agent_id == sender.agent_id:
                    continue
                if self._can_communicate(sender, receiver):
                    receiver.add_received_message(
                        sender.agent_id, message_text, step
                    )
                    receiver_ids.append(receiver.agent_id)

            if receiver_ids:
                self._log_jsonl("messages.jsonl", {
                    "step": step,
                    "sender_id": sender.agent_id,
                    "sender_bloc": sender.bloc,
                    "sender_model": sender.model,
                    "receiver_ids": receiver_ids,
                    "message": message_text,
                    "reasoning": reasoning,
                })

        # Phase 3: action decision
        phase3_actions: Dict[int, Tuple[str, str]] = {}
        for agent in self.agents:
            self.run_lifecycle.set_context(step, "phase3", agent.agent_id)
            place = self.world.get_place_for(*agent.position)
            agent_count = (self.world.count_agents_in_place(place, positions)
                           if place else 0)
            prompt = build_phase3_prompt(
                agent_id=agent.agent_id,
                x=agent.position[0], y=agent.position[1],
                half_space_size=self.half_space_size,
                places=self.world.places,
                place=place,
                agent_count=agent_count,
                memories=agent.get_recent_memories(),
                messages=agent.get_recent_messages(),
            )
            parsed, raw = self._call_llm(agent, prompt)

            if parsed is None:
                self._log_jsonl("parse_errors.jsonl", {
                    "step": step,
                    "agent_id": agent.agent_id,
                    "phase": 3,
                    "raw_output": raw,
                })
                action = "stay"
                direction = ""
                memory_text = ""
                reasoning = ""
            else:
                action = parsed.get("action", "stay")
                direction = parsed.get("direction", "")
                memory_text = parsed.get("memory", "")
                reasoning = parsed.get("reasoning", "")

            if memory_text:
                agent.add_memory(memory_text)

            self._log_jsonl("memory_reasoning.jsonl", {
                "step": step,
                "agent_id": agent.agent_id,
                "bloc": agent.bloc,
                "model": agent.model,
                "position": list(agent.position),
                "action": action,
                "direction": direction,
                "memory": memory_text,
                "reasoning": reasoning,
            })
            self.run_lifecycle.observe_agent(agent.agent_id)

            phase3_actions[agent.agent_id] = (action, direction)

        # Phase 4: execute movement only after every Phase 3 decision completes.
        for agent in sorted(self.agents, key=lambda item: item.agent_id):
            self.run_lifecycle.set_context(step, "phase4", agent.agent_id)
            action, direction = phase3_actions[agent.agent_id]
            if action == "move" and direction:
                x, y = agent.position
                if direction == "up":
                    y += 1
                elif direction == "down":
                    y -= 1
                elif direction == "left":
                    x -= 1
                elif direction == "right":
                    x += 1
                agent.position = self.world.clamp(x, y)

            print(f"  Phase 4: Agent {agent.agent_id} ({agent.bloc}) -> "
                  f"{action} {direction} @ {agent.position}")

        self.run_lifecycle.set_context(step, "step_complete", None)
