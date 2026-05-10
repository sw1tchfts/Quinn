"""Ingest champion, item, and rune data from Riot's Data Dragon."""
from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Dict, List, Optional

import requests

from .models import Champion, ChampionStats, Item, Rune, Spell

DDRAGON_BASE = "https://ddragon.leagueoflegends.com"

_DEFAULT_CACHE = Path(os.environ.get("LOL_DAMAGE_CACHE", "~/.cache/lol_damage")).expanduser()


class DataDragon:
    """Fetches and caches champion/item/rune data from Data Dragon.

    Caches raw JSON on disk so subsequent runs are offline.
    """

    def __init__(
        self,
        version: Optional[str] = None,
        locale: str = "en_US",
        cache_dir: Optional[Path] = None,
        session: Optional[requests.Session] = None,
    ) -> None:
        self.locale = locale
        self.session = session or requests.Session()
        self.cache_dir = Path(cache_dir) if cache_dir else _DEFAULT_CACHE
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.version = version or self._latest_version()

    # ---------------- raw fetch helpers ----------------

    def _latest_version(self) -> str:
        data = self._fetch_json(f"{DDRAGON_BASE}/api/versions.json", "versions.json")
        return data[0]

    def _fetch_json(self, url: str, cache_name: str) -> dict:
        path = self.cache_dir / cache_name
        if path.exists():
            try:
                with path.open("r", encoding="utf-8") as fh:
                    return json.load(fh)
            except Exception:
                path.unlink(missing_ok=True)
        resp = self.session.get(url, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8") as fh:
            json.dump(data, fh)
        return data

    def _cdn(self, path: str) -> str:
        return f"{DDRAGON_BASE}/cdn/{self.version}/data/{self.locale}/{path}"

    # ---------------- champions ----------------

    def list_champions(self) -> List[str]:
        raw = self._fetch_json(self._cdn("champion.json"), f"{self.version}/champion.json")
        return sorted(raw["data"].keys())

    def champion(self, name: str) -> Champion:
        """Load a single champion (with full spell data)."""
        cid = self._resolve_champion_id(name)
        raw = self._fetch_json(
            self._cdn(f"champion/{cid}.json"),
            f"{self.version}/champion/{cid}.json",
        )
        cdata = raw["data"][cid]
        return _parse_champion(cdata)

    def _resolve_champion_id(self, name: str) -> str:
        raw = self._fetch_json(self._cdn("champion.json"), f"{self.version}/champion.json")
        data = raw["data"]
        if name in data:
            return name
        lower = name.lower()
        for cid, cdata in data.items():
            if cid.lower() == lower or cdata["name"].lower() == lower:
                return cid
        raise KeyError(f"Champion not found: {name}")

    # ---------------- items ----------------

    def items(self) -> Dict[int, Item]:
        raw = self._fetch_json(self._cdn("item.json"), f"{self.version}/item.json")
        return {int(iid): _parse_item(int(iid), idata) for iid, idata in raw["data"].items()}

    def item(self, name_or_id) -> Item:
        items = self.items()
        if isinstance(name_or_id, int) or (isinstance(name_or_id, str) and name_or_id.isdigit()):
            return items[int(name_or_id)]
        target = str(name_or_id).lower()
        for it in items.values():
            if it.name.lower() == target:
                return it
        # Substring fallback.
        candidates = [it for it in items.values() if target in it.name.lower()]
        if len(candidates) == 1:
            return candidates[0]
        if not candidates:
            raise KeyError(f"Item not found: {name_or_id}")
        raise KeyError(f"Ambiguous item '{name_or_id}': {[c.name for c in candidates[:5]]}")

    # ---------------- runes ----------------

    def runes(self) -> List[Rune]:
        raw = self._fetch_json(
            self._cdn("runesReforged.json"), f"{self.version}/runesReforged.json"
        )
        out: List[Rune] = []
        for tree in raw:
            tree_name = tree.get("name", "")
            for slot_idx, slot in enumerate(tree.get("slots", [])):
                for r in slot.get("runes", []):
                    out.append(
                        Rune(
                            id=int(r["id"]),
                            key=r["key"],
                            name=r["name"],
                            tree=tree_name,
                            is_keystone=(slot_idx == 0),
                            description=_strip_tags(r.get("longDesc", "")),
                        )
                    )
        return out

    def runes_tree(self) -> list:
        """Return the raw runesReforged.json tree (with icons, slots, etc.)."""
        return self._fetch_json(
            self._cdn("runesReforged.json"), f"{self.version}/runesReforged.json"
        )

    def rune(self, name: str) -> Rune:
        target = name.lower()
        for r in self.runes():
            if r.name.lower() == target or r.key.lower() == target:
                return r
        raise KeyError(f"Rune not found: {name}")


# ---------------- parsers ----------------

_TAG_RE = re.compile(r"<[^>]+>")


def _strip_tags(s: str) -> str:
    return _TAG_RE.sub("", s).strip()


def _parse_champion(cdata: dict) -> Champion:
    s = cdata["stats"]
    stats = ChampionStats(
        hp=s["hp"], hp_per_level=s["hpperlevel"],
        mp=s.get("mp", 0), mp_per_level=s.get("mpperlevel", 0),
        armor=s["armor"], armor_per_level=s["armorperlevel"],
        spellblock=s["spellblock"], spellblock_per_level=s["spellblockperlevel"],
        attackdamage=s["attackdamage"], attackdamage_per_level=s["attackdamageperlevel"],
        attackspeed=s["attackspeed"], attackspeed_per_level=s["attackspeedperlevel"],
        attackspeed_ratio=s.get("attackspeedoffset", 0) or s["attackspeed"],
        crit=s.get("crit", 0), crit_per_level=s.get("critperlevel", 0),
        movespeed=s.get("movespeed", 0),
        attackrange=s.get("attackrange", 0),
    )

    spells: Dict[str, Spell] = {}
    keys = ["Q", "W", "E", "R"]
    for i, sp in enumerate(cdata.get("spells", [])):
        key = keys[i] if i < len(keys) else f"S{i}"
        spells[key] = Spell(
            key=key,
            name=sp.get("name", key),
            description=_strip_tags(sp.get("description", "")),
            max_rank=sp.get("maxrank", 5),
            damages=_extract_damage_blocks(sp),
            cooldowns=sp.get("cooldown", []) or [],
        )
    if "passive" in cdata:
        p = cdata["passive"]
        spells["P"] = Spell(
            key="P",
            name=p.get("name", "Passive"),
            description=_strip_tags(p.get("description", "")),
            max_rank=1,
            damages=[],
        )
    return Champion(
        name=cdata["name"],
        id=cdata["id"],
        stats=stats,
        spells=spells,
    )


def _extract_damage_blocks(spell: dict) -> List[Dict]:
    """Best-effort extraction of damage from a spell's effect array.

    Data Dragon's spell tooltips don't reliably tag damage type or AD/AP ratios
    in a machine-readable form. We expose all ``effect`` arrays so callers can
    pick the relevant block; for true accuracy users should override per-spell.
    """
    effects = spell.get("effect") or []
    out: List[Dict] = []
    for idx, eff in enumerate(effects):
        if not eff:
            continue
        out.append({
            "effect_index": idx,
            "values_per_rank": list(eff),
            # Type/ratio left unspecified — caller layers on top.
            "type": "unknown",
        })
    return out


def _parse_item(iid: int, idata: dict) -> Item:
    stats = idata.get("stats", {})
    return Item(
        id=iid,
        name=idata.get("name", f"Item {iid}"),
        cost=idata.get("gold", {}).get("total", 0),
        ad=stats.get("FlatPhysicalDamageMod", 0.0),
        ap=stats.get("FlatMagicDamageMod", 0.0),
        hp=stats.get("FlatHPPoolMod", 0.0),
        mp=stats.get("FlatMPPoolMod", 0.0),
        armor=stats.get("FlatArmorMod", 0.0),
        mr=stats.get("FlatSpellBlockMod", 0.0),
        attack_speed=stats.get("PercentAttackSpeedMod", 0.0),
        crit_chance=stats.get("FlatCritChanceMod", 0.0),
        move_speed_flat=stats.get("FlatMovementSpeedMod", 0.0),
        move_speed_percent=stats.get("PercentMovementSpeedMod", 0.0),
        lifesteal=stats.get("PercentLifeStealMod", 0.0),
        tags=idata.get("tags", []) or [],
        description=_strip_tags(idata.get("description", "")),
    )
