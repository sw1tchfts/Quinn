"""Hand-curated spell damage definitions.

Data Dragon's spell payloads do not reliably tag damage type or AD/AP ratios in
machine-readable form, so the predictor relies on a small registry of spells we
know how to compute. Users can register their own via :func:`register`.

Each entry is a dict with keys:
  type:                    'physical' | 'magic' | 'true'
  base_per_rank:           list of floats indexed by rank-1
  ad_ratio:                float on total AD
  bonus_ad_ratio:          float on bonus AD
  ap_ratio:                float on AP
  target_max_hp_ratio:     float on target max HP
  target_missing_hp_ratio: float on target missing HP

Optional 'aoe' (bool) and 'on_hit' (bool) flags are informational.

Champion key uses Data Dragon's id (e.g. 'Garen', 'MissFortune').
"""
from __future__ import annotations

from typing import Dict, List, Optional


# (champion_id, spell_key) -> spell damage definition
REGISTRY: Dict[tuple, dict] = {}


def register(champion_id: str, spell_key: str, definition: dict) -> None:
    REGISTRY[(champion_id, spell_key.upper())] = definition


def lookup(champion_id: str, spell_key: str) -> Optional[dict]:
    return REGISTRY.get((champion_id, spell_key.upper()))


# ---------------- a curated subset (current as of 2024-2025 patches) ----------------

# Garen — Decisive Strike (Q): physical AD scaling.
register("Garen", "Q", {
    "type": "physical",
    "base_per_rank": [30, 55, 80, 105, 130],
    "bonus_ad_ratio": 0.5,
})
# Garen — Judgment (E): physical, big total over channel; we model the total spin damage.
register("Garen", "E", {
    "type": "physical",
    "base_per_rank": [40, 64, 88, 112, 136],  # rough per-tick-base * ticks total simplification
    "ad_ratio": 2.6,  # total AD ratio over full duration (approximate)
})
# Garen — Demacian Justice (R): magic, scales with target missing HP.
register("Garen", "R", {
    "type": "magic",
    "base_per_rank": [150, 300, 450],
    "target_missing_hp_ratio": 0.20,
})

# Annie — Disintegrate (Q)
register("Annie", "Q", {
    "type": "magic",
    "base_per_rank": [80, 110, 140, 170, 200],
    "ap_ratio": 0.8,
})
# Annie — Incinerate (W)
register("Annie", "W", {
    "type": "magic",
    "base_per_rank": [70, 115, 160, 205, 250],
    "ap_ratio": 0.85,
})
# Annie — Summon Tibbers (R)
register("Annie", "R", {
    "type": "magic",
    "base_per_rank": [150, 275, 400],
    "ap_ratio": 0.65,
})

# Ahri
register("Ahri", "Q", {
    "type": "magic",
    "base_per_rank": [40, 65, 90, 115, 140],
    "ap_ratio": 0.4,
})
register("Ahri", "W", {
    "type": "magic",
    "base_per_rank": [55, 80, 105, 130, 155],
    "ap_ratio": 0.45,
})
register("Ahri", "E", {
    "type": "magic",
    "base_per_rank": [80, 110, 140, 170, 200],
    "ap_ratio": 0.6,
})
register("Ahri", "R", {
    "type": "magic",
    "base_per_rank": [60, 90, 120],
    "ap_ratio": 0.35,
})

# Lux
register("Lux", "Q", {
    "type": "magic",
    "base_per_rank": [50, 100, 150, 200, 250],
    "ap_ratio": 0.6,
})
register("Lux", "E", {
    "type": "magic",
    "base_per_rank": [60, 105, 150, 195, 240],
    "ap_ratio": 0.6,
})
register("Lux", "R", {
    "type": "magic",
    "base_per_rank": [300, 400, 500],
    "ap_ratio": 1.2,
})

# Miss Fortune
register("MissFortune", "Q", {
    "type": "physical",
    "base_per_rank": [20, 40, 60, 80, 100],
    "ad_ratio": 1.0,
    "bonus_ad_ratio": 0.35,
})
register("MissFortune", "E", {
    "type": "magic",
    "base_per_rank": [80, 130, 180, 230, 280],
    "ap_ratio": 0.8,
})
register("MissFortune", "R", {
    "type": "physical",
    "base_per_rank": [600, 900, 1200],
    "bonus_ad_ratio": 2.4,
    "ap_ratio": 1.2,
})

# Darius
register("Darius", "Q", {
    "type": "physical",
    "base_per_rank": [50, 80, 110, 140, 170],
    "bonus_ad_ratio": 1.1,
})
register("Darius", "E", {
    # E pulls; minor damage, ignored here.
    "type": "physical",
    "base_per_rank": [0, 0, 0, 0, 0],
})
register("Darius", "R", {
    "type": "true",
    "base_per_rank": [125, 250, 375],
    "bonus_ad_ratio": 0.75,
})

# Lee Sin
register("LeeSin", "Q", {
    "type": "physical",
    "base_per_rank": [55, 80, 105, 130, 155],
    "bonus_ad_ratio": 1.0,
    "target_missing_hp_ratio": 0.08,
})
register("LeeSin", "R", {
    "type": "physical",
    "base_per_rank": [175, 400, 625],
    "bonus_ad_ratio": 2.0,
})

# Zed
register("Zed", "Q", {
    "type": "physical",
    "base_per_rank": [70, 95, 120, 145, 170],
    "bonus_ad_ratio": 1.0,
})
register("Zed", "E", {
    "type": "physical",
    "base_per_rank": [60, 80, 100, 120, 140],
    "bonus_ad_ratio": 0.65,
})
register("Zed", "R", {
    # R is an execute amp on stored damage; modeled as a scalar bonus.
    "type": "physical",
    "base_per_rank": [0, 0, 0],
    "bonus_ad_ratio": 0.0,
})

# Veigar (true ult)
register("Veigar", "Q", {
    "type": "magic",
    "base_per_rank": [70, 110, 150, 190, 230],
    "ap_ratio": 0.6,
})
register("Veigar", "W", {
    "type": "magic",
    "base_per_rank": [100, 150, 200, 250, 300],
    "ap_ratio": 1.0,
})
register("Veigar", "R", {
    "type": "magic",
    "base_per_rank": [175, 250, 325],
    "ap_ratio": 0.75,
    "target_missing_hp_ratio": 1.5 / 100.0 * 50,  # rough: scales with missing HP per 100 AP; simplified
})


def known_champions() -> List[str]:
    return sorted({cid for cid, _ in REGISTRY.keys()})
