#!/usr/bin/env python3
"""Run a deterministic headless mock simulation for a CompiledAssetCandidate.

This is deliberately coarse. It is a guardrail for AI output, not a replacement
for the Phaser battle runtime.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


SIMULATION_VERSION = "mock_sim_v0.1"
DEFAULT_DURATION_SECONDS = 30.0

ENEMY_SAMPLES = [
    {"key": "normal", "hp": 100.0, "speed": 1.0, "count": 4},
    {"key": "fast", "hp": 70.0, "speed": 1.6, "count": 4},
    {"key": "armored", "hp": 220.0, "speed": 0.7, "count": 2}
]


def load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(data, handle, ensure_ascii=False, indent=2)
        handle.write("\n")


def effects(candidate: dict[str, Any]) -> list[dict[str, Any]]:
    gameplay = candidate.get("gameplay", {})
    effect_blocks = gameplay.get("effect_blocks", [])
    if not isinstance(effect_blocks, list):
        return []
    return [effect for effect in effect_blocks if isinstance(effect, dict)]


def base_stats(candidate: dict[str, Any]) -> dict[str, Any]:
    gameplay = candidate.get("gameplay", {})
    stats = gameplay.get("base_stats", {})
    return stats if isinstance(stats, dict) else {}


def estimate_dps(candidate: dict[str, Any]) -> float:
    stats = base_stats(candidate)
    cooldown = float(stats.get("cooldown") or 1.0)
    cooldown = max(cooldown, 0.1)
    dps = 0.0
    for effect in effects(candidate):
        effect_type = effect.get("type")
        if effect_type == "damage":
            dps += float(effect.get("amount", 0)) / cooldown
        elif effect_type == "area_damage":
            # Assume a conservative average of 2.2 enemies caught in the area.
            dps += float(effect.get("amount", 0)) * 2.2 / cooldown
        elif effect_type == "damage_over_time":
            dps += float(effect.get("damage_per_second", 0))
        elif effect_type == "charge_burst":
            multiplier = float(effect.get("burst_multiplier", 1.0))
            charge = max(float(effect.get("charge_seconds", 1.0)), 1.0)
            dps += 18.0 * multiplier / charge
    return round(dps, 2)


def estimate_slow_uptime(candidate: dict[str, Any]) -> tuple[float, float]:
    stats = base_stats(candidate)
    cooldown = max(float(stats.get("cooldown") or 1.0), 0.1)
    uptime = 0.0
    max_ratio = 0.0
    has_aura = any(effect.get("type") == "aura_buff" for effect in effects(candidate))
    for effect in effects(candidate):
        if effect.get("type") != "slow":
            continue
        ratio = float(effect.get("slow_ratio", 0))
        duration = float(effect.get("duration", 0))
        max_ratio = max(max_ratio, ratio)
        if has_aura:
            uptime = max(uptime, 0.95)
        else:
            uptime = max(uptime, min(1.0, duration / cooldown))
    return round(min(uptime, 1.0), 2), round(max_ratio, 2)


def estimate_power_peak(candidate: dict[str, Any]) -> float:
    total = 0.0
    for effect in effects(candidate):
        if effect.get("type") == "power_cost":
            total += float(effect.get("power_per_second", 0))
    return round(total, 2)


def estimate_leaks(candidate: dict[str, Any], dps: float, slow_uptime: float, slow_ratio: float, duration: float) -> int:
    total_leaks = 0
    control_multiplier = 1.0 + slow_uptime * slow_ratio * 1.8
    total_output = dps * duration * control_multiplier
    total_enemies = sum(int(enemy["count"]) for enemy in ENEMY_SAMPLES)
    if dps <= 0 and slow_uptime > 0:
        # Pure control towers are judged as enabling allies, not killing alone.
        return max(0, total_enemies - 3)
    if dps <= 0:
        return total_enemies

    for enemy in ENEMY_SAMPLES:
        effective_hp = float(enemy["hp"]) * int(enemy["count"])
        enemy_pressure = effective_hp * float(enemy["speed"])
        killed_ratio = min(1.0, total_output / max(enemy_pressure, 1.0))
        total_leaks += int(round(int(enemy["count"]) * (1.0 - killed_ratio)))
    return max(total_leaks, 0)


def estimate_cost_efficiency(candidate: dict[str, Any], dps: float, slow_uptime: float, slow_ratio: float, power_peak: float) -> float:
    stats = base_stats(candidate)
    build_cost = max(float(stats.get("build_cost") or 100.0), 1.0)
    utility = dps + (slow_uptime * slow_ratio * 140.0)
    penalty = 1.0 + power_peak * 0.08
    return round((utility / build_cost) / penalty, 3)


def balance_flags(candidate: dict[str, Any], dps: float, slow_uptime: float, slow_ratio: float, power_peak: float, cost_efficiency: float) -> list[str]:
    flags: list[str] = []
    stats = base_stats(candidate)
    build_cost = float(stats.get("build_cost") or 0)
    effect_count = len(effects(candidate))

    if dps == 0 and slow_uptime == 0:
        flags.append("no_direct_impact")
    if dps == 0 and slow_uptime > 0:
        flags.append("pure_control_requires_damage_partner")
    if slow_uptime > 0.85 and slow_ratio > 0.45:
        flags.append("control_may_be_too_strong")
    if slow_uptime > 0.85 and power_peak < 2:
        flags.append("control_has_weak_cost")
    if power_peak > 10:
        flags.append("high_power_demand")
    if build_cost < 120 and effect_count >= 3:
        flags.append("possibly_underpriced")
    if cost_efficiency < 0.05:
        flags.append("low_cost_efficiency")
    if cost_efficiency > 0.6:
        flags.append("high_cost_efficiency")

    return flags


def simulate(candidate: dict[str, Any], duration: float) -> dict[str, Any]:
    candidate_id = str(candidate.get("id", "unknown_candidate"))
    dps = estimate_dps(candidate)
    slow_uptime, slow_ratio = estimate_slow_uptime(candidate)
    power_peak = estimate_power_peak(candidate)
    leaked = estimate_leaks(candidate, dps, slow_uptime, slow_ratio, duration)
    cost_efficiency = estimate_cost_efficiency(candidate, dps, slow_uptime, slow_ratio, power_peak)
    flags = balance_flags(candidate, dps, slow_uptime, slow_ratio, power_peak, cost_efficiency)

    notes = [
        "mock simulation is deterministic and intentionally coarse",
        "Phaser runtime combat remains the source of truth for final battle behavior"
    ]
    return {
        "id": f"sim_{candidate_id}_{SIMULATION_VERSION}",
        "candidate_id": candidate_id,
        "simulation_version": SIMULATION_VERSION,
        "duration_seconds": duration,
        "estimated_dps": dps,
        "slow_uptime": slow_uptime,
        "enemies_leaked": leaked,
        "power_peak": power_peak,
        "cost_efficiency": cost_efficiency,
        "balance_flags": flags,
        "notes": notes
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("candidate", help="Path to a CompiledAssetCandidate JSON file.")
    parser.add_argument("--duration", type=float, default=DEFAULT_DURATION_SECONDS)
    parser.add_argument("--output", help="Write the simulation report to this path. Defaults to stdout.")
    args = parser.parse_args()

    candidate = load_json(Path(args.candidate))
    if not isinstance(candidate, dict):
        print("CompiledAssetCandidate root must be an object")
        return 1

    report = simulate(candidate, args.duration)
    if args.output:
        output_path = Path(args.output)
        write_json(output_path, report)
        print(f"Wrote {output_path}")
    else:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

