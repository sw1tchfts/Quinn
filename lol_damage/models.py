"""Data models for champions, items, runes, builds, and targets."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional


def _stat_at_level(base: float, growth: float, level: int) -> float:
    """Riot's per-level scaling curve.

    stat(level) = base + growth * (level - 1) * (0.7025 + 0.0175 * (level - 1))
    """
    n = level - 1
    return base + growth * n * (0.7025 + 0.0175 * n)


@dataclass
class ChampionStats:
    """Per-level scaling stats pulled from Data Dragon."""

    hp: float = 0.0
    hp_per_level: float = 0.0
    mp: float = 0.0
    mp_per_level: float = 0.0
    armor: float = 0.0
    armor_per_level: float = 0.0
    spellblock: float = 0.0  # magic resist
    spellblock_per_level: float = 0.0
    attackdamage: float = 0.0
    attackdamage_per_level: float = 0.0
    attackspeed: float = 0.0
    attackspeed_per_level: float = 0.0  # percent
    attackspeed_ratio: float = 0.0
    crit: float = 0.0
    crit_per_level: float = 0.0
    movespeed: float = 0.0
    attackrange: float = 0.0

    def at_level(self, level: int) -> "ChampionStats":
        return ChampionStats(
            hp=_stat_at_level(self.hp, self.hp_per_level, level),
            armor=_stat_at_level(self.armor, self.armor_per_level, level),
            spellblock=_stat_at_level(self.spellblock, self.spellblock_per_level, level),
            attackdamage=_stat_at_level(self.attackdamage, self.attackdamage_per_level, level),
            mp=_stat_at_level(self.mp, self.mp_per_level, level),
            attackspeed=self.attackspeed
            * (1 + (self.attackspeed_per_level / 100) * (level - 1) * (0.7025 + 0.0175 * (level - 1))),
            attackspeed_ratio=self.attackspeed_ratio or self.attackspeed,
            crit=self.crit,
            movespeed=self.movespeed,
            attackrange=self.attackrange,
        )


@dataclass
class Spell:
    """A champion ability."""

    key: str  # 'Q', 'W', 'E', 'R', 'P' (passive), 'A' (auto)
    name: str
    description: str = ""
    max_rank: int = 5
    # Damage definitions per rank. Each entry is a dict like:
    # {"type": "physical"|"magic"|"true",
    #  "base": [r1, r2, r3, r4, r5],
    #  "ad_ratio": 0.0, "bonus_ad_ratio": 0.0, "ap_ratio": 0.0,
    #  "target_max_hp_ratio": 0.0, "target_missing_hp_ratio": 0.0}
    damages: List[Dict] = field(default_factory=list)
    cooldowns: List[float] = field(default_factory=list)


@dataclass
class Champion:
    name: str
    id: str
    stats: ChampionStats
    spells: Dict[str, Spell] = field(default_factory=dict)
    # Auto-attack damage type is almost always physical.
    aa_type: str = "physical"


@dataclass
class Item:
    id: int
    name: str
    cost: int = 0
    # Flat stat bonuses
    ad: float = 0.0           # FlatPhysicalDamageMod
    ap: float = 0.0           # FlatMagicDamageMod
    hp: float = 0.0
    mp: float = 0.0
    armor: float = 0.0
    mr: float = 0.0           # FlatSpellBlockMod
    attack_speed: float = 0.0  # PercentAttackSpeedMod (0.30 = +30%)
    crit_chance: float = 0.0   # FlatCritChanceMod (0.20 = 20%)
    move_speed_flat: float = 0.0
    move_speed_percent: float = 0.0
    lifesteal: float = 0.0
    # Penetration stats are typically not in Data Dragon (live in passives).
    # We expose these so the user can set them explicitly or via custom mods.
    lethality: float = 0.0
    armor_pen_percent: float = 0.0
    flat_magic_pen: float = 0.0
    magic_pen_percent: float = 0.0
    # Free-form tags Data Dragon provides.
    tags: List[str] = field(default_factory=list)
    description: str = ""


@dataclass
class Rune:
    id: int
    key: str
    name: str
    tree: str = ""           # Precision, Domination, Sorcery, Resolve, Inspiration
    is_keystone: bool = False
    description: str = ""


@dataclass
class StatShard:
    """Inline stat shards in the rune page (Adaptive, AS, AH, etc.)."""

    name: str
    ad: float = 0.0
    ap: float = 0.0
    attack_speed: float = 0.0
    ability_haste: float = 0.0
    move_speed_percent: float = 0.0
    hp: float = 0.0
    armor: float = 0.0
    mr: float = 0.0


@dataclass
class RunePage:
    keystone: Optional[Rune] = None
    primary: List[Rune] = field(default_factory=list)
    secondary: List[Rune] = field(default_factory=list)
    shards: List[StatShard] = field(default_factory=list)

    def all_runes(self) -> List[Rune]:
        out: List[Rune] = []
        if self.keystone is not None:
            out.append(self.keystone)
        out.extend(self.primary)
        out.extend(self.secondary)
        return out


@dataclass
class Build:
    """A champion's full setup: level, items, runes, manual overrides."""

    champion: Champion
    level: int = 1
    items: List[Item] = field(default_factory=list)
    runes: RunePage = field(default_factory=RunePage)
    # Skill point allocation (Q/W/E/R rank 0-5).
    skill_ranks: Dict[str, int] = field(default_factory=lambda: {"Q": 1, "W": 1, "E": 1, "R": 1})
    # Optional flat overrides (e.g., extra lethality from runes/elixirs).
    bonus_lethality: float = 0.0
    bonus_armor_pen_percent: float = 0.0
    bonus_flat_magic_pen: float = 0.0
    bonus_magic_pen_percent: float = 0.0
    bonus_ad_flat: float = 0.0
    bonus_ap_flat: float = 0.0
    bonus_crit_chance: float = 0.0
    crit_damage: float = 1.75  # 175% by default; IE/Navori add more


@dataclass
class Target:
    """The recipient of damage."""

    name: str = "Dummy"
    level: int = 1
    max_hp: float = 1000.0
    current_hp: Optional[float] = None  # defaults to max_hp
    armor: float = 30.0
    magic_resist: float = 30.0
    # Damage reduction multipliers (flat 1 = no reduction).
    damage_reduction: float = 1.0  # e.g. 0.7 means take 70% damage

    def __post_init__(self) -> None:
        if self.current_hp is None:
            self.current_hp = self.max_hp

    def missing_hp(self) -> float:
        return max(0.0, self.max_hp - (self.current_hp or self.max_hp))

    def missing_hp_pct(self) -> float:
        return self.missing_hp() / self.max_hp if self.max_hp > 0 else 0.0
