/* Agent Village — client engine. Polls /api/state, keeps the world alive. */
"use strict";

// ------------------------------------------------------------ config + utils
const POLL_MS = 3000;
const params = new URLSearchParams(location.search);
const TOKEN = params.get("token") || localStorage.getItem("village-token") || "";
if (TOKEN) localStorage.setItem("village-token", TOKEN);
if (params.get("present") === "1") document.body.classList.add("present");

const PROVIDERS = {
  claude:  { color: "#e8825a", badge: "🧡", body: "🧑‍💻" },
  codex:   { color: "#6fcf97", badge: "💚", body: "🧑‍💻" },
  kimi:    { color: "#7eb6ff", badge: "🌙", body: "🧑‍💻" },
  cursor:  { color: "#b494ff", badge: "💜", body: "🧑‍💻" },
  cowork:  { color: "#ffd166", badge: "🤝", body: "🧑‍💻" },
  gemini:  { color: "#8ad4ff", badge: "♊", body: "🧑‍💻" },
  aider:   { color: "#ffb3c7", badge: "🅰️", body: "🧑‍💻" },
  unknown: { color: "#b0bec5", badge: "⚪", body: "🧑‍💻" },
};
const KIND_ICON = { commit: "🏗️", edit: "✏️", claim: "📌", note: "📒", chat: "💬",
                    arrive: "🚶", leave: "👋", system: "🔧" };

