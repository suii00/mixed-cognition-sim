"""Threaded, phase-preserving execution for blocking LLM transports."""

from __future__ import annotations

import copy
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Iterable, Optional, Tuple

from engine.llm_client import LLMTransportError, TelemetryCallback


THREAD_NAME_PREFIX = "gate2-llm"
PHASE_ORDER = {"phase1": 1, "phase3": 3}


@dataclass(frozen=True)
class LLMRequest:
    """One transport request containing no mutable simulation object."""

    request_id: str
    step: int
    phase: str
    agent_id: int
    model: str
    base_url: str
    prompt: str
    temperature: float
    max_tokens: int
    timeout_s: int
    llm_overrides: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.phase not in PHASE_ORDER:
            raise ValueError(f"unsupported LLM request phase: {self.phase!r}")
        object.__setattr__(self, "llm_overrides", copy.deepcopy(self.llm_overrides))


@dataclass(frozen=True)
class WorkerTelemetry:
    http_attempts: int = 0
    generation_retries: int = 0
    transport_failures: int = 0
    syntax_parse_attempt_failures: int = 0


class LocalTelemetry:
    """A worker-owned telemetry collector with no shared-state callbacks."""

    _EVENT_FIELDS = {
        "http_attempt": "http_attempts",
        "generation_retry": "generation_retries",
        "transport_failure": "transport_failures",
        "syntax_parse_attempt_failure": "syntax_parse_attempt_failures",
    }

    def __init__(self) -> None:
        self._counts = {field_name: 0 for field_name in self._EVENT_FIELDS.values()}

    def record(self, event: str, amount: int = 1) -> None:
        field_name = self._EVENT_FIELDS.get(event)
        if field_name is None:
            raise ValueError(f"unknown worker telemetry event: {event}")
        if not isinstance(amount, int) or isinstance(amount, bool) or amount < 0:
            raise ValueError("worker telemetry amount must be a non-negative integer")
        self._counts[field_name] += amount

    def snapshot(self) -> WorkerTelemetry:
        return WorkerTelemetry(**self._counts)


@dataclass(frozen=True)
class LLMResult:
    request_id: str
    step: int
    phase: str
    agent_id: int
    parsed: Optional[Dict[str, Any]]
    raw_output: str
    telemetry: WorkerTelemetry
    error_kind: Optional[str] = None
    error: Optional[BaseException] = None


TransportInvocation = Callable[
    [LLMRequest, TelemetryCallback],
    Tuple[Optional[Dict[str, Any]], str],
]


def request_sort_key(request: LLMRequest) -> tuple[int, int, int, str]:
    return (
        request.step,
        PHASE_ORDER[request.phase],
        request.agent_id,
        request.request_id,
    )


def _execute_one(
    request: LLMRequest,
    invoke_transport: TransportInvocation,
) -> LLMResult:
    telemetry = LocalTelemetry()
    try:
        parsed, raw_output = invoke_transport(request, telemetry.record)
    except LLMTransportError as error:
        return LLMResult(
            request_id=request.request_id,
            step=request.step,
            phase=request.phase,
            agent_id=request.agent_id,
            parsed=None,
            raw_output="",
            telemetry=telemetry.snapshot(),
            error_kind="transport",
            error=error,
        )
    except BaseException as error:
        return LLMResult(
            request_id=request.request_id,
            step=request.step,
            phase=request.phase,
            agent_id=request.agent_id,
            parsed=None,
            raw_output="",
            telemetry=telemetry.snapshot(),
            error_kind="unexpected",
            error=error,
        )
    return LLMResult(
        request_id=request.request_id,
        step=request.step,
        phase=request.phase,
        agent_id=request.agent_id,
        parsed=copy.deepcopy(parsed),
        raw_output=raw_output,
        telemetry=telemetry.snapshot(),
    )


def execute_llm_batch(
    requests: Iterable[LLMRequest],
    max_concurrency: int,
    invoke_transport: TransportInvocation,
) -> list[LLMResult]:
    """Settle every request and return results in canonical request order."""
    if (
        not isinstance(max_concurrency, int)
        or isinstance(max_concurrency, bool)
        or max_concurrency <= 0
    ):
        raise ValueError("max_concurrency must be a positive integer")

    ordered = sorted(list(requests), key=request_sort_key)
    request_ids = [request.request_id for request in ordered]
    agent_ids = [request.agent_id for request in ordered]
    if len(set(request_ids)) != len(request_ids):
        raise ValueError("duplicate LLM request_id in phase batch")
    if len(set(agent_ids)) != len(agent_ids):
        raise ValueError("duplicate agent_id in phase batch")
    if not ordered:
        return []

    worker_count = min(max_concurrency, len(ordered))
    with ThreadPoolExecutor(
        max_workers=worker_count,
        thread_name_prefix=THREAD_NAME_PREFIX,
    ) as executor:
        future_by_request_id = {
            request.request_id: executor.submit(
                _execute_one,
                request,
                invoke_transport,
            )
            for request in ordered
        }
        results = [
            future_by_request_id[request.request_id].result()
            for request in ordered
        ]
    return results
