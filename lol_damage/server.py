"""HTTP server that exposes the damage predictor as a JSON API + static UI.

Run with::

    python -m lol_damage.server [--host HOST] [--port PORT] [--patch VERSION]

The server uses only Python's standard library so no extra dependency is
required. The static frontend lives in ``lol_damage/web/``.
"""
from __future__ import annotations

import argparse
import json
import sys
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

from .data import DataDragon
from .models import Build, Item, RunePage, StatShard, Target
from .predictor import DamagePredictor

WEB_ROOT = Path(__file__).parent / "web"


class _State:
    """Shared, lazily-loaded Data Dragon singleton."""

    def __init__(self, version: Optional[str]):
        self.version = version
        self._lock = threading.Lock()
        self._dd: Optional[DataDragon] = None

    def dd(self) -> DataDragon:
        with self._lock:
            if self._dd is None:
                self._dd = DataDragon(version=self.version)
            return self._dd


def _make_handler(state: _State):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, fmt: str, *args: Any) -> None:  # quieter logs
            sys.stderr.write(f"[server] {self.address_string()} - {fmt % args}\n")

        # ---------- helpers ----------

        def _send_json(self, payload: Any, status: int = 200) -> None:
            body = json.dumps(payload).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(body)

        def _send_static(self, rel: str) -> None:
            # Resolve safely under WEB_ROOT.
            target = (WEB_ROOT / rel).resolve()
            if WEB_ROOT.resolve() not in target.parents and target != WEB_ROOT.resolve():
                self.send_error(403, "Forbidden")
                return
            if not target.exists() or not target.is_file():
                self.send_error(404, "Not Found")
                return
            ctype = {
                ".html": "text/html; charset=utf-8",
                ".js": "application/javascript; charset=utf-8",
                ".css": "text/css; charset=utf-8",
                ".json": "application/json; charset=utf-8",
                ".svg": "image/svg+xml",
            }.get(target.suffix, "application/octet-stream")
            data = target.read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def _read_json(self) -> Dict[str, Any]:
            length = int(self.headers.get("Content-Length", "0"))
            raw = self.rfile.read(length) if length else b"{}"
            return json.loads(raw or b"{}")

        # ---------- routes ----------

        def do_GET(self) -> None:  # noqa: N802
            path = urlparse(self.path).path
            if path == "/" or path == "/index.html":
                self._send_static("index.html")
                return
            if path.startswith("/static/"):
                self._send_static(path[len("/static/"):])
                return
            if path == "/api/champions":
                dd = state.dd()
                self._send_json({"version": dd.version, "champions": dd.list_champions()})
                return
            if path == "/api/items":
                dd = state.dd()
                items = [
                    {
                        "id": it.id, "name": it.name, "cost": it.cost,
                        "ad": it.ad, "ap": it.ap, "hp": it.hp, "armor": it.armor, "mr": it.mr,
                        "attack_speed": it.attack_speed, "crit_chance": it.crit_chance,
                        "tags": it.tags,
                    }
                    for it in dd.items().values()
                    if it.cost > 0  # filter out non-purchaseable junk
                ]
                items.sort(key=lambda x: x["name"])
                self._send_json({"items": items})
                return
            if path == "/api/runes":
                dd = state.dd()
                runes = [
                    {"id": r.id, "key": r.key, "name": r.name, "tree": r.tree, "is_keystone": r.is_keystone}
                    for r in dd.runes()
                ]
                self._send_json({"runes": runes})
                return
            self.send_error(404, "Not Found")

        def do_POST(self) -> None:  # noqa: N802
            path = urlparse(self.path).path
            if path != "/api/predict":
                self.send_error(404, "Not Found")
                return
            try:
                payload = self._read_json()
                result = _run_prediction(state.dd(), payload)
                self._send_json(result)
            except KeyError as exc:
                self._send_json({"error": f"Not found: {exc}"}, status=404)
            except Exception as exc:  # surface errors clearly to the UI
                self._send_json({"error": str(exc), "type": exc.__class__.__name__}, status=400)

    return Handler


