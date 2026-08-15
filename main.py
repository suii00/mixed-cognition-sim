import argparse
import sys
from typing import Optional, Sequence

import yaml

from engine.config import load_config
from engine.provenance import InvalidRunIdError, RunCollisionError
from engine.sim import Simulation, SimulationAbortedError


def _nonzero_system_exit_code(error: SystemExit) -> int:
    code = error.code
    return code if isinstance(code, int) and code != 0 else 1


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="Mixed-cognition agent simulation"
    )
    parser.add_argument("--config", required=True, help="Path to YAML config")
    args = parser.parse_args(argv)

    try:
        config = load_config(args.config)
    except (OSError, TypeError, ValueError, yaml.YAMLError) as error:
        print(f"[ERROR] Invalid configuration: {error}", file=sys.stderr)
        return 2

    try:
        sim = Simulation(config)
    except (InvalidRunIdError, RunCollisionError) as error:
        print(f"[ERROR] Run cannot start: {error}", file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        print("[ABORT] Interrupted while starting the run", file=sys.stderr)
        return 130
    except SystemExit as error:
        print("[ERROR] Internal SystemExit while starting the run", file=sys.stderr)
        return _nonzero_system_exit_code(error)

    try:
        sim.run()
    except SimulationAbortedError as error:
        print(f"[ABORT] {error}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("[ABORT] Interrupted by user", file=sys.stderr)
        return 130
    except SystemExit as error:
        print("[ERROR] Internal SystemExit during the run", file=sys.stderr)
        return _nonzero_system_exit_code(error)

    terminal_meta = sim.run_lifecycle.meta
    if (
        terminal_meta.get("status") != "completed"
        or terminal_meta.get("aborted") is not False
    ):
        print("[ERROR] Run returned without completed metadata", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
