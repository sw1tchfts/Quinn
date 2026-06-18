"use strict";

const $ = (id) => document.getElementById(id);

// Client state.
const state = {
  version: null,
  champions: [],         // [{id, name, image, ...}]
  items: [],             // [{id, name, image, cost, ad, ap, tags, ...}]
  trees: [],             // [{id, key, name, icon, slots: [{runes: [...]}]}]
  shards: { rows: [] },

  selectedChampion: null,    // champion id (string)
  itemSlots: [null, null, null, null, null, null],  // chosen item objects
  activeItemSlot: 0,
  itemFilter: { tag: null, search: "" },

  rune: {
    primaryTreeId: null,
    primary: { keystone: null, slots: [null, null, null] }, // rune ids
    secondaryTreeId: null,
    secondary: { picks: [null, null, null] }, // rune id per row, max 2 non-null
    shards: [null, null, null], // shard key per row
  },
};

// ----------------------- bootstrap -----------------------

async function loadCatalogs() {
  const [champRes, itemRes, runeRes] = await Promise.all([
    fetch("/api/champions").then((r) => r.json()),
    fetch("/api/items").then((r) => r.json()),
    fetch("/api/runes").then((r) => r.json()),
  ]);
  state.version = champRes.version;
  state.champions = champRes.champions;
  state.items = itemRes.items;
  state.trees = runeRes.trees;
  state.shards = runeRes.shards;
  $("ddversion").textContent = state.version || "?";
  renderChampionGrid();
  renderItemSlots();
  renderItemTagFilters();
  renderItemGrid();
  renderRuneTrees();
  renderShards();
}

// ----------------------- champions -----------------------

function renderChampionGrid() {
  const grid = $("champ-grid");
  grid.innerHTML = "";
  const q = ($("champ-search").value || "").toLowerCase();
  for (const c of state.champions) {
    if (q && !c.name.toLowerCase().includes(q) && !c.id.toLowerCase().includes(q)) continue;
    const img = document.createElement("img");
    img.src = c.image;
    img.alt = c.name;
    img.title = c.name;
    img.loading = "lazy";
    if (c.id === state.selectedChampion) img.classList.add("selected");
    img.addEventListener("click", () => selectChampion(c.id));
    grid.appendChild(img);
  }
}

function selectChampion(id) {
  state.selectedChampion = id;
  const c = state.champions.find((x) => x.id === id);
  if (!c) return;
  $("champ-portrait").src = c.image;
  $("champ-name").textContent = c.name;
  $("champ-title").textContent = c.title || "";
  renderChampionGrid();
}

// ----------------------- items -----------------------

function renderItemSlots() {
  const slots = $("item-slots");
  slots.innerHTML = "";
  for (let i = 0; i < 6; i++) {
    const slot = document.createElement("div");
    slot.className = "item-slot" + (i === state.activeItemSlot ? " active" : "");
    const it = state.itemSlots[i];
    if (it) {
      const img = document.createElement("img");
      img.src = it.image;
      img.alt = it.name;
      img.title = `${it.name} (${it.cost}g)`;
      slot.appendChild(img);
      const x = document.createElement("div");
      x.className = "clear-btn";
      x.textContent = "×";
      x.title = "Clear";
      x.addEventListener("click", (e) => { e.stopPropagation(); state.itemSlots[i] = null; renderItemSlots(); });
      slot.appendChild(x);
    } else {
      const n = document.createElement("div");
      n.className = "slot-num";
      n.textContent = `slot ${i + 1}`;
      slot.appendChild(n);
    }
    slot.addEventListener("click", () => { state.activeItemSlot = i; renderItemSlots(); });
    slots.appendChild(slot);
  }
}

