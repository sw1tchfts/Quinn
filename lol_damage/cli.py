"""CLI for the LoL damage predictor.

Examples
--------
List champions/items::

    lol-damage list-champions
    lol-damage list-items "Infinity"

Predict a single auto::

    lol-damage predict --champion Garen --level 11 \
        --items "Stridebreaker" "Black Cleaver" \
        --target-armor 100 --target-mr 50 --target-hp 2400 \
        --auto

Run a combo::

    lol-damage predict --champion Garen --level 11 \
        --items "Stridebreaker" "Black Cleaver" "Sterak's Gage" \
        --skills Q=5,E=5,R=3 --rune-keystone "Conqueror" \
        --target-hp 2400 --target-armor 120 --target-mr 50 \
        --combo Q,A,E,R
"""
from __future__ import annotations

import argparse
import sys
from typing import List, Optional

from .data import DataDragon
from .models import Build, RunePage, StatShard, Target


def _parse_skills(s: str):
    out = {"Q": 1, "W": 1, "E": 1, "R": 1}
    if not s:
        return out
    for part in s.split(","):
        if "=" not in part:
            continue
        k, v = part.split("=", 1)
        out[k.strip().upper()] = int(v.strip())
    return out


def _build_from_args(dd: DataDragon, args) -> Build:
    champ = dd.champion(args.champion)
    items = []
    for name in args.items or []:
        items.append(dd.item(name))

    rune_page = RunePage()
    if args.rune_keystone:
        rune_page.keystone = dd.rune(args.rune_keystone)
    for r in args.rune or []:
        rune_page.primary.append(dd.rune(r))

    if args.shard_ad:
        rune_page.shards.append(StatShard(name="Adaptive (AD)", ad=args.shard_ad))
    if args.shard_ap:
        rune_page.shards.append(StatShard(name="Adaptive (AP)", ap=args.shard_ap))
    if args.shard_as:
        rune_page.shards.append(StatShard(name="Attack Speed", attack_speed=args.shard_as))

    return Build(
        champion=champ,
        level=args.level,
        items=items,
        runes=rune_page,
        skill_ranks=_parse_skills(args.skills or ""),
        bonus_lethality=args.bonus_lethality,
        bonus_armor_pen_percent=args.bonus_armor_pen_percent,
        bonus_flat_magic_pen=args.bonus_flat_magic_pen,
        bonus_magic_pen_percent=args.bonus_magic_pen_percent,
        crit_damage=args.crit_damage,
    )


def _target_from_args(args) -> Target:
    return Target(
        name=args.target_name,
        level=args.target_level,
        max_hp=args.target_hp,
        current_hp=args.target_current_hp if args.target_current_hp >= 0 else args.target_hp,
        armor=args.target_armor,
        magic_resist=args.target_mr,
        damage_reduction=args.target_dr,
    )


def cmd_predict(args) -> int:
    from .predictor import DamagePredictor

    dd = DataDragon(version=args.patch)
    build = _build_from_args(dd, args)
    target = _target_from_args(args)
    p = DamagePredictor(build)

    print(f"Champion: {build.champion.name} (lvl {build.level})")
    cs = p.combat_stats()
    print(f"  AD: {cs.total_ad:.1f} (base {cs.base_ad:.1f} + bonus {cs.bonus_ad:.1f})  AP: {cs.ap:.1f}")
    print(f"  AS: {cs.attack_speed:.2f}  Crit: {cs.crit_chance:.0%}@{cs.crit_damage:.2f}x")
    print(f"  Lethality: {cs.lethality:.0f}  %ArmorPen: {cs.armor_pen_percent:.0%}")
    print(f"  MagicPen flat: {cs.flat_magic_pen:.0f}  %MagicPen: {cs.magic_pen_percent:.0%}")
    print(f"Target: {target.name} HP={target.current_hp:.0f}/{target.max_hp:.0f} armor={target.armor} mr={target.magic_resist}")
    print()

    if args.auto:
        print("Single auto-attack:")
        for crit, label in [(False, "non-crit"), (True, "crit"), (None, "expected")]:
            r = p.auto_attack(target, crit=crit)
            print(f"  {label:<10} raw={r.raw:7.1f}  -> {r.mitigated:7.1f}")
        print()

    if args.spell:
        print("Spell single-cast:")
        for sk in args.spell:
            r = p.spell(sk, target)
            print(f"  {r.label:<20} raw={r.raw:7.1f}  -> {r.mitigated:7.1f} ({r.damage_type})")
            if r.notes:
                print(f"    note: {r.notes}")
        print()

    if args.multi:
        n, action = args.multi
        n = int(n)
        spell_key = action.upper() if action.upper() in {"Q", "W", "E", "R"} else None
        kind = "spell" if spell_key else "auto"
        result = p.multi_hit(target, n=n, action=kind, spell_key=spell_key, crit_pattern=args.crit_pattern)
        print(f"Multi-hit ({n} x {action}):")
        print(result.summary())
        print()

    if args.combo:
        seq = [s.strip() for s in args.combo.split(",") if s.strip()]
        result = p.combo(seq, target)
        print(f"Combo: {' -> '.join(seq)}")
        print(result.summary())
        print()
    return 0


