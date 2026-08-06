import argparse
from engine.config import load_config
from engine.sim import Simulation


def main():
    parser = argparse.ArgumentParser(
        description="Mixed-cognition agent simulation"
    )
    parser.add_argument("--config", required=True, help="Path to YAML config")
    args = parser.parse_args()

    config = load_config(args.config)
    sim = Simulation(config)
    sim.run()


if __name__ == "__main__":
    main()
