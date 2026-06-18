# CLAUDE.md — LoL Damage Predictor

A Python application that predicts how much damage a League of Legends
champion deals against a target, given their level, items, runes, and
abilities. Data is sourced from Riot's Data Dragon CDN. There is a CLI, a
Python library, and a local web UI.

## Repo at a glance

```
lol_damage/
  __init__.py          public surface (Champion, Item, Build, Target, DamagePredictor, DataDragon)
  models.py            dataclasses for Champion / Item / Rune / Build / Target / RunePage / StatShard
  data.py              DataDragon — fetches + caches champions/items/runes JSON
  damage.py            core math: armor/MR mitigation, lethality, %pen, crit, true damage
  runes.py             rune effects — proc damage (Electrocute, Comet, …) + amps (Conqueror, PtA, …)
  spell_overrides.py   hand-curated spell damage formulas keyed by (champion_id, key)
  predictor.py         DamagePredictor — single hits, multi-hit, combo (with HP tracking + per-hit explanations)
  server.py            stdlib HTTP server: /api/champions, /api/items, /api/runes, /api/predict
  cli.py               `lol-damage` CLI entry point
  web/                 frontend: index.html, style.css, app.js
tests/                 offline pytest suite (no network)
start.bat / start.sh   launchers: install requests if missing, start server, open browser
pyproject.toml         editable install + script entry point
```

## How to run

```bash
pip install -e . pytest      # one-time
pytest -q                    # run tests (offline)
python -m lol_damage.server --open  # web UI on http://127.0.0.1:8765/
lol-damage predict --champion Garen --level 11 --auto  # CLI
```

The web UI is the primary interface. Double-click `start.bat` (Windows) or
`./start.sh` (Unix) for a one-click launch.

## Data source

All game data comes from **Riot's [Data Dragon](https://developer.riotgames.com/docs/lol#data-dragon) CDN** — no API key required. The `DataDragon`
class caches every JSON it fetches under `~/.cache/lol_damage/{version}/...`,
so subsequent runs are fully offline. Pin a patch with `DataDragon(version="14.20.1")` or `--patch 14.20.1`.

What Data Dragon **does** provide: base champion stats, per-level scaling,
spell tooltip text, item flat stats (AD, AP, HP, armor, MR, AS, crit,
lifesteal, MS), rune list with icons.

What Data Dragon **does not** provide:
- Damage type or AD/AP ratios for spells (buried in tooltip strings).
  → modeled in `spell_overrides.py` (hand-curated, ~10 champions covered).
- Item penetration stats (lethality, %armor pen, magic pen).
  → live in passives; pass via `Build.bonus_*` or CLI flags.
- Rune effect formulas.
  → modeled in `runes.py` against published wiki numbers.

## Damage flow (read this when changing math)

1. **Effective stats** — `DamagePredictor.combat_stats()` computes a
   `CombatStats` from `Build`: champion stats at level + sum of item flats +
   rune shards/stat-runes. `%armor_pen` and `%magic_pen` from items compound
   *multiplicatively* (`1 - product(1 - p_i)`), not additively.

2. **Per-hit raw damage** — `auto_attack` and `spell` produce a `HitResult`
   with `raw`, `mitigated`, and an `explanation: List[str]` (each line is a
   step in the math). The frontend renders `explanation` line-by-line under a
   collapsible chevron.

3. **Mitigation** — applied in `damage.apply_damage()`. Order:
   - `%pen` reduces armor first
   - `lethality → flat_pen` via `lethality * (0.6 + 0.4 * level / 18)`
   - flat pen reduces remaining armor (cannot push below 0)
   - resist multiplier: `100/(100+R)` if `R >= 0`, else `2 - 100/(100-R)`
   - amp multipliers: `physical_amp * versus_amp` (or magic/true equivalents)

