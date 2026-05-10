# LoL Damage Predictor

A Python application that ingests champion, item, and rune data from Riot's
[Data Dragon](https://developer.riotgames.com/docs/lol#data-dragon) and predicts
how much damage a champion will deal — for a single hit, a series of hits, or a
full combo — given their level, items, runes, and the target's resistances.

## Install

```bash
pip install -e .
```

Python 3.9+. The only runtime dependency is `requests`. Data Dragon JSON is
cached under `~/.cache/lol_damage/` so subsequent runs work offline.

## CLI

List things:

```bash
lol-damage list-champions
lol-damage list-items "Infinity"
lol-damage list-runes
```

Predict damage for a Garen build:

```bash
lol-damage predict \
  --champion Garen --level 11 \
  --items "Stridebreaker" "Black Cleaver" \
  --skills Q=5,E=5,R=2 \
  --rune-keystone "Conqueror" \
  --shard-ad 9 \
  --target-hp 2400 --target-armor 120 --target-mr 50 \
  --auto --spell Q E R \
  --combo Q,E,A,KEYSTONE,R
```

The `--combo` token language:

| Token       | Meaning                                |
|-------------|----------------------------------------|
| `Q W E R`   | Single cast of that spell              |
| `A`         | Auto attack (uses crit chance)         |
| `A!`        | Forced-crit auto                       |
| `A.`        | Forced non-crit auto                   |
| `KEYSTONE`  | Proc the keystone (Electrocute, etc.)  |

HP is tracked between hits, so missing-HP scalings (Lee Sin Q, Garen R, …)
update mid-combo.

## Library

```python
from lol_damage import DataDragon, Build, RunePage, Target, DamagePredictor

dd = DataDragon()
champ = dd.champion("Ahri")
items = [dd.item("Luden's Companion"), dd.item("Shadowflame")]
runes = RunePage(keystone=dd.rune("Electrocute"))

build = Build(
    champion=champ,
    level=11,
    items=items,
    runes=runes,
    skill_ranks={"Q": 5, "W": 3, "E": 5, "R": 2},
)

target = Target(name="Lux", level=11, max_hp=2000, armor=60, magic_resist=40)
predictor = DamagePredictor(build)

print(predictor.auto_attack(target).mitigated)
print(predictor.spell("Q", target).mitigated)
print(predictor.combo(["Q", "W", "E", "KEYSTONE", "R"], target).summary())
```

## What's modelled

- **Champion stats per level** using Riot's curve
  `base + growth * n * (0.7025 + 0.0175 * n)`.
- **Items**: every flat stat exposed by Data Dragon (AD, AP, HP, armor, MR,
  attack speed, crit chance, lifesteal, movespeed). Penetration values
  (lethality, %armor pen, magic pen) are not in Data Dragon — pass them as
  `Build.bonus_*` or via the CLI flags.
- **Damage formulas**: armor/MR mitigation (positive and negative resists),
  lethality -> flat-pen scaling with level, %pen applied before flat pen,
  per-source amp multipliers, true damage that ignores resists.
- **Auto attacks**: expected damage averaged over crit chance, plus forced
  crit / forced non-crit options.
- **Spells**: damage formulas for a curated set of champions in
  `lol_damage/spell_overrides.py`. Add your own with
  `spell_overrides.register(champion_id, "Q", {...})`.
- **Runes**: stat shards, common adaptive-force runes, and discrete proc
  damage for Electrocute, Dark Harvest, Comet, Aery, Grasp, plus amp-style
  effects for Conqueror, Press the Attack, Coup de Grace, etc.
- **Combos**: HP is tracked between hits, so missing-HP scalings update.

## Limitations

Data Dragon does not publish damage type or AD/AP ratios in a fully
machine-readable form. Spells without a registered formula in
`spell_overrides.py` return zero damage with a `notes` field flagging the gap.
Pull requests adding more champions are welcome.

## Tests

```bash
pytest -q
```

The test suite is offline; it verifies the math and the JSON parsers using
hand-built fixtures.