function renderItemTagFilters() {
  const all = new Set();
  for (const it of state.items) for (const t of it.tags || []) all.add(t);
  // Pick a few damage-relevant tags.
  const wanted = ["Damage", "AttackSpeed", "CriticalStrike", "ArmorPenetration", "MagicPenetration",
                  "SpellDamage", "AbilityHaste", "Health", "Armor", "SpellBlock", "LifeSteal", "OnHit"];
  const tags = wanted.filter((t) => all.has(t));
  const row = $("item-tags");
  row.innerHTML = "";
  const mk = (label, value) => {
    const b = document.createElement("button");
    b.textContent = label;
    if (state.itemFilter.tag === value) b.classList.add("active");
    b.addEventListener("click", () => { state.itemFilter.tag = state.itemFilter.tag === value ? null : value; renderItemTagFilters(); renderItemGrid(); });
    return b;
  };
  row.appendChild(mk("All", null));
  for (const t of tags) row.appendChild(mk(t, t));
}

function renderItemGrid() {
  const grid = $("item-grid");
  grid.innerHTML = "";
  const q = ($("item-search").value || "").toLowerCase();
  const tag = state.itemFilter.tag;
  for (const it of state.items) {
    if (tag && !(it.tags || []).includes(tag)) continue;
    if (q && !it.name.toLowerCase().includes(q)) continue;
    const img = document.createElement("img");
    img.src = it.image;
    img.alt = it.name;
    img.title = `${it.name} — ${it.cost}g\n${[`AD ${it.ad}`, `AP ${it.ap}`, `HP ${it.hp}`, `Armor ${it.armor}`, `MR ${it.mr}`, `AS ${it.attack_speed}`].filter(s => !s.endsWith(" 0")).join(" / ")}`;
    img.loading = "lazy";
    img.addEventListener("click", () => {
      state.itemSlots[state.activeItemSlot] = it;
      state.activeItemSlot = Math.min(state.activeItemSlot + 1, 5);
      renderItemSlots();
    });
    grid.appendChild(img);
  }
}

// ----------------------- runes -----------------------

function renderRuneTrees() {
  // Default: pick first tree as primary, second as secondary.
  if (state.rune.primaryTreeId == null && state.trees.length > 0) {
    state.rune.primaryTreeId = state.trees[0].id;
  }
  if (state.rune.secondaryTreeId == null && state.trees.length > 1) {
    state.rune.secondaryTreeId = state.trees[1].id;
  }

  const onPrimary = (id) => {
    state.rune.primaryTreeId = id;
    state.rune.primary = { keystone: null, slots: [null, null, null] };
    if (id === state.rune.secondaryTreeId) {
      const fallback = state.trees.find((t) => t.id !== id);
      state.rune.secondaryTreeId = fallback ? fallback.id : null;
      state.rune.secondary = { picks: [null, null, null] };
    }
    renderTreeTabs("primary-tabs", state.rune.primaryTreeId, onPrimary);
    renderTreeTabs("secondary-tabs", state.rune.secondaryTreeId, onSecondary, state.rune.primaryTreeId);
    renderPrimarySlots();
    renderSecondarySlots();
    renderRuneSummary();
  };
  const onSecondary = (id) => {
    state.rune.secondaryTreeId = id;
    state.rune.secondary = { picks: [null, null, null] };
    renderTreeTabs("secondary-tabs", state.rune.secondaryTreeId, onSecondary, state.rune.primaryTreeId);
    renderSecondarySlots();
    renderRuneSummary();
  };

  renderTreeTabs("primary-tabs", state.rune.primaryTreeId, onPrimary);
  renderTreeTabs("secondary-tabs", state.rune.secondaryTreeId, onSecondary, state.rune.primaryTreeId);
  renderPrimarySlots();
  renderSecondarySlots();
  renderRuneSummary();
}

function renderTreeTabs(elId, selectedId, onClick, excludeId = null) {
  const el = $(elId);
  el.innerHTML = "";
  for (const t of state.trees) {
    if (excludeId != null && t.id === excludeId) continue;
    const tab = document.createElement("div");
    tab.className = "tree-tab" + (t.id === selectedId ? " selected" : "");
    tab.title = t.name;
    const img = document.createElement("img");
    img.src = t.icon;
    img.alt = t.name;
    tab.appendChild(img);
    tab.addEventListener("click", () => onClick(t.id));
    el.appendChild(tab);
  }
}