def _run_prediction(dd: DataDragon, payload: Dict[str, Any]) -> Dict[str, Any]:
    champ = dd.champion(payload["champion"])

    items: List[Item] = []
    for name in payload.get("items", []):
        if not name:
            continue
        items.append(dd.item(name))

    page = RunePage()
    if payload.get("rune_keystone"):
        page.keystone = dd.rune(payload["rune_keystone"])
    for rname in payload.get("runes", []):
        if rname:
            page.primary.append(dd.rune(rname))
    shards = payload.get("shards") or {}
    if shards.get("ad"):
        page.shards.append(StatShard(name="Adaptive (AD)", ad=float(shards["ad"])))
    if shards.get("ap"):
        page.shards.append(StatShard(name="Adaptive (AP)", ap=float(shards["ap"])))
    if shards.get("as"):
        page.shards.append(StatShard(name="Attack Speed", attack_speed=float(shards["as"])))

    skills = payload.get("skills") or {"Q": 5, "W": 5, "E": 5, "R": 3}
    skills = {k.upper(): int(v) for k, v in skills.items()}

    build = Build(
        champion=champ,
        level=int(payload.get("level", 11)),
        items=items,
        runes=page,
        skill_ranks=skills,
        bonus_lethality=float(payload.get("bonus_lethality", 0) or 0),
        bonus_armor_pen_percent=float(payload.get("bonus_armor_pen_percent", 0) or 0),
        bonus_flat_magic_pen=float(payload.get("bonus_flat_magic_pen", 0) or 0),
        bonus_magic_pen_percent=float(payload.get("bonus_magic_pen_percent", 0) or 0),
        crit_damage=float(payload.get("crit_damage", 1.75) or 1.75),
    )

    t = payload.get("target") or {}
    target = Target(
        name=t.get("name", "Dummy"),
        level=int(t.get("level", 11)),
        max_hp=float(t.get("max_hp", 2000)),
        current_hp=float(t["current_hp"]) if t.get("current_hp") not in (None, "") else None,
        armor=float(t.get("armor", 60)),
        magic_resist=float(t.get("magic_resist", 40)),
        damage_reduction=float(t.get("damage_reduction", 1.0) or 1.0),
    )

    p = DamagePredictor(build)
    cs = p.combat_stats()

    out: Dict[str, Any] = {
        "champion": champ.name,
        "level": build.level,
        "stats": {
            "base_ad": round(cs.base_ad, 1),
            "bonus_ad": round(cs.bonus_ad, 1),
            "total_ad": round(cs.total_ad, 1),
            "ap": round(cs.ap, 1),
            "attack_speed": round(cs.attack_speed, 2),
            "crit_chance": round(cs.crit_chance, 3),
            "crit_damage": cs.crit_damage,
            "lethality": round(cs.lethality, 1),
            "armor_pen_percent": round(cs.armor_pen_percent, 3),
            "flat_magic_pen": round(cs.flat_magic_pen, 1),
            "magic_pen_percent": round(cs.magic_pen_percent, 3),
            "max_hp": round(cs.max_hp, 0),
            "armor": round(cs.armor, 1),
            "magic_resist": round(cs.magic_resist, 1),
        },
        "target": {
            "name": target.name,
            "level": target.level,
            "max_hp": target.max_hp,
            "current_hp": target.current_hp,
            "armor": target.armor,
            "magic_resist": target.magic_resist,
        },
    }

    actions = payload.get("actions") or {}

    if actions.get("auto"):
        out["auto"] = {
            "expected": _hit_to_dict(p.auto_attack(target, crit=None)),
            "crit": _hit_to_dict(p.auto_attack(target, crit=True)),
            "non_crit": _hit_to_dict(p.auto_attack(target, crit=False)),
        }

    spells_req = actions.get("spells") or []
    if spells_req:
        out["spells"] = [_hit_to_dict(p.spell(s, target)) for s in spells_req]

    multi = actions.get("multi")
    if multi:
        n = int(multi.get("n", 1))
        action = multi.get("action", "auto")
        if action.upper() in {"Q", "W", "E", "R"}:
            r = p.multi_hit(target, n=n, action="spell", spell_key=action.upper())
        else:
            r = p.multi_hit(target, n=n, action="auto", crit_pattern=multi.get("crit_pattern", "expected"))
        out["multi"] = _combo_to_dict(r)

    combo = actions.get("combo")
    if combo:
        if isinstance(combo, str):
            combo = [s.strip() for s in combo.split(",") if s.strip()]
        out["combo"] = _combo_to_dict(p.combo(combo, target))

    return out


def _hit_to_dict(h) -> Dict[str, Any]:
    return {
        "label": h.label,
        "damage_type": h.damage_type,
        "raw": round(h.raw, 1),
        "mitigated": round(h.mitigated, 1),
        "notes": h.notes,
    }


def _combo_to_dict(r) -> Dict[str, Any]:
    return {
        "hits": [_hit_to_dict(h) for h in r.hits],
        "total": round(r.total, 1),
        "target_hp_remaining": round(r.target_hp_remaining, 1),
        "killed": r.killed,
    }


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="LoL damage predictor web server")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--patch", default=None, help="Data Dragon version")
    parser.add_argument("--open", action="store_true", help="Open browser when ready")
    args = parser.parse_args(argv)

    state = _State(args.patch)
    server = ThreadingHTTPServer((args.host, args.port), _make_handler(state))
    url = f"http://{args.host}:{args.port}/"
    print(f"[server] LoL damage predictor running at {url}")
    print("[server] Press Ctrl+C to stop.")

    if args.open:
        threading.Timer(0.6, lambda: webbrowser.open(url)).start()

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n[server] shutting down")
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
