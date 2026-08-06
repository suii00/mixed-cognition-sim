import yaml
from typing import Dict, Any


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

    for i, bloc in enumerate(cfg["blocs"]):
        for key in ["name", "model", "base_url", "num_agents"]:
            if key not in bloc:
                raise ValueError(f"blocs[{i}] missing '{key}'")

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
