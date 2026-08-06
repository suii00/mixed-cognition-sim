import math
import random
from typing import List, Dict, Optional, Tuple


class Place:
    def __init__(self, name: str, center_x: int, center_y: int,
                 half_size: int, capacity: int):
        self.name = name
        self.center_x = center_x
        self.center_y = center_y
        self.half_size = half_size
        self.capacity = capacity

    @property
    def x_min(self) -> int:
        return self.center_x - self.half_size

    @property
    def x_max(self) -> int:
        return self.center_x + self.half_size

    @property
    def y_min(self) -> int:
        return self.center_y - self.half_size

    @property
    def y_max(self) -> int:
        return self.center_y + self.half_size

    def contains(self, x: int, y: int) -> bool:
        return self.x_min <= x <= self.x_max and self.y_min <= y <= self.y_max


class World:
    def __init__(self, half_space_size: int, places_config: List[Dict]):
        self.half_space_size = half_space_size
        self.places: List[Place] = []
        for p in places_config:
            self.places.append(Place(
                name=p["name"],
                center_x=p["center_x"],
                center_y=p["center_y"],
                half_size=p["half_size"],
                capacity=p["capacity"],
            ))

    def clamp(self, x: int, y: int) -> Tuple[int, int]:
        s = self.half_space_size
        return max(-s, min(s, x)), max(-s, min(s, y))

    def get_place_for(self, x: int, y: int) -> Optional[Place]:
        for place in self.places:
            if place.contains(x, y):
                return place
        return None

    def euclidean_distance(self, x1: int, y1: int, x2: int, y2: int) -> float:
        return math.sqrt((x1 - x2) ** 2 + (y1 - y2) ** 2)

    def generate_initial_positions(self, num_agents: int, rng: random.Random) -> List[Tuple[int, int]]:
        s = self.half_space_size
        all_coords = []
        for x in range(-s, s + 1):
            for y in range(-s, s + 1):
                if self.get_place_for(x, y) is None:
                    all_coords.append((x, y))
        rng.shuffle(all_coords)
        if len(all_coords) < num_agents:
            raise ValueError(
                f"Not enough outside-place cells ({len(all_coords)}) "
                f"for {num_agents} agents"
            )
        return all_coords[:num_agents]

    def count_agents_in_place(self, place: Place,
                              positions: Dict[int, Tuple[int, int]]) -> int:
        count = 0
        for pos in positions.values():
            if place.contains(pos[0], pos[1]):
                count += 1
        return count