function renderPrimarySlots() {
  const tree = state.trees.find((t) => t.id === state.rune.primaryTreeId);
  const wrap = $("primary-slots");
  wrap.innerHTML = "";
  if (!tree) return;
  tree.slots.forEach((slot, slotIdx) => {
    const row = document.createElement("div");
    row.className = "rune-slot" + (slotIdx === 0 ? " keystone-slot" : "");
    for (const r of slot.runes) {
      const o = mkRuneOption(r, slotIdx === 0, isPrimarySelected(slotIdx, r.id));
      o.addEventListener("click", () => {
        if (slotIdx === 0) state.rune.primary.keystone = r.id;
        else state.rune.primary.slots[slotIdx - 1] = r.id;
        renderPrimarySlots();
        renderRuneSummary();
      });
      row.appendChild(o);
    }
    wrap.appendChild(row);
  });
}

function isPrimarySelected(slotIdx, runeId) {
  if (slotIdx === 0) return state.rune.primary.keystone === runeId;
  return state.rune.primary.slots[slotIdx - 1] === runeId;
}

function renderSecondarySlots() {
  const tree = state.trees.find((t) => t.id === state.rune.secondaryTreeId);
  const wrap = $("secondary-slots");
  wrap.innerHTML = "";
  if (!tree) return;
  // Secondary skips keystone row. Show rows 1-3 (3 minor slots).
  tree.slots.slice(1).forEach((slot, slotIdx) => {
    const row = document.createElement("div");
    row.className = "rune-slot";
    for (const r of slot.runes) {
      const o = mkRuneOption(r, false, state.rune.secondary.picks[slotIdx] === r.id);
      o.addEventListener("click", () => toggleSecondaryPick(slotIdx, r.id));
      row.appendChild(o);
    }
    wrap.appendChild(row);
  });
}

function toggleSecondaryPick(slotIdx, runeId) {
  // Click toggles within a row; max 2 picks across rows.
  const picks = state.rune.secondary.picks;
  if (picks[slotIdx] === runeId) {
    picks[slotIdx] = null;
  } else {
    const filledOtherRows = picks.filter((p, i) => p && i !== slotIdx).length;
    if (filledOtherRows >= 2) {
      // Drop the earliest non-null pick from another row.
      for (let i = 0; i < picks.length; i++) {
        if (i !== slotIdx && picks[i]) { picks[i] = null; break; }
      }
    }
    picks[slotIdx] = runeId;
  }
  renderSecondarySlots();
  renderRuneSummary();
}

function mkRuneOption(rune, isKeystone, isSelected) {
  const o = document.createElement("div");
  o.className = "rune-option" + (isKeystone ? " keystone" : "") + (isSelected ? " selected" : "");
  const img = document.createElement("img");
  img.src = rune.icon;
  img.alt = rune.name;
  o.appendChild(img);
  const tip = document.createElement("div");
  tip.className = "tooltip";
  tip.innerHTML = `<strong>${rune.name}</strong>${rune.shortDesc || ""}`;
  o.appendChild(tip);
  return o;
}

// ----------------------- stat shards -----------------------

function renderShards() {
  const wrap = $("shard-rows");
  wrap.innerHTML = "";
  state.shards.rows.forEach((row, rowIdx) => {
    const r = document.createElement("div");
    r.className = "shard-row";
    const lbl = document.createElement("div");
    lbl.className = "row-label";
    lbl.textContent = row.name;
    r.appendChild(lbl);
    row.options.forEach((opt) => {
      const o = document.createElement("div");
      o.className = "shard-option" + (state.rune.shards[rowIdx] === opt.key ? " selected" : "");
      o.textContent = opt.glyph;
      const tip = document.createElement("div");
      tip.className = "tooltip";
      tip.textContent = opt.desc;
      o.appendChild(tip);
      o.addEventListener("click", () => {
        state.rune.shards[rowIdx] = state.rune.shards[rowIdx] === opt.key ? null : opt.key;
        renderShards();
        renderRuneSummary();
      });
      r.appendChild(o);
    });
    wrap.appendChild(r);
  });
}

