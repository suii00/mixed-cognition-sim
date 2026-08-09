PHASE1_MESSAGE_PROMPT = """\
あなたは2Dグリッド世界にいるエージェント{agent_id}です。
グリッドの範囲は ({neg_s}, {neg_s}) から ({pos_s}, {pos_s}) までです。
現在の位置は ({x}, {y}) です。

既知の場所:
{places_info}

{occupancy_info}\
{memory_section}\
{messages_section}\

近くのエージェントに送るメッセージを決めてください。何も言うことがなければ空文字列でも構いません。

以下のJSON形式のみで回答してください:
{{"message": "<メッセージ内容>", "reasoning": "<あなたの内部推論>"}}\
"""

PHASE3_ACTION_PROMPT = """\
あなたは2Dグリッド世界にいるエージェント{agent_id}です。
グリッドの範囲は ({neg_s}, {neg_s}) から ({pos_s}, {pos_s}) までです。
現在の位置は ({x}, {y}) です。

既知の場所:
{places_info}

{occupancy_info}\
{memory_section}\
{messages_section}\

次の行動を決めてください。上下左右に1マス移動するか、その場に留まることができます。

以下のJSON形式のみで回答してください:
{{"action": "move" または "stay", "direction": "up" または "down" または "left" または "right", "memory": "<未来の自分へのメモ>", "reasoning": "<あなたの内部推論>"}}\
"""


def format_places_info(places) -> str:
    lines = []
    for p in places:
        lines.append(
            f"- {p.name}: 中心 ({p.center_x}, {p.center_y}), "
            f"範囲 ({p.x_min}, {p.y_min}) から ({p.x_max}, {p.y_max})"
        )
    return "\n".join(lines) if lines else "なし"


def format_occupancy_info(place, agent_count: int) -> str:
    if place is None:
        return ""
    return (
        f"あなたは{place.name}の中にいます。"
        f"現在の入場者数: {agent_count}/{place.capacity}\n"
    )


def format_memory_section(memories) -> str:
    if not memories:
        return ""
    lines = "\n".join(f"- {m}" for m in memories)
    return f"\n最近の記憶:\n{lines}\n"


def format_messages_section(messages) -> str:
    if not messages:
        return ""
    lines = "\n".join(
        f"- エージェント{m['sender_id']}: {m['message']}" for m in messages
    )
    return f"\n最近受信したメッセージ:\n{lines}\n"


def build_phase1_prompt(agent_id, x, y, half_space_size,
                        places, place, agent_count,
                        memories, messages) -> str:
    return PHASE1_MESSAGE_PROMPT.format(
        agent_id=agent_id,
        neg_s=-half_space_size,
        pos_s=half_space_size,
        x=x, y=y,
        places_info=format_places_info(places),
        occupancy_info=format_occupancy_info(place, agent_count),
        memory_section=format_memory_section(memories),
        messages_section=format_messages_section(messages),
    )


def build_phase3_prompt(agent_id, x, y, half_space_size,
                        places, place, agent_count,
                        memories, messages) -> str:
    return PHASE3_ACTION_PROMPT.format(
        agent_id=agent_id,
        neg_s=-half_space_size,
        pos_s=half_space_size,
        x=x, y=y,
        places_info=format_places_info(places),
        occupancy_info=format_occupancy_info(place, agent_count),
        memory_section=format_memory_section(memories),
        messages_section=format_messages_section(messages),
    )