const $ = (id) => document.getElementById(id);
const esc = (s) => String(s ?? "").replace(/[&<>"']/g,
  (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

function hashStr(s) { let h = 0; for (let i = 0; i < s.length; i++) h = (h * 31 + s.charCodeAt(i)) | 0; return Math.abs(h); }
function ago(ts) {
  if (!ts) return "";
  const d = Math.max(0, Date.now() / 1000 - ts);
  if (d < 60) return `${Math.floor(d)}s`;
  if (d < 3600) return `${Math.floor(d / 60)}m`;
  if (d < 86400) return `${Math.floor(d / 3600)}h`;
  return `${Math.floor(d / 86400)}d`;
}
function api(path, opts) {
  const sep = path.includes("?") ? "&" : "?";
  return fetch(path + (TOKEN ? sep + "token=" + encodeURIComponent(TOKEN) : ""), opts)
    .then(async (r) => {
      const data = await r.json().catch(() => ({}));
      if (!r.ok) throw new Error(data.error || `${r.status}`);
      return data;
    });
}
function toast(text, ms = 2600) {
  const el = $("toast"); el.textContent = text; el.hidden = false;
  clearTimeout(toast._t); toast._t = setTimeout(() => { el.hidden = true; }, ms);
}

// ------------------------------------------------------------ sound
const sound = {
  on: false, ctx: null,
  toggle() {
    this.on = !this.on;
    if (this.on && !this.ctx) this.ctx = new (window.AudioContext || window.webkitAudioContext)();
    $("btn-sound").textContent = this.on ? "🔊" : "🔇";
    if (this.on) this.blip(660, 0.08);
  },
  blip(freq = 520, dur = 0.06, type = "sine", gain = 0.045) {
    if (!this.on || !this.ctx) return;
    const t = this.ctx.currentTime, osc = this.ctx.createOscillator(), g = this.ctx.createGain();
    osc.type = type; osc.frequency.value = freq;
    g.gain.setValueAtTime(gain, t); g.gain.exponentialRampToValueAtTime(0.0001, t + dur);
    osc.connect(g).connect(this.ctx.destination); osc.start(t); osc.stop(t + dur);
  },
  chord() { [523, 659, 784].forEach((f, i) => setTimeout(() => this.blip(f, 0.14, "triangle"), i * 70)); },
};

// ------------------------------------------------------------ ambient sky
function buildAmbient() {
  const stars = $("stars");
  for (let i = 0; i < 60; i++) {
    const s = document.createElement("div");
    s.className = "star";
    s.style.left = Math.random() * 100 + "%";
    s.style.top = Math.random() * 80 + "%";
    s.style.animationDelay = Math.random() * 3 + "s";
    stars.appendChild(s);
  }
  const clouds = $("clouds");
  for (let i = 0; i < 3; i++) {
    const c = document.createElement("div");
    c.className = "cloud"; c.textContent = "☁️";
    c.style.top = 8 + i * 26 + "px";
    c.style.animationDuration = 90 + i * 40 + "s";
    c.style.animationDelay = -i * 35 + "s";
    clouds.appendChild(c);
  }
  setInterval(() => {  // an occasional bird crosses the village
    if (document.hidden || Math.random() > 0.4) return;
    const b = document.createElement("div");
    b.className = "bird"; b.textContent = Math.random() > 0.5 ? "🐦" : "🕊️";
    b.style.top = 10 + Math.random() * 30 + "%";
    b.style.animationDuration = 14 + Math.random() * 10 + "s";
    $("fx").appendChild(b);
    setTimeout(() => b.remove(), 26000);
  }, 22000);
}

function fireworks(x, y) {
  const fx = $("fx"), colors = ["#ffd166", "#ff6b6b", "#6fcf97", "#7eb6ff", "#b494ff"];
  for (let i = 0; i < 22; i++) {
    const s = document.createElement("div");
    s.className = "spark";
    const ang = (Math.PI * 2 * i) / 22, dist = 40 + Math.random() * 70;
    s.style.setProperty("--dx", Math.cos(ang) * dist + "px");
    s.style.setProperty("--dy", Math.sin(ang) * dist + "px");
    s.style.left = x + "px"; s.style.top = y + "px";
    s.style.background = colors[i % colors.length];
    s.style.boxShadow = `0 0 8px ${colors[i % colors.length]}`;
    fx.appendChild(s);
    setTimeout(() => s.remove(), 1200);
  }
}

// ------------------------------------------------------------ state + replay
let latest = null;
const historyBuf = [];           // snapshots for time travel
let replaying = false;

function pushHistory(state) {
  historyBuf.push(state);
  if (historyBuf.length > 120) historyBuf.shift();
  const slider = $("replay-slider");
  slider.max = Math.max(0, historyBuf.length - 1);
  if (!replaying) slider.value = slider.max;
}

function poll() {
  if (replaying) { schedule(); return; }
  api("/api/state").then((state) => {
    const prevEventId = latest ? topEventId(latest) : -1;
    latest = state; pushHistory(state);
    render(state, prevEventId);
    if (pendingSheet) {
      const u = (state.universes || []).find((x) => x.id === pendingSheet);
      if (u) { openUniverseSheet(u); pendingSheet = null; }
    }
  }).catch(() => { /* keep last frame; server may be restarting */ });
  schedule();
}
let pendingSheet = params.get("universe");
function schedule() { setTimeout(poll, POLL_MS); }
function topEventId(state) { return state.events.length ? state.events[state.events.length - 1].id : -1; }

// ------------------------------------------------------------ render: village
const sprites = new Map();  // id -> element

function render(state, prevEventId) {
  document.body.classList.remove("day", "sunset", "night");
  document.body.classList.add(state.day_phase || "day");
  renderStats(state.stats);
  renderArchipelago(state.universes || []);
  renderZones(state.zones || []);
  renderHarbor(state.zones.filter((z) => z.kind === "island"));
  renderWorld(state.world || null);
  renderSprites(state.agents || []);  // sync: innerHTML above already forced layout
  renderFeed(state.events || [], prevEventId);
}

function renderStats(stats) {
  const s = stats || {};
  $("stats").innerHTML = [
    s.agents_active ? `🟢 <b>${s.agents_active}</b> working` : `😴 quiet`,
    `👥 ${s.agents_total ?? 0}`,
    s.subagents ? `🐣 ${s.subagents} sub` : "",
    `✏️ ${s.edits_1h ?? 0}/h`,
    s.commits_24h ? `🏗️ ${s.commits_24h}/24h` : "",
    s.hottest_zone ? `🔥 ${esc(s.hottest_zone)}` : "",
    s.universes_total ? `☁️ ${s.universes_alive}/${s.universes_total} universes` : "",
  ].filter(Boolean).map((h) => `<span class="chip">${h}</span>`).join("");
}

function renderArchipelago(universes) {
  const el = $("archipelago");
  if (!universes.length) {
    el.innerHTML = `<div class="isle empty">no universes in the sky yet — they appear as your daemons wake</div>`;
    return;
  }
  el.innerHTML = universes.map((u) => `
    <div class="isle" data-universe="${esc(u.id)}" title="${esc(u.premise || u.name)}">
      <span class="dot ${u.status === "alive" ? "alive" : "dormant"}"></span>
      <div class="isle-emoji">${esc(u.emoji)}</div>
      <div class="isle-name">${esc(u.name)}</div>
      <div class="isle-meta">${u.words ? `${Number(u.words).toLocaleString()} words · ` : ""}${u.preset ? `🧠 ${esc(u.preset)} · ` : ""}${esc(u.seen || "")}</div>
    </div>`).join("");
  el.querySelectorAll(".isle[data-universe]").forEach((node) =>
    node.addEventListener("click", () => openUniverseSheet(universes.find((u) => u.id === node.dataset.universe))));
}

function renderZones(zones) {
  const el = $("zones");
  const core = zones.filter((z) => z.kind === "core");
  el.innerHTML = core.map((z) => {
    const heat = z.heat >= 6 ? 3 : z.heat >= 3 ? 2 : z.heat >= 1 ? 1 : 0;
    return `<div class="zone heat-${heat}" data-zone="${esc(z.id)}">
      ${heat >= 2 ? '<div class="smoke">💨</div>' : ""}
      <div class="z-emoji">${esc(z.emoji)}</div>
      <div class="z-label">${esc(z.label)}</div>
    </div>`;
  }).join("");
}

function renderHarbor(islands) {
  const el = $("islands");
  el.innerHTML = islands.map((z) => `
    <div class="island ${z.stale ? "stale" : ""}" data-zone="${esc(z.id)}">
      ${z.dirty ? '<span class="i-flag">🚩</span>' : ""}
      <div class="i-name">🏝️ ${esc(z.label)}</div>
      <div class="i-branch">${esc(z.branch || "")}${z.stale ? " · stale" : ""}</div>
    </div>`).join("");
  $("harbor").style.display = islands.length ? "" : "none";
}

function zoneAnchor(zoneId) {
  const node = document.querySelector(`[data-zone="${CSS.escape(zoneId)}"]`);
  const world = $("village");
  if (!node) return null;
  const zr = node.getBoundingClientRect(), wr = world.getBoundingClientRect();
  return { x: zr.left - wr.left + zr.width / 2, y: zr.top - wr.top + zr.height / 2 };
}

function propAnchor(propId) {
  const node = $(propId), world = $("village");
  const zr = node.getBoundingClientRect(), wr = world.getBoundingClientRect();
  return { x: zr.left - wr.left + 20, y: zr.top - wr.top - 6 };
}

function renderSprites(agents) {
  const layer = $("sprites");
  const seen = new Set();
  const groups = new Map();  // anchorKey -> [{a, el}]

  agents.forEach((a) => {
    seen.add(a.id);
    let el = sprites.get(a.id);
    const meta = PROVIDERS[a.provider] || PROVIDERS.unknown;
    if (!el) {
      el = document.createElement("div");
      el.className = "sprite";
      el.innerHTML = `<div class="bubble"></div>
        <span class="badge">${meta.badge}</span>
        <span class="body">${a.kind === "subagent" ? "🤖" : meta.body}</span>
        <div class="ring"></div><div class="tag"></div>`;
      el.addEventListener("click", () => openAgentSheet(a));
      layer.appendChild(el);
      sprites.set(a.id, el);
      el._born = Date.now();
    }
    el.classList.toggle("sub", a.kind === "subagent");
    el.classList.toggle("idle", a.status === "idle");
    el.querySelector(".ring").style.borderColor = meta.color;
    el.querySelector(".tag").textContent = a.name;
    el.querySelector(".tag").style.color = meta.color;
    const old = el.querySelector(".zzz");
    if (a.status === "idle" && !old) {
      const z = document.createElement("span"); z.className = "zzz"; z.textContent = "💤"; el.appendChild(z);
    } else if (a.status !== "idle" && old) old.remove();
    const bubble = el.querySelector(".bubble");
    bubble.textContent = `${a.action || "thinking"} · ${a.seen || ""}`;
    el.classList.toggle("loud", Date.now() - el._born < 9000);
    el.style.display = "";

    const key = a.status === "idle" ? "prop:campfire"
      : a.status === "claimed" ? "prop:notice-board"
      : `zone:${a.zone}`;
    if (!groups.has(key)) groups.set(key, []);
    groups.get(key).push({ a, el });
  });

  // grid-layout each group around its anchor, overflow collapses to +N
  for (const [key, members] of groups) {
    const splitAt = key.indexOf(":");
    const kind = key.slice(0, splitAt), id = key.slice(splitAt + 1);
    const anchor = kind === "zone"
      ? (zoneAnchor(id) || propAnchor("notice-board"))
      : propAnchor(id);
    const mains = members.filter((m) => m.a.kind !== "subagent");
    const subs = members.filter((m) => m.a.kind === "subagent");
    const ordered = [...mains, ...subs];
    const CAP = 11;
    ordered.forEach(({ a, el }, idx) => {
      if (idx >= CAP) { el.style.display = "none"; return; }
      const cols = Math.min(4, Math.max(2, Math.ceil(Math.sqrt(Math.min(ordered.length, CAP)))));
      const col = idx % cols, row = Math.floor(idx / cols);
      const jx = (col - (cols - 1) / 2) * 42 + (a.kind === "subagent" ? 16 : 0);
      const jy = (row - 1) * 38 + (a.kind === "subagent" ? 24 : 0);
      moveSprite(el, anchor.x + jx - 20, anchor.y + jy - 30);
    });
    updateOverflowChip(key, anchor, ordered.length - CAP > 0 ? ordered.length - CAP : 0);
  }

  for (const [id, el] of sprites) {
    if (!seen.has(id)) { el.style.opacity = "0"; setTimeout(() => el.remove(), 600); sprites.delete(id); }
  }
}

function moveSprite(el, nx, ny) {
  if (el.style.left !== nx + "px" || el.style.top !== ny + "px") {
    el.classList.add("walking");
    clearTimeout(el._walkT);
    el._walkT = setTimeout(() => el.classList.remove("walking"), 2700);
  }
  el.style.left = nx + "px"; el.style.top = ny + "px";
}

const overflowChips = new Map();
function updateOverflowChip(key, anchor, count) {
  let chip = overflowChips.get(key);
  if (!count) {
    if (chip) { chip.remove(); overflowChips.delete(key); }
    return;
  }
  if (!chip) {
    chip = document.createElement("div");
    chip.className = "sprite overflow-chip";
    $("sprites").appendChild(chip);
    overflowChips.set(key, chip);
  }
  chip.innerHTML = `<div class="tag" style="background:#1d2547">+${count} more</div>`;
  chip.style.left = anchor.x + 30 + "px";
  chip.style.top = anchor.y + 44 + "px";
  chip.style.display = "";
}

// ------------------------------------------------------------ render: feed
const FEED_ICON = (k) => KIND_ICON[k] || "•";
const ACTOR_COLORS = ["#e8825a", "#6fcf97", "#7eb6ff", "#b494ff", "#ffd166", "#8ad4ff", "#ffb3c7"];
const actorColor = (name) => ACTOR_COLORS[hashStr(name || "?") % ACTOR_COLORS.length];

function renderFeed(events, prevEventId) {
  const el = $("feed");
  const items = events.slice(-80).reverse();
  el.innerHTML = items.map((e) => `
    <div class="feed-item" data-eid="${e.id}">
      <div class="f-icon">${FEED_ICON(e.kind)}</div>
      <div><span class="f-actor" style="color:${actorColor(e.actor)}">${esc(e.actor)}</span>
        <span class="f-time">${ago(e.ts)}</span>
        <div class="f-text">${esc(e.text).replace(/`([^`]+)`/g, "<code>$1</code>")}</div>
      </div>
    </div>`).join("");
  $("feed-count").textContent = `${events.length} events`;
  // celebrate genuinely new events
  if (prevEventId >= 0) {
    const fresh = events.filter((e) => e.id > prevEventId);
    for (const e of fresh) {
      if (e.kind === "commit") {
        const w = $("village").getBoundingClientRect();
        fireworks(w.width * (0.2 + Math.random() * 0.6), w.height * (0.2 + Math.random() * 0.4));
        sound.chord();
      } else if (e.kind === "arrive") sound.blip(700, 0.09, "triangle");
      else if (e.kind === "edit") sound.blip(440, 0.04);
    }
  }
}

// ------------------------------------------------------------ world zoom
let zoomed = false;
function renderWorld(world) {
  if (!world) return;
  const el = $("worldmap");
  if (!world.reachable) {
    el.innerHTML = `<div class="wm-head">🌍 world unreachable — the public directory didn't answer. Your village keeps working offline.</div>`;
    return;
  }
  const m = world.market || {};
  const universes = world.universes || [];
  const commons = world.commons || [];
  const sections = [];
  sections.push(`<div class="wm-head">🌍 everything publicly viewable right now</div>`);
  if (m.bids_open || m.queue_pending || m.settlements_unsettled) {
    sections.push(`<div class="wm-market">
      <span class="chip">🪙 <b>${m.bids_open ?? 0}</b> open bids</span>
      <span class="chip">📥 <b>${m.queue_pending ?? 0}</b> queued</span>
      <span class="chip">💰 <b>${m.settlements_unsettled ?? 0}</b> unsettled</span>
    </div>`);
  }
  if (universes.length) {
    sections.push(`<div class="wm-section">☁️ universes</div><div class="wm-grid">${universes.map((u) => `
      <div class="wm-card" data-live-universe="${esc(u.id)}">
        <div class="wm-emoji">${esc(u.emoji || "☁️")}</div>
        <div class="wm-name">${esc(u.name)}</div>
        <div class="wm-premise">${esc(u.premise || "")}</div>
        <div class="wm-meta">${u.accept_rate != null ? `✅ ${Math.round(u.accept_rate * 100)}% accepted · ` : ""}${u.words ? `${Number(u.words).toLocaleString()} words · ` : ""}${esc(u.seen || "")}</div>
      </div>`).join("")}</div>`);
  }
  if (commons.length) {
    sections.push(`<div class="wm-section">🌿 the commons</div><div class="wm-grid">${commons.map((p) => `
      <div class="wm-card"><div class="wm-emoji">📄</div>
        <div class="wm-name">${esc(p.name)}</div>
        <div class="wm-meta">${esc(p.path || "")}</div></div>`).join("")}</div>`);
  }
  if (!universes.length && !commons.length) {
    sections.push(`<div class="wm-head">the commons is quiet — nothing public yet</div>`);
  }
  el.innerHTML = sections.join("");
  el.querySelectorAll("[data-live-universe]").forEach((node) =>
    node.addEventListener("click", () => {
      const u = universes.find((x) => x.id === node.dataset.liveUniverse);
      if (u) openUniverseSheet(u);
    }));
}
function setZoom(world) {
  zoomed = world;
  $("worldmap").style.display = world ? "block" : "none";
  $("village").style.display = world ? "none" : "";
  $("harbor").style.display = world ? "none" : "";
  $("zoom-toggle").textContent = world ? "🏘️ my village" : "🌍 zoom out";
}

// ------------------------------------------------------------ sheets + chat
let chatTarget = null, chatTimer = null;

function openSheet(whoHtml, detailHtml, target, hint) {
  $("sheet-who").innerHTML = whoHtml;
  $("sheet-detail").innerHTML = detailHtml;
  $("chat-hint").textContent = hint;
  $("sheet").hidden = false; $("sheet-backdrop").hidden = false;
  chatTarget = target;
  loadChat();
  clearInterval(chatTimer);
  chatTimer = setInterval(loadChat, 4000);
  setTimeout(() => $("chat-input").focus(), 150);
}
function closeSheet() {
  $("sheet").hidden = true; $("sheet-backdrop").hidden = true;
  $("hire-box").hidden = true;
  chatTarget = null; clearInterval(chatTimer);
}

function openAgentSheet(a) {
  if (!a) return;
  const meta = PROVIDERS[a.provider] || PROVIDERS.unknown;
  openSheet(
    `${esc(a.name)} <span class="who-chip" style="background:${meta.color}22;color:${meta.color}">${esc(a.provider)} · ${a.kind}</span>`,
    `<div class="d-row">⚡ <b>${esc(a.action || "thinking")}</b></div>
     ${a.file ? `<div class="d-row">📄 <b>${esc(a.file)}</b></div>` : ""}
     ${a.task && a.task !== a.label ? `<div class="d-row">💭 opened with: "${esc(String(a.task).slice(0, 140))}"</div>` : ""}
     ${a.claim ? `<div class="d-row">📌 claim: ${esc(a.claim)}</div>` : ""}
     <div class="d-row">🪪 session <b>${esc(a.serial || "—")}</b>${a.branch ? ` · 🌿 <b>${esc(a.branch)}</b>` : ""}</div>
     <div class="d-row">🕐 seen ${esc(a.seen || "—")}${a.model ? ` · 🧠 ${esc(a.model)}` : ""} · status ${esc(a.status)}</div>`,
    `agent:${a.id}`,
    "Your note lands in their inbox file (.agents/village-inbox/) — agents read it on their next check-in."
  );
}

function openUniverseSheet(u) {
  if (!u) return;
  const brief = u.brief || {};
  const briefRows = [
    brief.phase ? `⚙️ phase: <b>${esc(brief.phase)}</b>` : "",
    brief.accept_rate != null ? `✅ ${Math.round(brief.accept_rate * 100)}% of scenes accepted` : "",
    brief.paused === true ? "⏸️ daemon paused" : "",
    brief.bids_open != null ? `🪙 ${brief.bids_open} open bids` : "",
    brief.queue_pending != null ? `📥 ${brief.queue_pending} queued` : "",
  ].filter(Boolean).map((r) => `<div class="d-row">${r}</div>`).join("");
  const liveHint = u.source === "live"
    ? "Live over the platform MCP — the daemon answers in its own voice (writes need sign-in; without it your note is mirrored locally)."
    : null;
  openSheet(
    `${esc(u.emoji)} ${esc(u.name)} <span class="who-chip" style="background:#7eb6ff22;color:#7eb6ff">${u.status}</span>`,
    `${u.premise ? `<div class="d-row">📖 <b>${esc(u.premise)}</b></div>` : ""}
     <div class="d-row">${u.words ? `✍️ ${Number(u.words).toLocaleString()} words · ` : ""}🕐 ${esc(u.seen || "")}${u.preset ? ` · 🧠 runs on <b>${esc(u.preset)}</b>` : ""}</div>
     ${briefRows}
     ${u.last_activity ? `<div class="d-row">📜 ${esc(u.last_activity)}</div>` : ""}`,
    `universe:${u.id}`,
    liveHint || (u.status === "alive"
      ? "Your note reaches the daemon at its next scene boundary; it answers through its log."
      : "This daemon is asleep — your note is pinned in its universe and read on next wake.")
  );
  showHireBox(u);
}

// ------------------------------------------------------------ hire
let providerList = null;
function loadProviders() {
  if (providerList) return Promise.resolve(providerList);
  return api("/api/providers")
    .then((d) => { providerList = d.providers || []; return providerList; })
    .catch(() => []);
}

function showHireBox(u) {
  const box = $("hire-box");
  box.hidden = false;
  loadProviders().then((list) => {
    const sel = $("hire-provider");
    sel.innerHTML = list.map((p) =>
      `<option value="${esc(p.id)}" ${p.available ? "" : "disabled"}>` +
      `${esc(p.label)}${p.available ? "" : ` — ${esc(p.note)}`}</option>`).join("");
    if (u.preset) {
      const match = list.find((p) => p.available && u.preset.includes(p.id));
      if (match) sel.value = match.id;
    }
    const updateNote = () => {
      const engine = list.find((p) => p.id === sel.value);
      $("hire-note").textContent = engine?.dispatchable
        ? "dispatch spawns real sessions on that provider's budget — they'll walk into the village as sprites"
        : "set-as-engine rewrites the universe's config.yaml preset for its next daemon run";
    };
    sel.onchange = updateNote;
    updateNote();
  });
  $("hire-dispatch").onclick = () => submitHire(u, false);
  $("hire-preset").onclick = () => submitHire(u, true);
}

function submitHire(u, preset) {
  const payload = {
    universe_id: u.id,
    provider: $("hire-provider").value,
    count: Math.max(1, Math.min(8, Number($("hire-count").value || 1))),
    task: $("hire-task").value.trim(),
    preset,
  };
  api("/api/hire", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  }).then((res) => {
    toast(res.note || `hired for ${res.to}`);
    loadChat();
  }).catch((e) => toast(`hire failed — ${e.message}`, 4200));
}

function loadChat() {
  if (!chatTarget) return;
  api("/api/chat?target=" + encodeURIComponent(chatTarget)).then((data) => {
    const log = $("chat-log");
    const msgs = data.messages || [];
    log.innerHTML = msgs.length ? msgs.map((m) => `
      <div class="chat-msg ${m.who === "host" ? "host" : "them"}">
        <span class="m-who">${esc(m.who)} · ${esc(m.ts || "")}</span>
        <span class="m-text">${esc(m.text)}</span>
      </div>`).join("") : '<div class="chat-empty">no messages yet — say hi 👋</div>';
    log.scrollTop = log.scrollHeight;
  }).catch(() => {});
}

function sendChat(ev) {
  ev.preventDefault();
  const input = $("chat-input");
  const text = input.value.trim();
  if (!text || !chatTarget) return;
  input.value = "";
  api("/api/talk", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ target: chatTarget, message: text }),
  }).then((res) => {
    toast(res.note || (res.mode ? `delivered to ${res.to} (${res.mode})` : `delivered to ${res.to}`));
    loadChat();
  }).catch((e) => toast(`failed to send (${e.message})`));
}

