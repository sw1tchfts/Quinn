# ROADMAP

What's next on the LoL Damage Predictor, in the order I think makes the
most sense to attack. Read `CLAUDE.md` first for architecture context.

## 1. Calibration feedback loop (next session — agreed direction)

The predictor will never be 100% accurate up front, because every champion
has unique passives, item passives, and conditional rune effects. Closing
the gap requires *observing actual in-game damage and locking it in as a
test*. Plan:

### Layer 1 — Observation lab in the UI

- Next to each predicted hit (and each variant total), an `Actual observed`
  number input + Save button.
- Saving snapshots `{build, target, action, predicted, actual, ts, notes}`
  to a local JSON file (proposed path: `~/.local/share/lol_damage/observations.json`,
  with an env override).
- The hit row gains a delta column (`predicted − actual`, %) the moment a
  value is filled in.
- New backend endpoint: `POST /api/observations` (append) and
  `GET /api/observations` (list).

### Layer 2 — Regression suite from the same file

- A new pytest file (e.g. `tests/test_observations.py`) that loads the JSON
  and asserts each entry's predicted value is within tolerance of the
  recorded actual (e.g. ±2%).
- The suite runs offline. Failing assertions name the scenario so it's
  obvious which one drifted.
- New observations are added by clicking Save in the UI; commits to that
  JSON file are how the corpus grows.

### Layer 3 — Diagnostic diff per champion

- A "Diff against saved scenarios" button that, for the active champion,
  re-runs every saved observation and surfaces which scenarios pass/fail
  and by how much. Lets you spot patterns:
  - all off by a constant → flat passive missing
  - off by a fraction that grows with target HP → missing %max-HP scaling
  - off only when a specific item is equipped → that item's passive needs modeling

This is the headline next thing to build.

## 2. Known modeling gaps to close

Captured here so they don't get lost. Each one is a candidate for
`spell_overrides.py`, `runes.py`, or a new "item passives" module.

### Champion passives currently un-modeled

- **Quinn — Harrier.** Marks targets every few seconds; next auto deals
  bonus physical damage scaling with level + AD. The user observed 96
  damage in-game vs 93.7 predicted at level 6; Harrier is the most likely
  cause.
- (Add more here as they're encountered.)

### Item passives currently un-modeled

Many mythic/legendary items have a damage-relevant passive that Data
Dragon does not expose as a stat:

- **Black Cleaver** — armor reduction stacks (up to 30%); should feed
  into `bonus_armor_pen_percent` over time.
- **Eclipse** — bonus AD on consecutive hits.
- **Serylda's Grudge** — %armor pen scaling with lethality.
- **Liandry's Torment / Demonic Embrace** — burn DoT scaling with target HP.
- **Stridebreaker, Goredrinker** — active damage components.
- **Infinity Edge / Navori Quickblades** — increases crit damage from
  175% to 210%; we should auto-detect this and bump `crit_damage`.

A small registry keyed by item id (similar to `spell_overrides`) would
let the predictor add these effects to either flat damage, amps, or
penetration stats.

### Runes currently un-modeled or approximated

- **Conqueror** — adaptive force ramps with stacks (up to 12) and converts
  some damage to true at full stacks. Currently treated as flat-stat only.
- **Press the Attack** — bonus damage on third hit + 8% taken-damage amp on
  target. The amp is modeled; the third-hit bonus damage is not.
- **Cut Down / Last Stand / Coup de Grace** — currently constant amps;
  should be conditional on target/source HP%.
- **Dark Harvest** — soul stacks; currently fires only the base proc.

### Stat shards

`AbilityHaste`, `MoveSpeed`, `Health`, `HealthScaling`, `Tenacity` are
displayed in the UI but don't affect outgoing damage so they're ignored
when resolving the shard payload. If the predictor ever models DoT
durations or HP-scaling effects (Liandry's, Demonic), `HealthScaling`
becomes relevant.

## 3. UX polish (lower priority, after #1)

- **Auto-bump `crit_damage` to 2.10 if Infinity Edge or Navori is equipped.**
  Right now the field is a free-form input.
- **Pin selected champion to the top** of the picker grid so they stay
  visible after scrolling.
- **Item builds presets** — "save this build", load it back later.
- **Side-by-side build comparison** — predict A vs B against the same
  target.
- **Permalinks** — encode the full build/target/sequence in the URL hash.

## 4. Bigger ideas (consider after #1 + #2)

- **Live Client Data integration.** While in-game, Riot exposes a local
  HTTPS API at `https://127.0.0.1:2999/liveclientdata/...` with player
  stats, items, and runes (no damage events though). Could pre-fill the
  build for the active champion.
- **Probabilistic damage distribution** — instead of just `expected`,
  return a distribution over crit outcomes for a multi-hit sequence.
- **Replay log scraping** — investigate whether League's replay system
  exposes damage events in any form. Probably no, but worth checking.

## Working agreement reminders

- Develop on branch `claude/lol-damage-predictor-WGpwA`.
- No new runtime dependencies (requests only).
- Update `tests/` first when changing math.
- New champion spells go in `spell_overrides.py`, not the parser.
- Append to `HitResult.explanation` so the UI breakdown stays accurate.
