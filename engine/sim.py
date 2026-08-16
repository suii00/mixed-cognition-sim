import copy
import json
import os
import random
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from engine.agent import Agent
from engine.config import build_effective_config
from engine.llm_client import LLMTransportError, call_ollama
from engine.parallel_transport import (
    LLMRequest,
    LLMResult,
    TransportInvocation,
    execute_llm_batch,
)
from engine.prompts import build_phase1_prompt, build_phase3_prompt
from engine.provenance import RunLifecycle
from engine.world import World


class SimulationAbortedError(RuntimeError):
    """A controlled run abort that must produce a non-zero CLI exit."""


class Simulation:
    def __init__(
        self,
        config: Dict[str, Any],
        output_root: Optional[Path] = None,
        repo_root: Optional[Path] = None,
        transport: Optional[TransportInvocation] = None,
    ):
        # Own the effective config so execution-affecting defaults are captured
        # by provenance without mutating the caller's object.
        self.config = build_effective_config(config)
        sim_cfg = self.config["simulation"]
        self.duration = sim_cfg["duration"]
        self.half_space_size = sim_cfg["half_space_size"]
        self.seed = sim_cfg["seed"]
        self.run_name = sim_cfg["run_name"]

        agent_cfg = self.config["agents"]
        self.communication_radius = agent_cfg["communication_radius"]
        self.edge_policy = agent_cfg["edge_policy"]
        self.memory_limit = agent_cfg["memory_limit"]
        self.memory_size = agent_cfg["memory_size"]
        self.message_history_limit = agent_cfg["message_history_limit"]
        self.message_context_size = agent_cfg["message_context_size"]

        llm = self.config["llm_defaults"]
        self.temperature = llm.get("temperature", 0.2)
        self.max_tokens = llm.get("max_tokens", 1024)
        self.timeout_s = llm.get("timeout_s", 120)
        self.max_concurrency = llm["max_concurrency"]
        self._transport = transport

        self.agents: List[Agent] = []
        self.parse_error_count = 0
        self.total_llm_calls = 0

        self.run_lifecycle = RunLifecycle.create(
            self.config,
            output_root=output_root,
            repo_root=repo_root,
        )
        self.run_id = self.run_lifecycle.run_id
        self.output_dir = str(self.run_lifecycle.output_dir)

        try:
            self.world = World(self.half_space_size, self.config["places"])
            self.rng = random.Random(self.seed)
            self._init_agents(self.config["blocs"])
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

    def _ordered_agents(self) -> List[Agent]:
        return sorted(self.agents, key=lambda agent: agent.agent_id)

    def _get_positions(self) -> Dict[int, Tuple[int, int]]:
        return {agent.agent_id: agent.position for agent in self.agents}

    def _can_communicate_positions(
        self,
        position1: Tuple[int, int],
        position2: Tuple[int, int],
    ) -> bool:
        dist = self.world.euclidean_distance(
            position1[0], position1[1], position2[0], position2[1]
        )
        if dist > self.communication_radius:
            return False
        place1 = self.world.get_place_for(*position1)
        place2 = self.world.get_place_for(*position2)
        if place1 is None and place2 is None:
            return True
        return (
            place1 is not None
            and place2 is not None
            and place1.name == place2.name
        )

    def _can_communicate(self, a1: Agent, a2: Agent) -> bool:
        if self.edge_policy == "within_bloc_only" and a1.bloc != a2.bloc:
            return False
        return self._can_communicate_positions(a1.position, a2.position)

    def _capture_phase_snapshot(self) -> Dict[str, Any]:
        """Copy all mutable prompt inputs before any request is dispatched."""
        positions = {
            agent.agent_id: tuple(agent.position)
            for agent in self._ordered_agents()
        }
        places = copy.deepcopy(self.world.places)
        agents: Dict[int, Dict[str, Any]] = {}
        for agent in self._ordered_agents():
            position = positions[agent.agent_id]
            place = next(
                (candidate for candidate in places if candidate.contains(*position)),
                None,
            )
            agent_count = (
                sum(1 for item in positions.values() if place.contains(*item))
                if place is not None
                else 0
            )
            agents[agent.agent_id] = {
                "position": position,
                "place": place,
                "agent_count": agent_count,
                "memories": copy.deepcopy(agent.get_recent_memories()),
                "messages": copy.deepcopy(agent.get_recent_messages()),
            }
        return {"positions": positions, "places": places, "agents": agents}

    @staticmethod
    def _request_id(step: int, phase: str, agent_id: int) -> str:
        return f"step-{step:06d}:{phase}:agent-{agent_id:06d}"

    def _build_phase_requests(
        self,
        step: int,
        phase: str,
        snapshot: Dict[str, Any],
    ) -> List[LLMRequest]:
        requests: List[LLMRequest] = []
        for agent in self._ordered_agents():
            state = snapshot["agents"][agent.agent_id]
            prompt_builder = (
                build_phase1_prompt if phase == "phase1" else build_phase3_prompt
            )
            prompt = prompt_builder(
                agent_id=agent.agent_id,
                x=state["position"][0],
                y=state["position"][1],
                half_space_size=self.half_space_size,
                places=snapshot["places"],
                place=state["place"],
                agent_count=state["agent_count"],
                memories=state["memories"],
                messages=state["messages"],
            )
            requests.append(
                LLMRequest(
                    request_id=self._request_id(step, phase, agent.agent_id),
                    step=step,
                    phase=phase,
                    agent_id=agent.agent_id,
                    model=agent.model,
                    base_url=agent.base_url,
                    prompt=prompt,
                    temperature=self.temperature,
                    max_tokens=self.max_tokens,
                    timeout_s=self.timeout_s,
                    llm_overrides=agent.llm_overrides,
                )
            )
        return requests

    @staticmethod
    def _default_transport(request: LLMRequest, telemetry):
        # Resolve engine.sim.call_ollama at invocation time so established
        # test patches remain effective.
        return call_ollama(
            prompt=request.prompt,
            model=request.model,
            base_url=request.base_url,
            temperature=request.temperature,
            max_tokens=request.max_tokens,
            timeout_s=request.timeout_s,
            llm_overrides=copy.deepcopy(request.llm_overrides),
            telemetry=telemetry,
        )

    def _execute_phase(self, requests: List[LLMRequest]) -> List[LLMResult]:
        invoke_transport = self._transport or self._default_transport
        results = execute_llm_batch(
            requests,
            self.max_concurrency,
            invoke_transport,
        )
        self._account_phase_results(results)
        return results

    def _account_phase_results(self, results: List[LLMResult]) -> None:
        """Apply worker facts and choose any terminal error deterministically."""
        self.total_llm_calls += len(results)
        self.run_lifecycle.increment("logical_llm_calls", len(results))
        for result in results:
            telemetry = result.telemetry
            self.run_lifecycle.increment("http_attempts", telemetry.http_attempts)
            self.run_lifecycle.increment(
                "generation_retries", telemetry.generation_retries
            )
            self.run_lifecycle.increment(
                "transport_failures", telemetry.transport_failures
            )
            self.run_lifecycle.increment(
                "syntax_parse_attempt_failures",
                telemetry.syntax_parse_attempt_failures,
            )
            if result.error_kind is None and result.parsed is None:
                self.parse_error_count += 1
                self.run_lifecycle.increment("syntax_parse_failures")

        unexpected = [
            result for result in results if result.error_kind == "unexpected"
        ]
        transport = [
            result for result in results if result.error_kind == "transport"
        ]
        errors = unexpected or transport
        selected = min(errors, key=lambda item: item.agent_id) if errors else None
        if selected is None:
            return
        self.run_lifecycle.set_context(
            selected.step,
            selected.phase,
            selected.agent_id,
        )
        if selected.error_kind == "transport":
            print(f"[FATAL] LLM transport failed for agent {selected.agent_id}")
        assert selected.error is not None
        raise selected.error

    def _log_jsonl(self, filename: str, record: Dict) -> None:
        path = os.path.join(self.output_dir, filename)
        with open(path, "a", encoding="utf-8") as file:
            file.write(json.dumps(record, ensure_ascii=False) + "\n")

    def run(self) -> None:
        # Claim outside the run's failure handler. A rejected concurrent or
        # repeated call is not an execution failure and must not mutate the
        # owning call's lifecycle metadata.
        self.run_lifecycle.claim_execution()
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
        ordered_agents = self._ordered_agents()
        agents_by_id = {agent.agent_id: agent for agent in ordered_agents}

        # Phase 1: all prompts share the copied step-start state.
        phase1_snapshot = self._capture_phase_snapshot()
        phase1_results = self._execute_phase(
            self._build_phase_requests(step, "phase1", phase1_snapshot)
        )
        phase1_by_agent = {result.agent_id: result for result in phase1_results}
        for agent in ordered_agents:
            result = phase1_by_agent[agent.agent_id]
            self.run_lifecycle.set_context(step, "phase1", agent.agent_id)
            self._log_jsonl(
                "phase1_raw.jsonl",
                {
                    "step": step,
                    "agent_id": agent.agent_id,
                    "bloc": agent.bloc,
                    "model": agent.model,
                    "parsed": result.parsed,
                    "raw_output": result.raw_output,
                },
            )
            self.run_lifecycle.observe_agent(agent.agent_id)
            if result.parsed is None:
                self._log_jsonl(
                    "parse_errors.jsonl",
                    {
                        "step": step,
                        "agent_id": agent.agent_id,
                        "phase": 1,
                        "raw_output": result.raw_output,
                    },
                )
            print(f"  Phase 1: Agent {agent.agent_id} ({agent.bloc}) done")

        # Phase 2: canonical delivery using only step-start positions.
        step_positions = phase1_snapshot["positions"]
        for sender in ordered_agents:
            self.run_lifecycle.set_context(step, "phase2", sender.agent_id)
            parsed = phase1_by_agent[sender.agent_id].parsed
            if parsed is None:
                continue
            message_text = parsed.get("message", "")
            if not message_text:
                continue
            reasoning = parsed.get("reasoning", "")
            receiver_ids = []
            for receiver in ordered_agents:
                if receiver.agent_id == sender.agent_id:
                    continue
                if (
                    self.edge_policy == "within_bloc_only"
                    and receiver.bloc != sender.bloc
                ):
                    continue
                if self._can_communicate_positions(
                    step_positions[sender.agent_id],
                    step_positions[receiver.agent_id],
                ):
                    receiver.add_received_message(
                        sender.agent_id,
                        message_text,
                        step,
                    )
                    receiver_ids.append(receiver.agent_id)
            if receiver_ids:
                self._log_jsonl(
                    "messages.jsonl",
                    {
                        "step": step,
                        "sender_id": sender.agent_id,
                        "sender_bloc": sender.bloc,
                        "sender_model": sender.model,
                        "receiver_ids": receiver_ids,
                        "message": message_text,
                        "reasoning": reasoning,
                    },
                )

        # Phase 3: snapshot only after every delivery, then settle every action.
        phase3_snapshot = self._capture_phase_snapshot()
        phase3_results = self._execute_phase(
            self._build_phase_requests(step, "phase3", phase3_snapshot)
        )
        phase3_by_agent = {result.agent_id: result for result in phase3_results}
        phase3_actions: Dict[int, Tuple[str, str]] = {}
        for agent in ordered_agents:
            result = phase3_by_agent[agent.agent_id]
            self.run_lifecycle.set_context(step, "phase3", agent.agent_id)
            if result.parsed is None:
                self._log_jsonl(
                    "parse_errors.jsonl",
                    {
                        "step": step,
                        "agent_id": agent.agent_id,
                        "phase": 3,
                        "raw_output": result.raw_output,
                    },
                )
                action = "stay"
                direction = ""
                memory_text = ""
                reasoning = ""
            else:
                action = result.parsed.get("action", "stay")
                direction = result.parsed.get("direction", "")
                memory_text = result.parsed.get("memory", "")
                reasoning = result.parsed.get("reasoning", "")
            if memory_text:
                agent.add_memory(memory_text)
            self._log_jsonl(
                "memory_reasoning.jsonl",
                {
                    "step": step,
                    "agent_id": agent.agent_id,
                    "bloc": agent.bloc,
                    "model": agent.model,
                    "position": list(
                        phase3_snapshot["agents"][agent.agent_id]["position"]
                    ),
                    "action": action,
                    "direction": direction,
                    "memory": memory_text,
                    "reasoning": reasoning,
                },
            )
            self.run_lifecycle.observe_agent(agent.agent_id)
            phase3_actions[agent.agent_id] = (action, direction)

        # Phase 4: apply movement only after every Phase 3 commit.
        for agent_id in sorted(phase3_actions):
            agent = agents_by_id[agent_id]
            self.run_lifecycle.set_context(step, "phase4", agent.agent_id)
            action, direction = phase3_actions[agent.agent_id]
            self._apply_movement(agent, action, direction)
            print(
                f"  Phase 4: Agent {agent.agent_id} ({agent.bloc}) -> "
                f"{action} {direction} @ {agent.position}"
            )

        self.run_lifecycle.set_context(step, "step_complete", None)

    def _apply_movement(self, agent: Agent, action: str, direction: str) -> None:
        if action != "move" or not direction:
            return
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
