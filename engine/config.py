import yaml
from typing import Dict, Any

from engine.provenance import (
    normalize_run_id,
    validate_base_url,
    validate_provider,
)


def load_config(path: str) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)

    required_top = ["simulation", "blocs", "agents", "places", "llm_defaults"]
    for key in required_top:
        if key not in cfg:
            raise ValueError(f"Missing required config section: {key}")

    sim = cfg["simulation"]
    for key in ["duration", "half_space_size", "seed", "run_name"]:
        if key not in sim:
            raise ValueError(f"Missing simulation.{key}")

    if not isinstance(sim["run_name"], str) or not sim["run_name"]:
        raise ValueError("simulation.run_name must be a non-empty string")
    if (
        not isinstance(sim["duration"], int)
        or isinstance(sim["duration"], bool)
        or sim["duration"] <= 0
    ):
        raise ValueError("simulation.duration must be a positive integer")
    if "run_id" in sim:
        normalize_run_id(sim["run_id"])
    for version_key in ["protocol_version", "metric_version"]:
        if version_key in sim and (
            not isinstance(sim[version_key], str) or not sim[version_key]
        ):
            raise ValueError(f"simulation.{version_key} must be a non-empty string")
    thresholds = sim.get("failure_thresholds", {})
    if not isinstance(thresholds, dict):
        raise ValueError("simulation.failure_thresholds must be a mapping")
    threshold_keys = {
        "transport_failures",
        "syntax_parse_failures",
        "schema_validation_failures",
    }
    unknown_thresholds = set(thresholds) - threshold_keys
    if unknown_thresholds:
        raise ValueError(
            "Unknown simulation.failure_thresholds keys: "
            + ", ".join(sorted(str(key) for key in unknown_thresholds))
        )
    for key in threshold_keys:
        if key in thresholds and (
            not isinstance(thresholds[key], int)
            or isinstance(thresholds[key], bool)
            or thresholds[key] < 0
        ):
            raise ValueError(
                f"simulation.failure_thresholds.{key} must be a non-negative integer"
            )

    if not isinstance(cfg["blocs"], list) or not cfg["blocs"]:
        raise ValueError("blocs must contain at least one bloc")
    for i, bloc in enumerate(cfg["blocs"]):
        if not isinstance(bloc, dict):
            raise ValueError(f"blocs[{i}] must be a mapping")
        for key in ["name", "model", "base_url", "num_agents"]:
            if key not in bloc:
                raise ValueError(f"blocs[{i}] missing '{key}'")
        for key in ["name", "model", "base_url"]:
            if not isinstance(bloc[key], str) or not bloc[key]:
                raise ValueError(f"blocs[{i}].{key} must be a non-empty string")
        validate_provider(bloc.get("provider", "ollama"))
        for key in ["model_digest", "quantization", "chat_template"]:
            if key in bloc and (
                not isinstance(bloc[key], str) or not bloc[key]
            ):
                raise ValueError(
                    f"blocs[{i}].{key} must be a non-empty string"
                )
        if (
            not isinstance(bloc["num_agents"], int)
            or isinstance(bloc["num_agents"], bool)
            or bloc["num_agents"] <= 0
        ):
            raise ValueError(f"blocs[{i}].num_agents must be a positive integer")
        validate_base_url(bloc["base_url"])

    agents = cfg["agents"]
    for key in ["communication_radius", "memory_limit", "memory_size",
                "message_history_limit", "message_context_size"]:
        if key not in agents:
            raise ValueError(f"agents.{key} missing")

    for i, place in enumerate(cfg["places"]):
        for key in ["name", "center_x", "center_y", "half_size", "capacity"]:
            if key not in place:
                raise ValueError(f"places[{i}] missing '{key}'")

    return cfg
