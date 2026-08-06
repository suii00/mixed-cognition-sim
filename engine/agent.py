from typing import List, Dict, Tuple, Optional
from collections import deque


class Agent:
    def __init__(self, agent_id: int, bloc: str, model: str,
                 base_url: str, position: Tuple[int, int],
                 memory_limit: int, memory_size: int,
                 message_history_limit: int, message_context_size: int,
                 llm_overrides: Optional[Dict] = None):
        self.agent_id = agent_id
        self.bloc = bloc
        self.model = model
        self.base_url = base_url
        self.position = position
        self.memory_limit = memory_limit
        self.memory_size = memory_size
        self.message_history_limit = message_history_limit
        self.message_context_size = message_context_size
        self.llm_overrides = llm_overrides or {}
        self.memories: List[str] = []
        self.received_messages: List[Dict] = []

    def add_memory(self, memory_text: str) -> None:
        self.memories.append(memory_text)
        if len(self.memories) > self.memory_limit:
            self.memories = self.memories[-self.memory_limit:]

    def get_recent_memories(self) -> List[str]:
        return self.memories[-self.memory_size:]

    def add_received_message(self, sender_id: int, message: str, step: int) -> None:
        self.received_messages.append({
            "sender_id": sender_id,
            "message": message,
            "step": step,
        })
        if len(self.received_messages) > self.message_history_limit:
            self.received_messages = self.received_messages[-self.message_history_limit:]

    def get_recent_messages(self) -> List[Dict]:
        return self.received_messages[-self.message_context_size:]
