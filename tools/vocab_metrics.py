"""Vocabulary propagation metrics for mixed-cognition simulation."""
import argparse
import csv
import json
import math
import os
import re
from collections import defaultdict
from typing import Dict, List, Set, Tuple

STOP_WORDS = {
    "a", "an", "the", "is", "are", "was", "were", "be", "been", "being",
    "have", "has", "had", "do", "does", "did", "will", "would", "could",
    "should", "may", "might", "shall", "can", "need", "must",
    "i", "me", "my", "we", "our", "you", "your", "he", "she", "it",
    "they", "them", "their", "his", "her", "its",
    "this", "that", "these", "those",
    "in", "on", "at", "to", "for", "of", "with", "by", "from", "up",
    "about", "into", "through", "during", "before", "after",
    "and", "but", "or", "nor", "not", "so", "if", "then", "than",
    "no", "yes", "all", "each", "every", "both", "few", "more", "most",
    "other", "some", "such", "only", "own", "same", "too", "very",
    "just", "because", "as", "until", "while", "here", "there", "when",
    "where", "why", "how", "what", "which", "who", "whom",
    "also", "am", "an", "any", "out", "over", "under",
    "again", "further", "once", "between", "down",
    "agent", "move", "stay", "left", "right", "up", "down",
    "position", "message", "direction", "memory", "reasoning",
    "action", "current", "grid", "world", "location",
}


def tokenize(text: str) -> List[str]:
    text = text.lower()
    text = re.sub(r"[^a-z\s]", "", text)
    tokens = text.split()
    return [t for t in tokens if t not in STOP_WORDS and len(t) > 2]


