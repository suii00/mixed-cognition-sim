import json
import os
import random
import time
from datetime import datetime, timezone
from typing import Dict, List, Any, Optional, Tuple

from engine.world import World
from engine.agent import Agent
from engine.llm_client import call_ollama, extract_json
from engine.prompts import build_phase1_prompt, build_phase3_prompt


class Simulation:
    def __init__(self, config: Dict[str, Any]):
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

        self.world = World(self.half_space_size, config["places"])
        self.rng = random.Random(self.seed)
        self.agents: List[Agent] = []
        self.parse_error_count = 0
        self.total_llm_calls = 0

        self._init_agents(config["blocs"])

        self.output_dir = f"output_{self.run_name}"
        os.makedirs(self.output_dir, exist_ok=True)

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
        try:
            parsed, raw = call_ollama(
                prompt=prompt,
                model=agent.model,
                base_url=agent.base_url,
                temperature=self.temperature,
                max_tokens=self.max_tokens,
                timeout_s=self.timeout_s,
                llm_overrides=agent.llm_overrides,
            )
            if parsed is None:
                self.parse_error_count += 1
            return parsed, raw
        except RuntimeError as e:
            print(f"[FATAL] LLM connection failed for agent {agent.agent_id}: {e}")
            raise

    def _log_jsonl(self, filename: str, record: Dict) -> None:
        path = os.path.join(self.output_dir, filename)
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")

    def run(self) -> None:
        start_time = datetime.now(timezone.utc).isoformat()
        print(f"=== Simulation '{self.run_name}' starting ===")
        print(f"  Duration: {self.duration} steps")
        print(f"  Agents: {len(self.agents)}")
        print(f"  Seed: {self.seed}")

        try:
            for step in range(1, self.duration + 1):
                print(f"\n--- Step {step}/{self.duration} ---")
                self._run_step(step)
        except RuntimeError as e:
            print(f"\n[ABORT] Simulation aborted at step: {e}")
            self._write_meta(start_time, aborted=True)
            return

        self._write_meta(start_time, aborted=False)
        print(f"\n=== Simulation '{self.run_name}' completed ===")
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
        for agent in self.agents:
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

            # Phase 4: execute movement
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

            print(f"  Phase 3-4: Agent {agent.agent_id} ({agent.bloc}) -> "
                  f"{action} {direction} @ {agent.position}")

    def _write_meta(self, start_time: str, aborted: bool) -> None:
        end_time = datetime.now(timezone.utc).isoformat()
        parse_rate = (self.parse_error_count / self.total_llm_calls
                      if self.total_llm_calls > 0 else 0.0)

        meta = {
            "run_name": self.run_name,
            "config": self.config,
            "seed": self.seed,
            "start_time": start_time,
            "end_time": end_time,
            "aborted": aborted,
            "total_llm_calls": self.total_llm_calls,
            "parse_errors": self.parse_error_count,
            "parse_error_rate": parse_rate,
        }

        path = os.path.join(self.output_dir, "run_meta.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(meta, f, indent=2, ensure_ascii=False)
