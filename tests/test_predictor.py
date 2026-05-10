"""Predictor tests using fabricated champions/items (no network)."""
import pytest

from lol_damage.models import (
    Build,
    Champion,
    ChampionStats,
    Item,
    Rune,
    RunePage,
    StatShard,
    Target,
)
from lol_damage.predictor import DamagePredictor
from lol_damage.spell_overrides import register


def _fake_garen() -> Champion:
    return Champion(
        name="Fakaren",
        id="Fakaren",
        stats=ChampionStats(
            hp=690, hp_per_level=104,
            armor=36, armor_per_level=4.5,
            spellblock=32, spellblock_per_level=2.05,
            attackdamage=64, attackdamage_per_level=4.5,
            attackspeed=0.625, attackspeed_per_level=2.9,
        ),
    )


def test_combat_stats_scale_with_level_and_items():
    champ = _fake_garen()
    build = Build(
        champion=champ,
        level=11,
        items=[Item(id=1, name="AD Sword", ad=70), Item(id=2, name="More AD", ad=30, crit_chance=0.25)],
    )
    cs = DamagePredictor(build).combat_stats()
    # base_ad at lvl 11: 64 + 4.5 * 10 * (0.7025 + 0.0175 * 10) = 64 + 45*0.8775 = 103.4875
    assert cs.base_ad == pytest.approx(103.4875, rel=1e-4)
    assert cs.bonus_ad == pytest.approx(100)
    assert cs.crit_chance == pytest.approx(0.25)


def test_auto_attack_expected_and_crit():
    champ = _fake_garen()
    build = Build(champion=champ, level=11, items=[Item(id=1, name="AD", ad=100)])
    target = Target(name="t", level=11, max_hp=2000, armor=100, magic_resist=50)
    p = DamagePredictor(build)

    cs = p.combat_stats()
    expected = p.auto_attack(target, crit=None)
    crit = p.auto_attack(target, crit=True)
    nocrit = p.auto_attack(target, crit=False)

    # No crit chance: expected == non-crit.
    assert expected.mitigated == pytest.approx(nocrit.mitigated)
    # Crit applies the multiplier.
    assert crit.mitigated == pytest.approx(nocrit.mitigated * cs.crit_damage)


def test_spell_with_registered_formula():
    champ = _fake_garen()
    register("Fakaren", "Q", {
        "type": "physical",
        "base_per_rank": [50, 80, 110, 140, 170],
        "bonus_ad_ratio": 1.0,
    })
    build = Build(
        champion=champ,
        level=11,
        items=[Item(id=1, name="AD", ad=100)],
        skill_ranks={"Q": 5, "W": 1, "E": 1, "R": 1},
    )
    target = Target(max_hp=2000, armor=0, magic_resist=0)
    hr = DamagePredictor(build).spell("Q", target)
    # Raw = 170 + 1.0 * 100 (bonus AD) = 270, vs 0 armor -> 270.
    assert hr.raw == pytest.approx(270.0)
    assert hr.mitigated == pytest.approx(270.0)
    assert hr.damage_type == "physical"


def test_combo_tracks_hp_and_kills():
    champ = _fake_garen()
    build = Build(
        champion=champ,
        level=11,
        items=[Item(id=1, name="AD", ad=200)],
        skill_ranks={"Q": 5, "W": 1, "E": 1, "R": 1},
    )
    target = Target(max_hp=200, armor=0, magic_resist=0)
    p = DamagePredictor(build)
    result = p.combo(["A.", "A.", "A.", "A."], target)
    # Each non-crit auto deals total_ad damage; lvl 11 base ~103.5 + 200 = 303.5.
    # First auto kills the 200-HP target.
    assert result.killed
    assert len(result.hits) == 1


def test_multi_hit_stops_on_kill():
    champ = _fake_garen()
    build = Build(champion=champ, level=11, items=[Item(id=1, name="AD", ad=200)])
    target = Target(max_hp=50, armor=0)
    p = DamagePredictor(build)
    r = p.multi_hit(target, n=10, action="auto", crit_pattern="never")
    assert r.killed
    assert len(r.hits) == 1


def test_armor_pen_percent_compounds_multiplicatively():
    champ = _fake_garen()
    build = Build(
        champion=champ,
        level=11,
        items=[
            Item(id=1, name="A", ad=0, armor_pen_percent=0.30),
            Item(id=2, name="B", ad=0, armor_pen_percent=0.30),
        ],
    )
    cs = DamagePredictor(build).combat_stats()
    # Compounded: 1 - 0.7 * 0.7 = 0.51
    assert cs.armor_pen_percent == pytest.approx(0.51)


def test_rune_shard_adds_ad():
    champ = _fake_garen()
    build = Build(
        champion=champ,
        level=11,
        runes=RunePage(shards=[StatShard(name="AD shard", ad=9)]),
    )
    cs = DamagePredictor(build).combat_stats()
    assert cs.bonus_ad == pytest.approx(9)


def test_unknown_spell_returns_zero_with_note():
    champ = _fake_garen()
    build = Build(champion=champ, level=11)
    target = Target()
    hr = DamagePredictor(build).spell("W", target)
    assert hr.mitigated == 0
    assert "No registered formula" in hr.notes