// Convert chosen shards to {ad, ap, as} numbers (resolving Adaptive Force).
function resolveShards() {
  const out = { ad: 0, ap: 0, as: 0 };
  // Decide adaptive direction from item totals (AP > AD bonus -> AP).
  const sumAd = state.itemSlots.reduce((s, it) => s + (it ? it.ad : 0), 0);
  const sumAp = state.itemSlots.reduce((s, it) => s + (it ? it.ap : 0), 0);
  const adaptiveAsAp = sumAp > sumAd;

  state.rune.shards.forEach((key, rowIdx) => {
    if (!key) return;
    if (key === "AdaptiveForce") {
      if (adaptiveAsAp) out.ap += 9;
      else out.ad += 5.4;
    } else if (key === "AttackSpeed") {
      out.as += 0.10;
    }
    // Other shards (AbilityHaste, MoveSpeed, Health*, Tenacity) don't affect outgoing damage.
  });
  return out;
}

// ----------------------- summary + payload -----------------------

function findRune(id) {
  for (const t of state.trees) for (const s of t.slots) for (const r of s.runes) if (r.id === id) return r;
  return null;
}

function renderRuneSummary() {
  const lines = [];
  const ks = findRune(state.rune.primary.keystone);
  if (ks) lines.push(`Keystone: ${ks.name}`);
  const prim = state.rune.primary.slots.map(findRune).filter(Boolean).map((r) => r.name);
  if (prim.length) lines.push(`Primary: ${prim.join(", ")}`);
  const sec = state.rune.secondary.picks.map(findRune).filter(Boolean).map((r) => r.name);
  if (sec.length) lines.push(`Secondary: ${sec.join(", ")}`);
  const sh = state.rune.shards.map((k, i) => {
    if (!k) return null;
    const opt = state.shards.rows[i].options.find((o) => o.key === k);
    return opt ? opt.name : k;
  }).filter(Boolean);
  if (sh.length) lines.push(`Shards: ${sh.join(", ")}`);
  $("rune-summary").textContent = lines.join("  •  ");
}

function gatherPayload() {
  const items = state.itemSlots.filter(Boolean).map((it) => it.name);
  const ks = findRune(state.rune.primary.keystone);
  const minorRunes = [
    ...state.rune.primary.slots.map(findRune).filter(Boolean).map((r) => r.name),
    ...state.rune.secondary.picks.map(findRune).filter(Boolean).map((r) => r.name),
  ];
  const shards = resolveShards();

  const combo = $("combo").value.trim();

  return {
    champion: state.selectedChampion || "Garen",
    level: parseInt($("level").value, 10),
    items,
    skills: {
      Q: parseInt($("rank-q").value, 10),
      W: parseInt($("rank-w").value, 10),
      E: parseInt($("rank-e").value, 10),
      R: parseInt($("rank-r").value, 10),
    },
    rune_keystone: ks ? ks.name : null,
    runes: minorRunes,
    shards,
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
      combo: combo || null,
    },
  };
}

// ----------------------- results rendering -----------------------

function dtClass(t) { return `dt-${(t || "unknown").toLowerCase()}`; }

function escapeHtml(s) {
  return String(s).replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
}

function renderVariant(title, variant, openByDefault) {
  if (!variant) return "";
  const hits = variant.hits || [];
  const total = (variant.total || 0).toFixed(1);
  const kill = variant.killed ? '<span class="killed">KILL</span>' : "";
  const remaining = (variant.target_hp_remaining || 0).toFixed(0);

  const hitBlocks = hits.map((h) => {
    const expl = (h.explanation || []).map((line) => `<li>${escapeHtml(line)}</li>`).join("");
    const note = h.notes ? `<div class="note">${escapeHtml(h.notes)}</div>` : "";
    return `<details class="hit">
      <summary>
        <span class="hit-label">${escapeHtml(h.label)}</span>
        <span class="hit-type ${dtClass(h.damage_type)}">${escapeHtml(h.damage_type)}</span>
        <span class="hit-mit">${h.mitigated.toFixed(1)}</span>
      </summary>
      <ul class="explanation">${expl}</ul>
      ${note}
    </details>`;
  }).join("");

  return `<details class="variant" ${openByDefault ? "open" : ""}>
    <summary>
      <span class="variant-title">${title}</span>
      <span class="variant-total">${total}</span>
      ${kill}
    </summary>
    <div class="variant-body">
      ${hits.length ? hitBlocks : '<p class="note">No hits.</p>'}
      <p class="note">Target HP remaining: ${remaining}</p>
    </div>
  </details>`;
}

