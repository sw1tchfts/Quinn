"use strict";

const $ = (id) => document.getElementById(id);

async function loadCatalogs() {
  const [champs, items, runes] = await Promise.all([
    fetch("/api/champions").then((r) => r.json()),
    fetch("/api/items").then((r) => r.json()),
    fetch("/api/runes").then((r) => r.json()),
  ]);

  $("ddversion").textContent = champs.version || "?";

  const champList = $("champion-list");
  for (const c of champs.champions) {
    const o = document.createElement("option");
    o.value = c;
    champList.appendChild(o);
  }

  const itemRows = $("item-rows");
  const itemList = document.createElement("datalist");
  itemList.id = "item-options";
  for (const it of items.items) {
    const o = document.createElement("option");
    o.value = it.name;
    o.label = `${it.name} — ${it.cost}g`;
    itemList.appendChild(o);
  }
  document.body.appendChild(itemList);

  for (let i = 0; i < 6; i++) {
    const inp = document.createElement("input");
    inp.placeholder = `Item ${i + 1}`;
    inp.setAttribute("list", "item-options");
    inp.dataset.role = "item";
    itemRows.appendChild(inp);
  }

  const runeList = $("rune-list");
  for (const r of runes.runes) {
    if (!r.is_keystone) continue;
    const o = document.createElement("option");
    o.value = r.name;
    runeList.appendChild(o);
  }
}

function gatherPayload() {
  const items = Array.from(document.querySelectorAll('input[data-role="item"]'))
    .map((el) => el.value.trim())
    .filter(Boolean);

  const spells = $("spells").value.split(",").map((s) => s.trim()).filter(Boolean);
  const multiN = parseInt($("multi-n").value || "0", 10);
  const combo = $("combo").value.trim();

  return {
    champion: $("champion").value.trim() || "Garen",
    level: parseInt($("level").value, 10),
    items,
    skills: {
      Q: parseInt($("rank-q").value, 10),
      W: parseInt($("rank-w").value, 10),
      E: parseInt($("rank-e").value, 10),
      R: parseInt($("rank-r").value, 10),
    },
    rune_keystone: $("keystone").value.trim() || null,
    shards: {
      ad: parseFloat($("shard-ad").value || "0"),
      ap: parseFloat($("shard-ap").value || "0"),
      as: parseFloat($("shard-as").value || "0"),
    },
    bonus_lethality: parseFloat($("lethality").value || "0"),
    bonus_armor_pen_percent: parseFloat($("armor-pen-pct").value || "0"),
    bonus_flat_magic_pen: parseFloat($("flat-magic-pen").value || "0"),
    bonus_magic_pen_percent: parseFloat($("magic-pen-pct").value || "0"),
    crit_damage: parseFloat($("crit-damage").value || "1.75"),
    target: {
      name: $("target-name").value.trim() || "Dummy",
      level: parseInt($("target-level").value, 10),
      max_hp: parseFloat($("target-hp").value),
      current_hp: parseFloat($("target-current-hp").value),
      armor: parseFloat($("target-armor").value),
      magic_resist: parseFloat($("target-mr").value),
      damage_reduction: parseFloat($("target-dr").value || "1"),
    },
    actions: {
      auto: $("want-auto").checked,
      spells,
      multi: multiN > 0
        ? { n: multiN, action: $("multi-action").value.trim() || "auto", crit_pattern: $("multi-crit").value }
        : null,
      combo: combo || null,
    },
  };
}

function dtClass(t) { return `dt-${(t || "unknown").toLowerCase()}`; }

function renderHit(h) {
  return `<tr>
    <td>${h.label}</td>
    <td class="${dtClass(h.damage_type)}">${h.damage_type}</td>
    <td>${h.raw.toFixed(1)}</td>
    <td>${h.mitigated.toFixed(1)}</td>
    <td class="note">${h.notes || ""}</td>
  </tr>`;
}

function renderResult(data) {
  const out = [];
  const s = data.stats;

  out.push(`<h3>${data.champion} (lvl ${data.level}) vs ${data.target.name}</h3>`);
  out.push(`<div class="kv">
    <div class="k">AD</div><div>${s.total_ad} (base ${s.base_ad} + bonus ${s.bonus_ad})</div>
    <div class="k">AP</div><div>${s.ap}</div>
    <div class="k">Attack speed</div><div>${s.attack_speed}</div>
    <div class="k">Crit</div><div>${(s.crit_chance * 100).toFixed(0)}% @ ${s.crit_damage}x</div>
    <div class="k">Lethality / %ArPen</div><div>${s.lethality} / ${(s.armor_pen_percent * 100).toFixed(0)}%</div>
    <div class="k">MagicPen flat / %</div><div>${s.flat_magic_pen} / ${(s.magic_pen_percent * 100).toFixed(0)}%</div>
    <div class="k">HP / Armor / MR</div><div>${s.max_hp} / ${s.armor} / ${s.magic_resist}</div>
  </div>`);

  if (data.auto) {
    out.push("<h3>Auto attack</h3><table><thead><tr><th>Variant</th><th>Type</th><th>Raw</th><th>Mitigated</th><th></th></tr></thead><tbody>");
    out.push(renderHit(data.auto.expected));
    out.push(renderHit(data.auto.crit));
    out.push(renderHit(data.auto.non_crit));
    out.push("</tbody></table>");
  }

  if (data.spells && data.spells.length) {
    out.push("<h3>Spell single-casts</h3><table><thead><tr><th>Spell</th><th>Type</th><th>Raw</th><th>Mitigated</th><th>Note</th></tr></thead><tbody>");
    for (const h of data.spells) out.push(renderHit(h));
    out.push("</tbody></table>");
  }

  if (data.multi) {
    out.push(`<h3>Multi-hit (total ${data.multi.total})${data.multi.killed ? ' <span class="killed">KILL</span>' : ""}</h3>`);
    out.push("<table><thead><tr><th>Hit</th><th>Type</th><th>Raw</th><th>Mitigated</th><th></th></tr></thead><tbody>");
    for (const h of data.multi.hits) out.push(renderHit(h));
    out.push(`</tbody></table><p class="note">Target HP remaining: ${data.multi.target_hp_remaining}</p>`);
  }

  if (data.combo) {
    out.push(`<h3>Combo (total ${data.combo.total})${data.combo.killed ? ' <span class="killed">KILL</span>' : ""}</h3>`);
    out.push("<table><thead><tr><th>Hit</th><th>Type</th><th>Raw</th><th>Mitigated</th><th></th></tr></thead><tbody>");
    for (const h of data.combo.hits) out.push(renderHit(h));
    out.push(`</tbody></table><p class="note">Target HP remaining: ${data.combo.target_hp_remaining}</p>`);
  }

  $("results").innerHTML = out.join("");
}

async function run() {
  const payload = gatherPayload();
  $("results").innerHTML = "<em>Computing…</em>";
  try {
    const resp = await fetch("/api/predict", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    const data = await resp.json();
    if (data.error) {
      $("results").innerHTML = `<div class="error">${data.type || "Error"}: ${data.error}</div>`;
      return;
    }
    renderResult(data);
  } catch (err) {
    $("results").innerHTML = `<div class="error">${err.message}</div>`;
  }
}

document.addEventListener("DOMContentLoaded", () => {
  loadCatalogs().catch((e) => {
    $("ddversion").textContent = "(failed to load)";
    console.error(e);
  });
  $("run").addEventListener("click", run);
});