def cmd_list_champions(args) -> int:
    dd = DataDragon(version=args.patch)
    for c in dd.list_champions():
        print(c)
    return 0


def cmd_list_items(args) -> int:
    dd = DataDragon(version=args.patch)
    items = dd.items()
    needle = (args.query or "").lower()
    for it in items.values():
        if not needle or needle in it.name.lower():
            tags = ",".join(it.tags) if it.tags else ""
            print(f"  {it.id:<5} {it.name:<30} cost={it.cost:<5} ad={it.ad:<5} ap={it.ap:<5} {tags}")
    return 0


def cmd_list_runes(args) -> int:
    dd = DataDragon(version=args.patch)
    for r in dd.runes():
        ks = " (keystone)" if r.is_keystone else ""
        print(f"  [{r.tree:<10}] {r.name}{ks}")
    return 0


def main(argv: Optional[List[str]] = None) -> int:
    p = argparse.ArgumentParser(prog="lol-damage", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--patch", default=None, help="Data Dragon version (defaults to latest)")
    sub = p.add_subparsers(dest="cmd", required=True)

    sp_pred = sub.add_parser("predict", help="Predict damage")
    sp_pred.add_argument("--champion", required=True)
    sp_pred.add_argument("--level", type=int, default=11)
    sp_pred.add_argument("--items", nargs="*", default=[])
    sp_pred.add_argument("--skills", default="Q=5,W=5,E=5,R=3")
    sp_pred.add_argument("--rune-keystone", default=None)
    sp_pred.add_argument("--rune", nargs="*", default=[])
    sp_pred.add_argument("--shard-ad", type=float, default=0.0)
    sp_pred.add_argument("--shard-ap", type=float, default=0.0)
    sp_pred.add_argument("--shard-as", type=float, default=0.0)
    sp_pred.add_argument("--bonus-lethality", type=float, default=0.0)
    sp_pred.add_argument("--bonus-armor-pen-percent", type=float, default=0.0)
    sp_pred.add_argument("--bonus-flat-magic-pen", type=float, default=0.0)
    sp_pred.add_argument("--bonus-magic-pen-percent", type=float, default=0.0)
    sp_pred.add_argument("--crit-damage", type=float, default=1.75)
    sp_pred.add_argument("--target-name", default="Dummy")
    sp_pred.add_argument("--target-level", type=int, default=11)
    sp_pred.add_argument("--target-hp", type=float, default=2000.0)
    sp_pred.add_argument("--target-current-hp", type=float, default=-1.0)
    sp_pred.add_argument("--target-armor", type=float, default=60.0)
    sp_pred.add_argument("--target-mr", type=float, default=40.0)
    sp_pred.add_argument("--target-dr", type=float, default=1.0)
    sp_pred.add_argument("--auto", action="store_true", help="Show auto-attack damage")
    sp_pred.add_argument("--spell", nargs="*", default=[], help="Spell keys (Q/W/E/R)")
    sp_pred.add_argument("--multi", nargs=2, metavar=("N", "ACTION"), help='e.g. --multi 5 auto  or  --multi 3 Q')
    sp_pred.add_argument("--crit-pattern", choices=["expected", "always", "never"], default="expected")
    sp_pred.add_argument("--combo", default=None, help='Comma-separated tokens, e.g. Q,A,E,KEYSTONE,R')
    sp_pred.set_defaults(func=cmd_predict)

    sp_lc = sub.add_parser("list-champions", help="List champion ids")
    sp_lc.set_defaults(func=cmd_list_champions)

    sp_li = sub.add_parser("list-items", help="List items (optional substring filter)")
    sp_li.add_argument("query", nargs="?", default=None)
    sp_li.set_defaults(func=cmd_list_items)

    sp_lr = sub.add_parser("list-runes", help="List runes")
    sp_lr.set_defaults(func=cmd_list_runes)

    args = p.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