def load_run_data(run_dir: str) -> Tuple[Dict[int, str], List[Dict], List[Dict]]:
    agent_bloc_map: Dict[int, str] = {}
    messages_data: List[Dict] = []
    memory_data: List[Dict] = []

    memory_path = os.path.join(run_dir, "memory_reasoning.jsonl")
    if os.path.exists(memory_path):
        with open(memory_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                record = json.loads(line)
                memory_data.append(record)
                agent_bloc_map[record["agent_id"]] = record["bloc"]

    messages_path = os.path.join(run_dir, "messages.jsonl")
    if os.path.exists(messages_path):
        with open(messages_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                record = json.loads(line)
                messages_data.append(record)
                agent_bloc_map[record["sender_id"]] = record["sender_bloc"]

    return agent_bloc_map, messages_data, memory_data


def compute_bloc_frequencies(
    agent_bloc_map: Dict[int, str],
    messages_data: List[Dict],
    memory_data: List[Dict],
) -> Dict[str, Dict[str, int]]:
    bloc_freq: Dict[str, Dict[str, int]] = defaultdict(lambda: defaultdict(int))

    for record in messages_data:
        bloc = record["sender_bloc"]
        tokens = tokenize(record.get("message", ""))
        for t in tokens:
            bloc_freq[bloc][t] += 1

    for record in memory_data:
        bloc = record["bloc"]
        tokens = tokenize(record.get("memory", ""))
        for t in tokens:
            bloc_freq[bloc][t] += 1

    return dict(bloc_freq)


def compute_distinctive_words(
    bloc_freq: Dict[str, Dict[str, int]], k: int = 20, alpha: float = 0.01
) -> Dict[str, List[Tuple[str, float]]]:
    all_blocs = list(bloc_freq.keys())
    if len(all_blocs) < 2:
        return {b: [] for b in all_blocs}

    total_per_bloc: Dict[str, int] = {}
    for bloc in all_blocs:
        total_per_bloc[bloc] = sum(bloc_freq[bloc].values())

    all_words: Set[str] = set()
    for freq in bloc_freq.values():
        all_words.update(freq.keys())

    distinctive: Dict[str, List[Tuple[str, float]]] = {}
    for target_bloc in all_blocs:
        other_freq: Dict[str, int] = defaultdict(int)
        other_total = 0
        for bloc in all_blocs:
            if bloc == target_bloc:
                continue
            for word, count in bloc_freq[bloc].items():
                other_freq[word] += count
            other_total += total_per_bloc[bloc]

        target_total = total_per_bloc[target_bloc]
        scores = []
        for word in all_words:
            f_target = bloc_freq[target_bloc].get(word, 0)
            f_other = other_freq.get(word, 0)
            p_target = (f_target + alpha) / (target_total + alpha * len(all_words))
            p_other = (f_other + alpha) / (other_total + alpha * len(all_words))
            log_odds = math.log(p_target / p_other)
            scores.append((word, log_odds))

        scores.sort(key=lambda x: x[1], reverse=True)
        distinctive[target_bloc] = scores[:k]

    return distinctive


def compute_crossover_events(
    distinctive: Dict[str, List[Tuple[str, float]]],
    agent_bloc_map: Dict[int, str],
    messages_data: List[Dict],
    memory_data: List[Dict],
) -> List[Dict]:
    distinctive_sets: Dict[str, Set[str]] = {}
    for bloc, words in distinctive.items():
        distinctive_sets[bloc] = {w for w, _ in words}

    events: List[Dict] = []

    usage_by_agent_step: List[Tuple[int, int, str, Set[str]]] = []

    for record in messages_data:
        tokens = set(tokenize(record.get("message", "")))
        for rid in record.get("receiver_ids", []):
            if rid in agent_bloc_map:
                usage_by_agent_step.append(
                    (record["step"], rid, agent_bloc_map[rid], tokens)
                )
        usage_by_agent_step.append(
            (record["step"], record["sender_id"],
             record["sender_bloc"], tokens)
        )

    for record in memory_data:
        tokens = set(tokenize(record.get("memory", "")))
        tokens.update(tokenize(record.get("reasoning", "")))
        usage_by_agent_step.append(
            (record["step"], record["agent_id"], record["bloc"], tokens)
        )

    first_crossover: Dict[Tuple[str, str, str], int] = {}
    crossover_counts: Dict[Tuple[str, str, str], int] = defaultdict(int)

    for step, agent_id, agent_bloc, tokens in usage_by_agent_step:
        for source_bloc, source_words in distinctive_sets.items():
            if source_bloc == agent_bloc:
                continue
            for word in tokens & source_words:
                key = (source_bloc, word, agent_bloc)
                if key not in first_crossover:
                    first_crossover[key] = step
                crossover_counts[key] += 1

    for key, first_step in sorted(first_crossover.items(), key=lambda x: x[1]):
        source_bloc, word, target_bloc = key
        events.append({
            "source_bloc": source_bloc,
            "word": word,
            "target_bloc": target_bloc,
            "first_step": first_step,
            "total_uses": crossover_counts[key],
        })

    return events


def write_report(
    output_dir: str,
    distinctive: Dict[str, List[Tuple[str, float]]],
    events: List[Dict],
) -> None:
    report_path = os.path.join(output_dir, "vocab_report.md")
    with open(report_path, "w", encoding="utf-8") as f:
        f.write("# Vocabulary Propagation Report\n\n")

        for bloc, words in sorted(distinctive.items()):
            f.write(f"## Bloc: {bloc}\n\n")
            f.write("| Rank | Word | Log-Odds |\n")
            f.write("|------|------|----------|\n")
            for i, (word, score) in enumerate(words, 1):
                f.write(f"| {i} | {word} | {score:.3f} |\n")
            f.write("\n")

        f.write("## Crossover Events\n\n")
        if not events:
            f.write("No crossover events detected.\n")
        else:
            f.write("| Source Bloc | Word | Target Bloc | First Step | Total Uses |\n")
            f.write("|------------|------|-------------|------------|------------|\n")
            for e in events:
                f.write(
                    f"| {e['source_bloc']} | {e['word']} | {e['target_bloc']} "
                    f"| {e['first_step']} | {e['total_uses']} |\n"
                )
        f.write("\n")

    csv_path = os.path.join(output_dir, "vocab_events.csv")
    with open(csv_path, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(
            f, fieldnames=["source_bloc", "word", "target_bloc",
                           "first_step", "total_uses"]
        )
        writer.writeheader()
        writer.writerows(events)


def main():
    parser = argparse.ArgumentParser(
        description="Vocabulary propagation metrics"
    )
    parser.add_argument("run_dir", help="Path to simulation output directory")
    args = parser.parse_args()

    if not os.path.isdir(args.run_dir):
        print(f"Error: {args.run_dir} is not a directory")
        return

    agent_bloc_map, messages_data, memory_data = load_run_data(args.run_dir)
    if not agent_bloc_map:
        print("No data found in run directory")
        return

    bloc_freq = compute_bloc_frequencies(agent_bloc_map, messages_data, memory_data)
    distinctive = compute_distinctive_words(bloc_freq)
    events = compute_crossover_events(
        distinctive, agent_bloc_map, messages_data, memory_data
    )

    write_report(args.run_dir, distinctive, events)
    print(f"Report written to {args.run_dir}/vocab_report.md")
    print(f"Events CSV written to {args.run_dir}/vocab_events.csv")
    print(f"Distinctive words per bloc: {', '.join(f'{b}={len(w)}' for b, w in distinctive.items())}")
    print(f"Crossover events: {len(events)}")


if __name__ == "__main__":
    main()
