"""High-level damage prediction for single hits, multi-hits, and combos."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional, Sequence

from .damage import (
    CombatStats,
    apply_damage,
    crit_auto_damage,
    effective_armor,
    effective_mr,
    expected_auto_damage,
    lethality_to_flat_pen,
    non_crit_auto_damage,
    resist_multiplier,
)
from .models import Build, Item, Target
from .runes import apply_rune_stats, keystone_amp, keystone_proc_damage
from .spell_overrides import lookup as lookup_spell


@dataclass
class HitResult:
    label: str
    damage_type: str
    raw: float
    mitigated: float
    notes: str = ""
    explanation: List[str] = field(default_factory=list)


@dataclass
class ComboResult:
    hits: List[HitResult] = field(default_factory=list)
    total: float = 0.0
    target_hp_remaining: float = 0.0
    killed: bool = False

    def summary(self) -> str:
        rows = [f"  {h.label:<28} {h.damage_type:<8} raw={h.raw:7.1f}  -> {h.mitigated:7.1f}" for h in self.hits]
        return "\n".join(rows) + f"\n  TOTAL: {self.total:.1f}  HP left: {self.target_hp_remaining:.0f}{' (KILL)' if self.killed else ''}"


class DamagePredictor:
    """Compute predicted damage for a champion build against a target.

    Use the high-level methods (:meth:`single_hit`, :meth:`multi_hit`,
    :meth:`combo`) to get :class:`HitResult` / :class:`ComboResult` objects.
    """

    def __init__(self, build: Build):
        self.build = build

    # ---------------- effective stats ----------------

    def combat_stats(self) -> CombatStats:
        b = self.build
        c = b.champion
        s = c.stats.at_level(b.level)

        item_ad = sum(it.ad for it in b.items)
        item_ap = sum(it.ap for it in b.items)
        item_hp = sum(it.hp for it in b.items)
        item_armor = sum(it.armor for it in b.items)
        item_mr = sum(it.mr for it in b.items)
        item_as = sum(it.attack_speed for it in b.items)
        item_crit = sum(it.crit_chance for it in b.items)
        item_lethality = sum(it.lethality for it in b.items)
        item_apen_pct = 1.0 - _product(1.0 - it.armor_pen_percent for it in b.items)
        item_mpen_flat = sum(it.flat_magic_pen for it in b.items)
        item_mpen_pct = 1.0 - _product(1.0 - it.magic_pen_percent for it in b.items)

        cs = CombatStats(
            level=b.level,
            base_ad=s.attackdamage,
            bonus_ad=item_ad + b.bonus_ad_flat,
            ap=item_ap + b.bonus_ap_flat,
            attack_speed=s.attackspeed * (1.0 + item_as),
            crit_chance=min(1.0, s.crit + item_crit + b.bonus_crit_chance),
            crit_damage=b.crit_damage,
            lethality=item_lethality + b.bonus_lethality,
            armor_pen_percent=min(0.99, item_apen_pct + b.bonus_armor_pen_percent),
            flat_magic_pen=item_mpen_flat + b.bonus_flat_magic_pen,
            magic_pen_percent=min(0.99, item_mpen_pct + b.bonus_magic_pen_percent),
            bonus_hp=item_hp,
            max_hp=s.hp + item_hp,
            armor=s.armor + item_armor,
            magic_resist=s.spellblock + item_mr,
        )

        cs = apply_rune_stats(b, cs)

        # Apply keystone amps that always apply (Coup de Grace etc. depend on target HP and
        # are layered on per-hit in combo evaluation).
        return cs

    # ---------------- single hits ----------------

    def auto_attack(self, target: Target, crit: Optional[bool] = None) -> HitResult:
        """A single auto-attack. ``crit=None`` returns expected damage."""
        cs = self.combat_stats()
        steps: List[str] = [f"Total AD = base {cs.base_ad:.1f} + bonus {cs.bonus_ad:.1f} = {cs.total_ad:.1f}"]

        if crit is True:
            raw = cs.total_ad * cs.crit_damage
            steps.append(f"Crit: {cs.total_ad:.1f} × {cs.crit_damage:.2f} = {raw:.1f}")
            mitigated = crit_auto_damage(cs, target.armor, target.damage_reduction)
            label = "Auto (crit)"
        elif crit is False:
            raw = cs.total_ad
            steps.append(f"No crit: raw = {raw:.1f}")
            mitigated = non_crit_auto_damage(cs, target.armor, target.damage_reduction)
            label = "Auto"
        else:
            mult = 1 + cs.crit_chance * (cs.crit_damage - 1)
            raw = cs.total_ad * mult
            steps.append(
                f"Avg crit (chance {cs.crit_chance:.0%}, mult {cs.crit_damage:.2f}×): "
                f"{cs.total_ad:.1f} × {mult:.3f} = {raw:.1f}"
            )
            mitigated = expected_auto_damage(cs, target.armor, target.damage_reduction)
            label = f"Auto (avg)"

        steps.extend(_armor_steps(cs, target))
        if cs.physical_amp != 1.0 or cs.versus_amp != 1.0:
            steps.append(f"Amps: physical ×{cs.physical_amp:.2f}, vs target ×{cs.versus_amp:.2f}")
        steps.append(f"Mitigated = {mitigated:.1f}")
        return HitResult(label=label, damage_type="physical", raw=raw, mitigated=mitigated, explanation=steps)

    def spell(self, spell_key: str, target: Target) -> HitResult:
        """Damage from a single cast of Q/W/E/R."""
        cs = self.combat_stats()
        b = self.build
        cid = b.champion.id
        defn = lookup_spell(cid, spell_key)
        if defn is None:
            return HitResult(
                label=f"{cid} {spell_key.upper()}",
                damage_type="unknown",
                raw=0.0,
                mitigated=0.0,
                notes=f"No registered formula for {cid} {spell_key.upper()}.",
                explanation=[
                    f"No registered formula for {cid} {spell_key.upper()}.",
                    "Add via lol_damage.spell_overrides.register().",
                ],
            )
        rank = max(1, b.skill_ranks.get(spell_key.upper(), 1))

        steps: List[str] = []
        base_list = defn.get("base_per_rank") or []
        base = float(base_list[min(rank, len(base_list)) - 1]) if base_list else 0.0
        raw = base
        steps.append(f"Base @ rank {rank}: {base:.1f}")

        def add(ratio_key: str, label: str, value: float) -> None:
            nonlocal raw
            ratio = defn.get(ratio_key, 0.0) or 0.0
            if ratio == 0.0 or value == 0.0:
                return
            v = ratio * value
            raw += v
            steps.append(f"+ {ratio * 100:.0f}% {label} ({value:.1f}) = {v:.1f}")

        add("ad_ratio", "total AD", cs.total_ad)
        add("bonus_ad_ratio", "bonus AD", cs.bonus_ad)
        add("ap_ratio", "AP", cs.ap)
        add("target_max_hp_ratio", "target max HP", target.max_hp)
        add("target_missing_hp_ratio", "target missing HP", target.missing_hp())

        steps.append(f"Raw total: {raw:.1f}")

        dt = defn["type"]
        if dt == "physical":
            steps.extend(_armor_steps(cs, target))
        elif dt == "magic":
            steps.extend(_mr_steps(cs, target))
        else:
            steps.append("True damage: ignores resists")

        mitigated = apply_damage(raw, dt, cs, target.armor, target.magic_resist, target.damage_reduction)
        steps.append(f"Mitigated = {mitigated:.1f}")
        return HitResult(
            label=f"{cid} {spell_key.upper()}",
            damage_type=dt,
            raw=raw,
            mitigated=mitigated,
            explanation=steps,
        )

    # ---------------- multi-hit ----------------

    def multi_hit(
        self,
        target: Target,
        n: int,
        action: str = "auto",
        spell_key: Optional[str] = None,
        crit_pattern: str = "expected",
    ) -> ComboResult:
        """Compute damage from ``n`` repeated auto-attacks or spell casts.

        ``crit_pattern`` for autos: 'expected' (uses crit chance), 'never', 'always'.
        """
        if n <= 0:
            return ComboResult()
        target = _clone_target(target)
        result = ComboResult()
        for i in range(n):
            if action == "auto":
                if crit_pattern == "always":
                    hr = self.auto_attack(target, crit=True)
                elif crit_pattern == "never":
                    hr = self.auto_attack(target, crit=False)
                else:
                    hr = self.auto_attack(target, crit=None)
            elif action == "spell":
                if spell_key is None:
                    raise ValueError("spell_key required when action='spell'")
                hr = self.spell(spell_key, target)
            else:
                raise ValueError(f"Unknown action: {action}")
            hr = HitResult(label=f"#{i+1} {hr.label}", damage_type=hr.damage_type, raw=hr.raw, mitigated=hr.mitigated, notes=hr.notes)
            result.hits.append(hr)
            target.current_hp = max(0.0, (target.current_hp or 0.0) - hr.mitigated)
            if target.current_hp <= 0:
                result.killed = True
                break
        result.total = sum(h.mitigated for h in result.hits)
        result.target_hp_remaining = target.current_hp or 0.0
        return result

    # ---------------- combos ----------------

    def combo(self, sequence: Sequence[str], target: Target) -> ComboResult:
        """Evaluate a combo expressed as a sequence of action tokens.

        Tokens:
          'Q' / 'W' / 'E' / 'R'  -> spell cast
          'A'                     -> auto attack (uses expected crit)
          'A!'                    -> guaranteed crit auto
          'A.'                    -> guaranteed non-crit auto
          'KEYSTONE'              -> proc the keystone (Electrocute etc.)

        HP is tracked between hits so missing-HP scaling works correctly.
        """
        target = _clone_target(target)
        result = ComboResult()
        b = self.build
        keystone_name = b.runes.keystone.name if b.runes.keystone else ""

        for token in sequence:
            tok = token.strip()
            if tok in ("Q", "W", "E", "R"):
                hr = self.spell(tok, target)
            elif tok == "A":
                hr = self.auto_attack(target, crit=None)
            elif tok == "A!":
                hr = self.auto_attack(target, crit=True)
            elif tok == "A.":
                hr = self.auto_attack(target, crit=False)
            elif tok.upper() == "KEYSTONE":
                cs = self.combat_stats()
                amount = keystone_proc_damage(keystone_name, cs, target)
                explanation = [f"Keystone: {keystone_name or '(none)'}"]
                if amount == 0 and keystone_name:
                    explanation.append("No proc damage (either non-damage keystone or condition not met).")
                else:
                    explanation.append(f"Proc damage (post-mitigation): {amount:.1f}")
                hr = HitResult(
                    label=f"Keystone: {keystone_name or '(none)'}",
                    damage_type="proc", raw=amount, mitigated=amount, explanation=explanation,
                )
            else:
                raise ValueError(f"Unknown combo token: {token}")
            result.hits.append(hr)
            target.current_hp = max(0.0, (target.current_hp or 0.0) - hr.mitigated)
            if target.current_hp <= 0:
                result.killed = True
                break

        # Apply post-keystone amps (Coup de Grace / Cut Down) by re-walking? Keep simple:
        # we already include amps in the CombatStats path via runes; cross-target conditional
        # amps can be set explicitly by the caller via Build.bonus_*.
        result.total = sum(h.mitigated for h in result.hits)
        result.target_hp_remaining = target.current_hp or 0.0
        return result


# ---------------- helpers ----------------

def _armor_steps(cs: CombatStats, target: Target) -> List[str]:
    flat_pen = lethality_to_flat_pen(cs.lethality, cs.level)
    eff = effective_armor(target.armor, flat_pen, cs.armor_pen_percent)
    mult = resist_multiplier(eff)
    parts = [f"Target armor {target.armor:.0f}"]
    if cs.armor_pen_percent:
        parts.append(f"−{cs.armor_pen_percent * 100:.0f}% pen")
    if flat_pen:
        parts.append(f"−{flat_pen:.1f} flat (lethality {cs.lethality:.0f})")
    parts.append(f"= effective {eff:.1f}")
    return [", ".join(parts), f"Mitigation multiplier: ×{mult:.3f}"]


def _mr_steps(cs: CombatStats, target: Target) -> List[str]:
    eff = effective_mr(target.magic_resist, cs.flat_magic_pen, cs.magic_pen_percent)
    mult = resist_multiplier(eff)
    parts = [f"Target MR {target.magic_resist:.0f}"]
    if cs.magic_pen_percent:
        parts.append(f"−{cs.magic_pen_percent * 100:.0f}% pen")
    if cs.flat_magic_pen:
        parts.append(f"−{cs.flat_magic_pen:.1f} flat")
    parts.append(f"= effective {eff:.1f}")
    return [", ".join(parts), f"Mitigation multiplier: ×{mult:.3f}"]


def _resolve_spell_raw(defn: dict, rank: int, cs: CombatStats, target: Target) -> float:
    base_list = defn.get("base_per_rank") or []
    base = base_list[min(rank, len(base_list)) - 1] if base_list else 0.0
    raw = float(base)
    raw += defn.get("ad_ratio", 0.0) * cs.total_ad
    raw += defn.get("bonus_ad_ratio", 0.0) * cs.bonus_ad
    raw += defn.get("ap_ratio", 0.0) * cs.ap
    raw += defn.get("target_max_hp_ratio", 0.0) * target.max_hp
    raw += defn.get("target_missing_hp_ratio", 0.0) * target.missing_hp()
    return raw


def _clone_target(t: Target) -> Target:
    return Target(
        name=t.name,
        level=t.level,
        max_hp=t.max_hp,
        current_hp=t.current_hp if t.current_hp is not None else t.max_hp,
        armor=t.armor,
        magic_resist=t.magic_resist,
        damage_reduction=t.damage_reduction,
    )


def _product(iterable) -> float:
    p = 1.0
    for x in iterable:
        p *= x
    return p
