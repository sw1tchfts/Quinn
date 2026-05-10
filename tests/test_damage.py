"""Unit tests for the core damage math (no network required)."""
import math

import pytest

from lol_damage.damage import (
    CombatStats,
    apply_damage,
    crit_auto_damage,
    effective_armor,
    expected_auto_damage,
    lethality_to_flat_pen,
    non_crit_auto_damage,
    resist_multiplier,
)


def test_resist_multiplier_zero_armor_is_one():
    assert resist_multiplier(0) == 1.0


def test_resist_multiplier_positive_armor():
    # 100 armor -> takes 50% damage.
    assert resist_multiplier(100) == pytest.approx(0.5)


def test_resist_multiplier_negative_armor():
    # -100 armor -> takes 150%.
    assert resist_multiplier(-100) == pytest.approx(1.5)


def test_lethality_scaling_linear_with_level():
    # At level 1 lethality is 60% effective; at 18 it's 100%.
    assert lethality_to_flat_pen(10, 1) == pytest.approx(10 * (0.6 + 0.4 / 18))
    assert lethality_to_flat_pen(10, 18) == pytest.approx(10.0)


def test_effective_armor_applies_percent_then_flat():
    # 100 armor, 30% pen -> 70; minus 10 flat -> 60.
    assert effective_armor(100, flat_pen=10, percent_pen=0.30) == pytest.approx(60.0)


def test_effective_armor_does_not_go_below_zero_from_pen():
    assert effective_armor(20, flat_pen=50, percent_pen=0) == 0.0


def test_apply_damage_physical_with_armor():
    # 200 armor -> 1/3 damage taken.
    cs = CombatStats(level=10)
    out = apply_damage(300, "physical", cs, target_armor=200, target_mr=0)
    assert out == pytest.approx(100.0)


def test_apply_damage_true_ignores_resists():
    cs = CombatStats(level=10)
    assert apply_damage(123, "true", cs, target_armor=999, target_mr=999) == pytest.approx(123)


def test_expected_auto_uses_crit_chance():
    cs = CombatStats(level=10, base_ad=100, bonus_ad=0, crit_chance=0.5, crit_damage=2.0)
    # No armor: expected = 100 * (1 + 0.5 * 1) = 150.
    out = expected_auto_damage(cs, target_armor=0)
    assert out == pytest.approx(150.0)


def test_crit_and_non_crit_match_definitions():
    cs = CombatStats(level=10, base_ad=100, bonus_ad=50, crit_damage=1.75)
    assert non_crit_auto_damage(cs, 0) == pytest.approx(150.0)
    assert crit_auto_damage(cs, 0) == pytest.approx(150.0 * 1.75)


def test_amp_multipliers_compound():
    cs = CombatStats(level=10, physical_amp=1.10, versus_amp=1.05)
    # 100 raw vs 0 armor -> 100 * 1.10 * 1.05 = 115.5
    assert apply_damage(100, "physical", cs, 0, 0) == pytest.approx(115.5)
