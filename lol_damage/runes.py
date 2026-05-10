"""Effects for keystone runes and notable damage runes.

This module models the damage-relevant runes. Effects are applied as either:

* a flat-stat contribution (handled by :func:`apply_rune_stats`), or
* a procced damage event added to a hit/combo (handled by
  :func:`keystone_proc_damage`).

Coverage is intentionally focused on the runes that materially affect damage
prediction. Unknown runes are ignored.
"""
from __future__ import annotations

from typing import Dict, List

from .damage import CombatStats, apply_damage
from .models import Build, Target


# Keystones that fire a discrete damage event when proc'd.
PROC_KEYSTONES = {
    "Electrocute",
    "Dark Harvest",
    "Phase Rush",  # not damage; ignored below
    "Hail of Blades",  # AS only
    "First Strike",
    "Press the Attack",  # exposes target rather than discrete proc; modeled as amp
    "Conqueror",  # stacking adaptive force; modeled as amp
    "Comet",  # Arcane Comet
    "Aery",  # Summon Aery
    "Glacial Augment",
    "Lethal Tempo",  # AS-only
    "Fleet Footwork",  # heal + slow; minor damage
    "Grasp of the Undying",
}


def apply_rune_stats(build: Build, base: CombatStats) -> CombatStats:
    """Add stats from rune shards and stat-granting runes."""
    stats = build.runes
    # Inline shards.
    for shard in stats.shards:
        base.bonus_ad += shard.ad
        base.ap += shard.ap
        base.attack_speed += shard.attack_speed
        base.ability_haste += shard.ability_haste
        base.bonus_hp += shard.hp
        base.armor += shard.armor
        base.magic_resist += shard.mr

    # A few static-stat runes (passive bonuses are approximations).
    rune_names = {r.name for r in stats.all_runes()}
    if "Gathering Storm" in rune_names:
        # Adaptive force ramping with time. Model a midgame value of ~24 AD/40 AP.
        base.bonus_ad += 12  # rough average; user can override via build flat bonuses
    if "Absolute Focus" in rune_names:
        # Up to 18-54 adaptive at full HP, lvl 1-18 (rough).
        base.bonus_ad += 8
    if "Sudden Impact" in rune_names:
        # Grants 9 lethality + 9 magic pen for 4s after dash/stealth.
        base.lethality += 9
        base.flat_magic_pen += 9
    if "Eyeball Collection" in rune_names:
        # Up to 30 adaptive at 10 stacks.
        base.bonus_ad += 6
    if "Ravenous Hunter" in rune_names or "Ultimate Hunter" in rune_names:
        pass  # cooldown / omnivamp; not direct damage
    return base


def keystone_proc_damage(
    keystone_name: str,
    attacker: CombatStats,
    target: Target,
    spell_count_in_window: int = 3,
) -> float:
    """Compute the damage of a single keystone proc against the target.

    Returns 0 if the keystone is not a damage keystone.
    """
    if not keystone_name:
        return 0.0
    name = keystone_name.strip()
    lvl = attacker.level

    if name == "Electrocute":
        # 30-180 (+0.4 bonus AD)(+0.25 AP) adaptive. Use bonus AD only.
        base = 30 + (180 - 30) * (lvl - 1) / 17.0
        raw = base + 0.4 * attacker.bonus_ad + 0.25 * attacker.ap
        # Adaptive: physical if more bonus AD, else magic.
        dt = "physical" if attacker.bonus_ad >= attacker.ap * 0.6 else "magic"
        return apply_damage(raw, dt, attacker, target.armor, target.magic_resist, target.damage_reduction)

    if name == "Dark Harvest":
        # 20 + soul stacks (here unknown, set 0) + 0.25 bonus AD + 0.15 AP, fires on <50% HP.
        base = 20
        raw = base + 0.25 * attacker.bonus_ad + 0.15 * attacker.ap
        # 1 + 9% per stack: assume 0 stacks here, caller can scale via amp.
        dt = "physical" if attacker.bonus_ad >= attacker.ap * 0.6 else "magic"
        if (target.current_hp or target.max_hp) >= 0.5 * target.max_hp:
            return 0.0
        return apply_damage(raw, dt, attacker, target.armor, target.magic_resist, target.damage_reduction)

    if name == "First Strike":
        # 7% extra true damage on hits during 3s after first damage proc.
        # We don't compute the proc itself here — it's modeled as `true_amp`.
        return 0.0

    if name == "Comet" or name == "Arcane Comet":
        # 30-100 (+0.2 bonus AD)(+0.35 AP) magic damage.
        base = 30 + (100 - 30) * (lvl - 1) / 17.0
        raw = base + 0.2 * attacker.bonus_ad + 0.35 * attacker.ap
        return apply_damage(raw, "magic", attacker, target.armor, target.magic_resist, target.damage_reduction)

    if name == "Aery" or name == "Summon Aery":
        # 10-40 (+0.1 bonus AD)(+0.2 AP) adaptive on damaging attack/ability.
        base = 10 + (40 - 10) * (lvl - 1) / 17.0
        raw = base + 0.1 * attacker.bonus_ad + 0.2 * attacker.ap
        dt = "physical" if attacker.bonus_ad >= attacker.ap * 0.6 else "magic"
        return apply_damage(raw, dt, attacker, target.armor, target.magic_resist, target.damage_reduction)

    if name == "Glacial Augment":
        # No direct damage; slow effect.
        return 0.0

    if name == "Grasp of the Undying":
        # Melee: 4% max HP (1.6% ranged) magic damage on proc'd auto.
        max_hp = target.max_hp
        raw = 0.04 * max_hp  # melee assumed
        return apply_damage(raw, "magic", attacker, target.armor, target.magic_resist, target.damage_reduction)

    return 0.0


def keystone_amp(keystone_name: str, stacks: int = 0) -> Dict[str, float]:
    """Return amp multipliers contributed by a keystone (for combos).

    Returned dict keys: 'physical_amp', 'magic_amp', 'true_amp', 'versus_amp'.
    """
    if not keystone_name:
        return {}
    name = keystone_name.strip()

    if name == "Conqueror":
        # Up to 12 stacks adaptive force at melee, 8% true conversion at full stacks.
        # Modeled as a small physical+magic amp; true conversion ignored here.
        n = max(0, min(stacks, 12))
        return {"physical_amp": 1.0 + 0.0 * n, "magic_amp": 1.0 + 0.0 * n}
        # Note: the headline benefit is the AD/AP itself; we already apply it via shards.

    if name == "Press the Attack":
        # 3 stacks -> bonus damage + 8% damage taken amp on target for 6s.
        # Approximate as +8% versus amp once procced.
        if stacks >= 3:
            return {"versus_amp": 1.08}
        return {}

    if name == "First Strike":
        return {"true_amp": 1.07}  # 7% extra (treated as true for simplicity)

    if name == "Coup de Grace":
        return {"versus_amp": 1.08}  # vs <40% HP

    if name == "Cut Down":
        return {"versus_amp": 1.05}  # vs higher-HP targets

    if name == "Last Stand":
        return {"physical_amp": 1.07, "magic_amp": 1.07}  # at low HP

    if name == "Giant Slayer":
        return {"versus_amp": 1.08}

    return {}