4. **Combos** — `DamagePredictor.combo(["Q", "A", "KEYSTONE", "R"], target)`
   walks the sequence, *clones the target*, and decrements HP between hits
   so missing-HP scalings update mid-combo. Tokens:
   - `Q W E R` — single spell cast
   - `A` / `A!` / `A.` — auto (expected / forced crit / forced non-crit)
   - `KEYSTONE` — proc the build's keystone

## Server / API

`lol_damage.server` runs a `ThreadingHTTPServer` on the stdlib (no Flask).

| Endpoint           | Returns                                                    |
|--------------------|------------------------------------------------------------|
| `GET /`            | `web/index.html`                                           |
| `GET /static/<f>`  | files under `web/`                                         |
| `GET /api/champions` | `{version, champions: [{id, name, image, tags, ...}]}`     |
| `GET /api/items`     | `{items: [{id, name, image, cost, ad, ap, ..., tags}]}`    |
| `GET /api/runes`     | `{trees: [{id, name, icon, slots: [{runes: [...]}]}], shards}` |
| `POST /api/predict`  | `{stats, target, combo_input, combo_variants: {no_crit, expected_crit, max_crit}}` |

The predict response no longer contains separate `auto`/`spells`/`multi`
blocks — everything funnels through three combo variants.

## Frontend

`web/index.html` + `style.css` + `app.js` (vanilla JS, no framework).
Layout:
- **Champion** — search + grid of all 172 portraits (clicking selects).
- **Target** — HP/armor/MR/etc.
- **Items** — six clickable slots; active slot highlighted; click an icon
  in the catalog grid to fill the active slot, then advances.
- **Runes** — in-game-style picker: primary tree tabs → keystone row → 3
  minor slots; secondary tree tabs (excluding primary) → 2 picks across 3
  slot rows; 3 stat-shard rows. Adaptive Force shards auto-resolve to AD or
  AP based on whether the equipped items lean AD or AP.
- **Action sequence** — single text input of comma-separated tokens.
- **Results** — three collapsible variant cards (no crit / predicted /
  max crit), each containing collapsible per-hit rows with the step-by-step
  math.

Skill ranks auto-distribute when level (or the max-order selector) changes:
R at 6/11/16, then 1-of-each in priority order, then max in priority order.

## Conventions / gotchas

- **No new runtime deps.** `requests` is the only one. Server uses stdlib.
- **Editing existing files > new files.** Especially: don't add a new ORM,
  framework, or build step.
- **Spell formulas are curated, not parsed.** Add new champions by calling
  `lol_damage.spell_overrides.register("ChampionId", "Q", {...})`. See
  `spell_overrides.py` for the schema.
- **Champion id vs name.** Data Dragon uses ids like `MissFortune`,
  `LeeSin`, `MonkeyKing` (Wukong). The `data.DataDragon` resolves names
  case-insensitively, but the **registry key in spell_overrides must match
  the id**.
- **Lethality / %ArPen are not in Data Dragon.** Items that grant them in
  the game (e.g. Eclipse, Black Cleaver passive, Serylda's) appear with
  zero penetration stats. Either expose a per-item override here or supply
  them as `Build.bonus_*` in the request.
- **Rune effect coverage is partial.** `runes.py` covers the keystones that
  do discrete damage and a few amp keystones. Conditional effects (e.g.
  Coup de Grace, Last Stand) are modeled as constant amps; the caller must
  decide whether the condition applies.
- **`HitResult.explanation`** is a list of human-readable strings shown
  verbatim in the UI. When extending math, append explanation lines so
  numbers stay traceable.

## Tests

```bash
pytest -q
```

22 offline tests covering damage math, predictor logic, and parser logic
against fabricated fixtures. No network is hit. When changing formulas,
update `tests/test_damage.py` or `tests/test_predictor.py` first.

## Branch / PR

- Active branch: **`claude/lol-damage-predictor-WGpwA`**
- Draft PR: **sw1tchfts/quinn#1**

When asked to commit, push to that branch (the harness enforces it).

## See also

- `ROADMAP.md` — the planned feedback loop (observation lab + regression
  suite) and the list of known modeling gaps to close.
