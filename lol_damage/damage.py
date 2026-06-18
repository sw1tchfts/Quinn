"""Core damage math: armor/MR mitigation, penetration, scaling, crit."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass
class CombatStats:
    """A champion's effective combat stats after items + runes + level."""

    level: int = 1
    base_ad: float = 0.0
    bonus_ad: float = 0.0
    ap: float = 0.0
    attack_speed: float = 0.65
    crit_chance: float = 0.0
    crit_damage: float = 1.75  # multiplier on crit (175% by default)
    lethality: float = 0.0
    armor_pen_percent: float = 0.0  # 0.30 = 30% reduced armor
    flat_magic_pen: float = 0.0
    magic_pen_percent: float = 0.0
    bonus_hp: float = 0.0
    max_hp: float = 0.0
    armor: float = 0.0
    magic_resist: float = 0.0
    ability_haste: float = 0.0
    # Damage amplification multipliers (e.g. Conqueror, Dark Harvest stack effects).
    physical_amp: float = 1.0
    magic_amp: float = 1.0
    true_amp: float = 1.0
    # Optional per-target modifier (e.g. Demolish, Cut Down).
    versus_amp: float = 1.0

    @property
    def total_ad(self) -> float:
        return self.base_ad + self.bonus_ad


def lethality_to_flat_pen(lethality: float, level: int) -> float:
    """Convert lethality to flat armor penetration based on level.

    flat_pen = lethality * (0.6 + 0.4 * level / 18)
    """
    return lethality * (0.6 + 0.4 * level / 18.0)


def effective_armor(armor: float, flat_pen: float, percent_pen: float) -> float:
    """Apply % pen first, then flat pen. Armor cannot go below 0 from pen."""
    a = armor * (1.0 - percent_pen)
    a -= flat_pen
    if armor >= 0:
        return max(0.0, a)
    # Negative armor stays negative; pen never makes negative armor more negative.
    return min(0.0, a)


def effective_mr(mr: float, flat_pen: float, percent_pen: float) -> float:
    return effective_armor(mr, flat_pen, percent_pen)


def resist_multiplier(effective_resist: float) -> float:
    """Damage multiplier based on effective resist after penetration.

    Standard League formula:
      if R >= 0: mult = 100 / (100 + R)
      else:      mult = 2 - 100 / (100 - R)
    """
    if effective_resist >= 0:
        return 100.0 / (100.0 + effective_resist)
    return 2.0 - 100.0 / (100.0 - effective_resist)


def physical_damage_dealt(
    raw: float,
    attacker: CombatStats,
    target_armor: float,
) -> float:
    flat_pen = lethality_to_flat_pen(attacker.lethality, attacker.level)
    eff = effective_armor(target_armor, flat_pen, attacker.armor_pen_percent)
    return raw * resist_multiplier(eff) * attacker.physical_amp * attacker.versus_amp


def magic_damage_dealt(
    raw: float,
    attacker: CombatStats,
    target_mr: float,
) -> float:
    eff = effective_mr(target_mr, attacker.flat_magic_pen, attacker.magic_pen_percent)
    return raw * resist_multiplier(eff) * attacker.magic_amp * attacker.versus_amp


def true_damage_dealt(raw: float, attacker: CombatStats) -> float:
    return raw * attacker.true_amp * attacker.versus_amp


def apply_damage(
    raw: float,
    damage_type: str,
    attacker: CombatStats,
    target_armor: float,
    target_mr: float,
    target_dr: float = 1.0,
) -> float:
    """Mitigate raw damage given a type and target resists.

    target_dr is a flat multiplier (e.g. 0.7 = takes 70% of damage) applied at the end.
    """
    dt = damage_type.lower()
    if dt == "physical":
        v = physical_damage_dealt(raw, attacker, target_armor)
    elif dt == "magic":
        v = magic_damage_dealt(raw, attacker, target_mr)
    elif dt == "true":
        v = true_damage_dealt(raw, attacker)
    else:
        raise ValueError(f"Unknown damage type: {damage_type}")
    return v * target_dr


def expected_auto_damage(
    attacker: CombatStats,
    target_armor: float,
    target_dr: float = 1.0,
    bonus_on_hit_physical: float = 0.0,
    bonus_on_hit_magic: float = 0.0,
    bonus_on_hit_true: float = 0.0,
    target_mr: float = 0.0,
) -> float:
    """Expected damage of a single auto-attack averaged over crit chance."""
    base = attacker.total_ad
    crit_mult = 1.0 + attacker.crit_chance * (attacker.crit_damage - 1.0)
    physical = base * crit_mult + bonus_on_hit_physical
    out = physical_damage_dealt(physical, attacker, target_armor) * target_dr
    if bonus_on_hit_magic:
        out += magic_damage_dealt(bonus_on_hit_magic, attacker, target_mr) * target_dr
    if bonus_on_hit_true:
        out += true_damage_dealt(bonus_on_hit_true, attacker) * target_dr
    return out


def crit_auto_damage(
    attacker: CombatStats,
    target_armor: float,
    target_dr: float = 1.0,
) -> float:
    return physical_damage_dealt(attacker.total_ad * attacker.crit_damage, attacker, target_armor) * target_dr


def non_crit_auto_damage(
    attacker: CombatStats,
    target_armor: float,
    target_dr: float = 1.0,
) -> float:
    return physical_damage_dealt(attacker.total_ad, attacker, target_armor) * target_dr