// ------------------------------------------------------------ boot
function boot() {
  buildAmbient();
  // feed panel: closed by default on small screens, FAB toggles
  const fab = document.createElement("button");
  fab.id = "feed-fab"; fab.textContent = "📜";
  fab.addEventListener("click", () => $("feed-panel").classList.toggle("open"));
  document.body.appendChild(fab);
  $("feed-handle").addEventListener("click", () => $("feed-panel").classList.toggle("open"));
  // zoom toggle
  const zoom = document.createElement("button");
  zoom.id = "zoom-toggle"; zoom.textContent = "🌍 zoom out";
  zoom.addEventListener("click", () => setZoom(!zoomed));
  document.body.appendChild(zoom);
  // hud buttons
  $("btn-sound").addEventListener("click", () => sound.toggle());
  $("btn-share").addEventListener("click", () => {
    navigator.clipboard?.writeText(location.href).then(
      () => toast("link copied — open it on any device on this network"),
      () => toast(location.href));
  });
  // replay
  $("btn-replay").addEventListener("click", () => { $("replay-bar").hidden = !$("replay-bar").hidden; });
  $("replay-slider").addEventListener("input", (e) => {
    const idx = Number(e.target.value);
    replaying = idx < historyBuf.length - 1;
    const state = historyBuf[idx];
    if (state) {
      render(state, -1);
      $("replay-label").textContent = replaying ? ago(state.generated_at) + " ago" : "live";
    }
  });
  $("replay-live").addEventListener("click", () => {
    replaying = false;
    $("replay-slider").value = $("replay-slider").max;
    $("replay-label").textContent = "live";
    if (latest) render(latest, -1);
  });
  // sheet
  $("sheet-close").addEventListener("click", closeSheet);
  $("sheet-backdrop").addEventListener("click", closeSheet);
  $("chat-form").addEventListener("submit", sendChat);
  document.addEventListener("keydown", (e) => { if (e.key === "Escape") closeSheet(); });
  // repo name in header
  api("/api/state").then((s) => { if (s.repo) $("brand-sub").textContent = s.repo; }).catch(() => {});
  if (params.get("zoom") === "world") setZoom(true);
  poll();
}

document.addEventListener("DOMContentLoaded", boot);
