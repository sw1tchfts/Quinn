"""Parser tests using cached fixtures (no live network)."""
import json
from pathlib import Path

from lol_damage.data import _parse_champion, _parse_item, _strip_tags


def test_strip_tags():
    assert _strip_tags("<span class='x'>Deal <b>50</b> damage</span>") == "Deal 50 damage"


def test_parse_item_extracts_stats():
    raw = {
        "name": "Test Sword",
        "gold": {"total": 3000},
        "stats": {
            "FlatPhysicalDamageMod": 60,
            "FlatCritChanceMod": 0.20,
            "PercentAttackSpeedMod": 0.30,
        },
        "tags": ["Damage", "CriticalStrike"],
        "description": "<b>+60 AD</b> rad sword",
    }
    item = _parse_item(1234, raw)
    assert item.id == 1234
    assert item.name == "Test Sword"
    assert item.cost == 3000
    assert item.ad == 60
    assert item.crit_chance == 0.20
    assert item.attack_speed == 0.30
    assert "Damage" in item.tags
    assert item.description == "+60 AD rad sword"


def test_parse_champion_minimal():
    raw = {
        "id": "Pytest",
        "name": "Pytest",
        "stats": {
            "hp": 600, "hpperlevel": 100, "mp": 300, "mpperlevel": 40,
            "armor": 30, "armorperlevel": 4,
            "spellblock": 32, "spellblockperlevel": 1.3,
            "attackdamage": 60, "attackdamageperlevel": 3,
            "attackspeed": 0.65, "attackspeedperlevel": 2.5,
            "movespeed": 340, "attackrange": 175,
        },
        "spells": [
            {"name": "Q", "description": "deal damage", "maxrank": 5, "effect": [None, [10, 20, 30, 40, 50]]},
        ],
        "passive": {"name": "Pass", "description": "<x>passive</x>"},
    }
    champ = _parse_champion(raw)
    assert champ.id == "Pytest"
    assert champ.stats.attackdamage == 60
    assert "Q" in champ.spells
    assert "P" in champ.spells
    assert champ.spells["P"].description == "passive"
    # Effect parsing exposes the values list.
    assert champ.spells["Q"].damages[0]["values_per_rank"] == [10, 20, 30, 40, 50]