function renderResult(data) {
  const s = data.stats;
  const out = [];

  out.push(`<h3>${escapeHtml(data.champion)} (lvl ${data.level}) vs ${escapeHtml(data.target.name)}</h3>`);
  out.push(`<div class="kv">
    <div class="k">AD</div><div>${s.total_ad} (base ${s.base_ad} + bonus ${s.bonus_ad})</div>
    <div class="k">AP</div><div>${s.ap}</div>
    <div class="k">Attack speed</div><div>${s.attack_speed}</div>
    <div class="k">Crit</div><div>${(s.crit_chance * 100).toFixed(0)}% @ ${s.crit_damage}x</div>
    <div class="k">Lethality / %ArPen</div><div>${s.lethality} / ${(s.armor_pen_percent * 100).toFixed(0)}%</div>
    <div class="k">MagicPen flat / %</div><div>${s.flat_magic_pen} / ${(s.magic_pen_percent * 100).toFixed(0)}%</div>
    <div class="k">HP / Armor / MR</div><div>${s.max_hp} / ${s.armor} / ${s.magic_resist}</div>
  </div>`);

  const v = data.combo_variants || {};
  out.push('<div class="variants">');
  out.push(renderVariant("Total damage (no crit)", v.no_crit, false));
  out.push(renderVariant("Total damage (predicted crit)", v.expected_crit, true));
  out.push(renderVariant("Total damage (max crit)", v.max_crit, false));
  out.push("</div>");

  $("results").innerHTML = out.join("");
}

async function run() {
  const payload = gatherPayload();
  if (!payload.champion) {
    $("results").innerHTML = '<div class="error">Pick a champion first.</div>';
    return;
  }
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

// Standard skill leveling: R at 6/11/16, the rest distributed by max order.
function distributeSkillPoints(level, order) {
  const ranks = { Q: 0, W: 0, E: 0, R: 0 };
  if (level >= 6) ranks.R = 1;
  if (level >= 11) ranks.R = 2;
  if (level >= 16) ranks.R = 3;
  let left = level - ranks.R;
  const seq = (order || "QEW").split("");
  for (const k of seq) { if (left <= 0) break; ranks[k] = 1; left--; }
  for (const k of seq) {
    while (left > 0 && ranks[k] < 5) { ranks[k]++; left--; }
  }
  return ranks;
}

function autoFillSkills() {
  const level = Math.max(1, Math.min(18, parseInt($("level").value, 10) || 1));
  const order = ($("skill-order") && $("skill-order").value) || "QEW";
  const r = distributeSkillPoints(level, order);
  $("rank-q").value = r.Q;
  $("rank-w").value = r.W;
  $("rank-e").value = r.E;
  $("rank-r").value = r.R;
}

document.addEventListener("DOMContentLoaded", () => {
  loadCatalogs().catch((e) => {
    $("ddversion").textContent = "(failed to load)";
    console.error(e);
    $("results").innerHTML = `<div class="error">Failed to load catalog: ${e.message}</div>`;
  });
  $("champ-search").addEventListener("input", renderChampionGrid);
  $("item-search").addEventListener("input", renderItemGrid);
  $("level").addEventListener("input", autoFillSkills);
  $("skill-order").addEventListener("change", autoFillSkills);
  autoFillSkills();
  $("run").addEventListener("click", run);
});
