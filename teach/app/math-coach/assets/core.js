"use strict";
/* Core: helpers, API client, router, header, sounds, dialogs, PIN pad, accessibility settings. */

const $ = (sel, root = document) => root.querySelector(sel);
const $$ = (sel, root = document) => [...root.querySelectorAll(sel)];
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const pct = (c, n) => (n ? Math.round((100 * c) / n) : 0) + "%";
const store = {
  get(k) { try { return localStorage.getItem(k); } catch { return null; } },
  set(k, v) { try { localStorage.setItem(k, v); } catch {} },
};
const sess = {
  get(k) { try { return sessionStorage.getItem(k) || ""; } catch { return ""; } },
  set(k, v) { try { v ? sessionStorage.setItem(k, v) : sessionStorage.removeItem(k); } catch {} },
};
const LOCALE = { cat: "ca", esp: "es", eng: "en" };
const S = {
  lang: store.get("lang") || "cat", token: sess.get("token"), tt: sess.get("tt"), me: null, info: null,
  timers: [], keys: null, badges: null, cleanup: [],
};
const L = new Proxy({}, {
  get(_, k) {
    const d = I18N[S.lang] || I18N.cat;
    if (k in d) return d[k];
    if (k in I18N.eng) return I18N.eng[k];
    return `⟨${String(k)}⟩`;
  },
});
const fmtNum = (n, digits = 0) => Number(n).toLocaleString(LOCALE[S.lang], { maximumFractionDigits: digits, minimumFractionDigits: digits });
const fmtSecs = (s) => {
  if (s == null) return "–";
  s = Math.round(s);
  return s < 60 ? `${s} s` : `${Math.floor(s / 60)} min ${String(s % 60).padStart(2, "0")} s`;
};
const clock = (s) => `${Math.floor(Math.max(0, s) / 60)}:${String(Math.floor(Math.max(0, s) % 60)).padStart(2, "0")}`;
const when = (ts) => new Date(ts * 1000).toLocaleString(LOCALE[S.lang], { dateStyle: "short", timeStyle: "short" });
const ago = (ts) => {
  if (!ts) return "–";
  const s = Date.now() / 1000 - ts;
  return s < 90 ? L.now : s < 3600 ? L.minAgo(Math.round(s / 60)) : s < 86400 ? L.hAgo(Math.round(s / 3600)) : L.dAgo(Math.round(s / 86400));
};
const avatar = (a, cls = "") => `<span class="av ${cls}" aria-hidden="true">${esc(a || "🦘")}</span>`;
/* Lucide icon from the sprite in index.html (decorative: the text next to it carries the meaning) */
const icon = (name, cls = "") => `<svg class="ic ${cls}" aria-hidden="true"><use href="#i-${name}"/></svg>`;
const shape = (letter) => `<svg class="shape" aria-hidden="true"><use href="#s-${letter}"/></svg>`;
/* Emojis that used to mark insights, mapped to icons (one consistent icon language in the interface) */
const EMOJI_ICON = { "📊": "chart-column", "🆘": "triangle-alert", "🎲": "circle-help", "📉": "trending-down", "💡": "lightbulb", "🧩": "puzzle",
  "🧠": "brain", "👥": "users", "⏱️": "timer", "🧭": "gauge", "🚀": "rocket", "📈": "trending-up", "🎚️": "gauge", "✅": "circle-check",
  "⚠️": "triangle-alert", "💤": "clock", "🌱": "sprout", "🐢": "hourglass", "💪": "award", "🎯": "target", "⏱": "timer", "🔬": "microscope",
  "✦": "sparkles", "🌍": "globe", "📝": "file-text", "⚖️": "shield-check", "🔒": "key-round", "🤖": "bot", "✍️": "pencil" };
const iconFor = (e) => icon(EMOJI_ICON[e] || "info");
const HUES = ["#ffe3e3", "#fff3bf", "#d3f9d8", "#d0ebff", "#e5dbff", "#ffe8cc", "#c5f6fa", "#fcc2d7", "#e9fac8", "#dbe4ff"];
const hue = (id) => HUES[Math.abs(Number(id) || 0) % HUES.length];

// ---------------------------------------------------------------- API
async function api(path, params = {}) {
  const q = new URLSearchParams(Object.entries(params).filter(([, v]) => v !== undefined && v !== null && v !== "")).toString();
  let r;
  try {
    r = await fetch(`/api/${path}${q ? "?" + q : ""}`, { cache: "no-store" });
  } catch (e) {
    toast(L.offline, "bad", "📡");
    throw e;
  }
  if (!r.ok) {
    toast(`${L.serverError} (${r.status})`, "bad", "⚠️");
    throw new Error(await r.text());
  }
  const data = await r.json();
  if (data.error === "auth") {
    if (path.startsWith("t_")) { S.tt = ""; sess.set("tt", ""); go("#/teacher"); }
    else { S.token = ""; sess.set("token", ""); S.me = null; toast(L.sessionEnded, "bad", "🔒"); go("#/"); }
    throw new Error("auth");
  }
  return data;
}
const my = (path, params = {}) => api(path, { token: S.token, ...params });
const tapi = (path, params = {}) => api(path, { tt: S.tt, ...params });

// ---------------------------------------------------------------- timers that stop when the page changes
function every(ms, fn) { const id = setInterval(fn, ms); S.timers.push(() => clearInterval(id)); return id; }
function later(ms, fn) { const id = setTimeout(fn, ms); S.timers.push(() => clearTimeout(id)); return id; }
function clearTimers() { S.timers.forEach((f) => f()); S.timers = []; }

// ---------------------------------------------------------------- feedback: toasts, live region, confetti, sounds
function toast(text, kind = "", icon = "") {
  const box = $("#toasts");
  const el = document.createElement("div");
  el.className = `toast ${kind}`;
  el.setAttribute("role", "status");
  el.innerHTML = `${icon ? `<span aria-hidden="true">${icon}</span>` : ""}<span>${esc(text)}</span>`;
  box.append(el);
  setTimeout(() => el.remove(), 3800);
}
const say = (text) => { $("#announce").textContent = ""; setTimeout(() => ($("#announce").textContent = text), 30); };
const reducedMotion = () => document.documentElement.dataset.motion === "reduce" || matchMedia("(prefers-reduced-motion: reduce)").matches;
function confetti(n = 42) {
  if (reducedMotion()) return;
  const box = $("#confetti"), colors = ["#ffb703", "#4060e8", "#0ca678", "#f76707", "#7048e8", "#e64980"];
  box.innerHTML = Array.from({ length: n }, (_, i) =>
    `<i style="left:${Math.random() * 100}%;background:${colors[i % colors.length]};animation-delay:${Math.random() * 0.4}s;transform:rotate(${Math.random() * 90}deg)"></i>`).join("");
  setTimeout(() => (box.innerHTML = ""), 2600);
}

const Sound = {
  on: store.get("sound") !== "off", ctx: null,
  tone(freq, start, dur, type = "triangle", vol = 0.15) {
    const c = this.ctx, o = c.createOscillator(), g = c.createGain(), at = c.currentTime + start;
    o.type = type; o.frequency.value = freq;
    g.gain.setValueAtTime(0.0001, at);
    g.gain.exponentialRampToValueAtTime(vol, at + 0.015);
    g.gain.exponentialRampToValueAtTime(0.0001, at + dur);
    o.connect(g).connect(c.destination); o.start(at); o.stop(at + dur + 0.05);
  },
  play(kind) {
    if (!this.on) return;
    try {
      this.ctx = this.ctx || new (window.AudioContext || window.webkitAudioContext)();
      if (this.ctx.state === "suspended") this.ctx.resume();
    } catch { return; }
    const notes = {
      right:   [[523.25, 0, .18], [659.25, .09, .18], [783.99, .18, .34]],
      levelup: [[523.25, 0, .14], [659.25, .1, .14], [783.99, .2, .14], [1046.5, .3, .5]],
      streak:  [[783.99, 0, .12], [1046.5, .08, .12], [1318.5, .16, .4]],
      wrong:   [[392.0, 0, .24, "sine", .12], [329.63, .17, .38, "sine", .1]],
      hint:    [[880, 0, .12, "sine", .08], [1174.66, .07, .18, "sine", .07]],
      click:   [[660, 0, .05, "sine", .06]],
      key:     [[520, 0, .04, "sine", .05]],
      join:    [[587.33, 0, .1, "sine", .09], [880, .08, .16, "sine", .09]],
      tick:    [[1200, 0, .05, "square", .03]],
      badge:   [[659.25, 0, .12], [987.77, .1, .12], [1318.5, .2, .45, "sine", .12]],
      win:     [[523.25, 0, .16], [659.25, .14, .16], [783.99, .28, .16], [1046.5, .42, .3], [783.99, .62, .14], [1046.5, .74, .6]],
      start:   [[392, 0, .12, "sine", .1], [523.25, .12, .12, "sine", .1], [659.25, .24, .25, "sine", .1]],
    }[kind] || [];
    for (const [f, s, d, type, vol] of notes) this.tone(f, s, d, type, vol);
  },
};

// ---------------------------------------------------------------- read aloud (the browser's own voices, offline)
function speak(text) {
  if (!("speechSynthesis" in window)) { toast(L.noVoice, "", "🔇"); return; }
  speechSynthesis.cancel();
  const u = new SpeechSynthesisUtterance(text);
  u.lang = { cat: "ca-ES", esp: "es-ES", eng: "en-GB" }[S.lang];
  u.rate = 0.92;
  speechSynthesis.speak(u);
}

// ---------------------------------------------------------------- dialogs
function dialog(html, { wide = false, onClose = null } = {}) {
  const d = document.createElement("dialog");
  if (wide) d.className = "wide";
  d.innerHTML = `<button class="icon-btn dlg-x" data-close aria-label="${esc(L.close)}">✕</button><div class="dlg-body">${html}</div>`;
  document.body.append(d);
  d.addEventListener("close", () => { d.remove(); onClose && onClose(); });
  d.addEventListener("click", (e) => { if (e.target === d || e.target.closest("[data-close]")) d.close(); });
  d.showModal();
  return d;
}
function confirmBox(title, text, yes, { danger = false } = {}) {
  return new Promise((resolve) => {
    let ok = false;
    const d = dialog(`<h2>${esc(title)}</h2><p>${esc(text)}</p>
      <div class="row" style="justify-content:flex-end;margin-top:16px"><button class="btn ghost" data-close>${esc(L.cancel)}</button>
      <button class="btn ${danger ? "danger" : ""}" id="dlgYes">${esc(yes)}</button></div>`, { onClose: () => resolve(ok) });
    $("#dlgYes", d).onclick = () => { ok = true; d.close(); };
    $("#dlgYes", d).focus();
  });
}

/* A PIN pad: big keys for small fingers, physical keyboard too. submit(pin) returns "" when right, or the error text. */
function pinPad({ title, subtitle = "", av = "", length = 4, submit }) {
  let pin = "", busy = false;
  const d = dialog(`<div class="pin">${av ? avatar(av) : ""}<h2 style="margin-bottom:4px">${esc(title)}</h2>
    <p class="muted" style="margin:0">${esc(subtitle)}</p>
    <div class="pin-dots" aria-hidden="true">${"<i></i>".repeat(length)}</div>
    <div class="pin-err" role="alert"></div>
    <div class="keypad">${[1, 2, 3, 4, 5, 6, 7, 8, 9].map((k) => `<button data-k="${k}">${k}</button>`).join("")}
      <button data-k="del" aria-label="${esc(L.del)}">⌫</button><button data-k="0">0</button><button data-k="ok" class="ok">${esc(L.enter)}</button></div>
    <input class="sr" id="pinInput" inputmode="numeric" autocomplete="off" aria-label="PIN"></div>`);
  const dots = $$(".pin-dots i", d), err = $(".pin-err", d), box = $(".pin", d);
  const draw = () => dots.forEach((el, i) => el.classList.toggle("on", i < pin.length));
  async function send() {
    if (busy || !pin) return;
    busy = true;
    const problem = await submit(pin).catch(() => L.serverError);
    busy = false;
    if (!problem) { d.close(); return; }
    err.textContent = problem;
    box.classList.remove("shake"); void box.offsetWidth; box.classList.add("shake");
    Sound.play("wrong");
    pin = ""; draw();
  }
  function press(k) {
    if (k === "del") pin = pin.slice(0, -1);
    else if (k === "ok") return send();
    else if (pin.length < length) { pin += k; Sound.play("key"); }
    err.textContent = "";
    draw();
    if (pin.length === length) setTimeout(send, 120);
  }
  $(".keypad", d).addEventListener("click", (e) => { const b = e.target.closest("button"); if (b) press(b.dataset.k); });
  d.addEventListener("keydown", (e) => {
    if (/^\d$/.test(e.key)) { press(e.key); e.preventDefault(); }
    else if (e.key === "Backspace") { press("del"); e.preventDefault(); }
    else if (e.key === "Enter") { press("ok"); e.preventDefault(); }
  });
  $("#pinInput", d).focus();
  return d;
}

// ---------------------------------------------------------------- accessibility & display settings
const A11Y = { size: store.get("a11y_size") || "m", contrast: store.get("a11y_contrast") || "normal", theme: store.get("a11y_theme") || "auto",
               motion: store.get("a11y_motion") || "auto" };
function applyA11y() {
  const h = document.documentElement;
  h.dataset.size = A11Y.size;
  h.dataset.contrast = A11Y.contrast;
  if (A11Y.theme === "auto") delete h.dataset.theme; else h.dataset.theme = A11Y.theme;
  if (A11Y.motion === "reduce") h.dataset.motion = "reduce"; else delete h.dataset.motion;
}
function a11yPanel(anchor) {
  const old = $("#a11yPop");
  if (old) { old.remove(); return; }
  const seg = (key, opts) => `<div class="seg" role="group">${opts.map(([v, label]) =>
    `<button data-k="${key}" data-v="${v}" aria-pressed="${A11Y[key] === v}">${label}</button>`).join("")}</div>`;
  const p = document.createElement("div");
  p.className = "popover"; p.id = "a11yPop";
  p.innerHTML = `<h4>${esc(L.textSize)}</h4>${seg("size", [["m", "A"], ["l", "A+"], ["xl", "A++"]])}
    <h4>${esc(L.contrast)}</h4>${seg("contrast", [["normal", esc(L.normal)], ["high", esc(L.high)]])}
    <h4>${esc(L.theme)}</h4>${seg("theme", [["auto", esc(L.auto)], ["light", "☀️"], ["dark", "🌙"]])}
    <h4>${esc(L.motion)}</h4>${seg("motion", [["auto", esc(L.auto)], ["reduce", esc(L.less)]])}
    <h4>${esc(L.sound)}</h4><div class="seg"><button data-sound="on" aria-pressed="${Sound.on}">🔊 ${esc(L.on)}</button><button data-sound="off" aria-pressed="${!Sound.on}">🔇 ${esc(L.off)}</button></div>`;
  document.body.append(p);
  p.addEventListener("click", (e) => {
    const b = e.target.closest("button");
    if (!b) return;
    if (b.dataset.sound) { Sound.on = b.dataset.sound === "on"; store.set("sound", Sound.on ? "on" : "off"); if (Sound.on) Sound.play("hint"); }
    else { A11Y[b.dataset.k] = b.dataset.v; store.set("a11y_" + b.dataset.k, b.dataset.v); applyA11y(); }
    p.remove(); a11yPanel(anchor);
  });
  setTimeout(() => document.addEventListener("click", function off(e) {
    if (!p.contains(e.target) && e.target !== anchor) { p.remove(); document.removeEventListener("click", off); }
  }), 0);
}

// ---------------------------------------------------------------- header
function renderHeader() {
  const me = S.me, teacherMode = location.hash.startsWith("#/teacher");
  $("#top").innerHTML = `<div class="topbar-in">
    <a class="brand" href="#/"><svg aria-hidden="true"><use href="#roo"/></svg><div><b>${esc(L.appName)}</b><small>${esc(L.tagline)}</small></div></a>
    ${me && !teacherMode ? `<a class="me-chip" href="#/me" title="${esc(L.myProgress)}">${avatar(me.student.avatar)}<span class="nm">${esc(me.student.name)}</span>
      <span class="pts">⭐ ${fmtNum(me.stats.points)}</span></a>` : ""}
    ${teacherMode && S.tt ? `<span class="chip brand hide-s">${icon("graduation-cap")} ${esc(L.teacherMode)}</span>` : ""}
    <select class="lang" id="langSel" aria-label="${esc(L.language)}">${Object.keys(I18N).map((k) =>
      `<option value="${k}" ${k === S.lang ? "selected" : ""}>${I18N[k].langName}</option>`).join("")}</select>
    <button class="icon-btn" id="a11yBtn" aria-label="${esc(L.display)}" title="${esc(L.display)}">${icon("type")}</button>
    ${(me && !teacherMode) || (teacherMode && S.tt) ? `<button class="icon-btn" id="logoutBtn" title="${esc(L.logout)}" aria-label="${esc(L.logout)}">${icon("log-out")}</button>` : ""}
  </div>`;
  $("#langSel").onchange = async (e) => {
    S.lang = e.target.value; store.set("lang", S.lang);
    document.documentElement.lang = LOCALE[S.lang];
    if (S.token && !teacherMode) { try { await my("settings", { lang: S.lang }); } catch {} }
    render();
  };
  $("#a11yBtn").onclick = (e) => a11yPanel(e.currentTarget);
  const out = $("#logoutBtn");
  if (out) out.onclick = () => teacherMode ? teacherLogout() : logout();
}
async function refreshMe() {
  if (!S.token) return null;
  S.me = await my("me");
  if (S.me.student.lang && S.me.student.lang !== S.lang) { S.lang = S.me.student.lang; store.set("lang", S.lang); }
  if (!S.badges) S.badges = new Set(S.me.badges.filter((b) => b.earned).map((b) => b.code));
  return S.me;
}
function noticeBadges(list) {
  if (!list) return;
  const now = new Set(list.filter((b) => b.earned).map((b) => b.code));
  if (S.badges) for (const code of now) if (!S.badges.has(code)) {
    const [name] = L.badgeInfo[code] || [code];
    setTimeout(() => { toast(L.newBadge(name), "sun", BADGE_ICONS[code] || "🏅"); Sound.play("badge"); }, 900);
  }
  S.badges = now;
}
async function logout() {
  try { await api("logout", { token: S.token }); } catch {}
  S.token = ""; sess.set("token", ""); S.me = null; S.badges = null;
  go("#/");
}

// ---------------------------------------------------------------- router
const ROUTES = [];
const route = (re, fn, { student = false } = {}) => ROUTES.push({ re, fn, student });
const go = (hash) => { if (location.hash === hash) render(); else location.hash = hash; };
const SKELETON = `<div class="skeleton" aria-busy="true"><i style="height:64px;width:40%"></i><i style="height:150px"></i>
  <div class="grid3"><i style="height:120px"></i><i style="height:120px"></i><i style="height:120px"></i></div><i style="height:220px"></i></div>`;
function page(html) {
  clearTimeout(S.skeleton);
  document.body.classList.remove("has-checkbar");
  const v = $("#view");
  v.innerHTML = html;
  const h = $("h1", v);
  if (h) { h.tabIndex = -1; h.focus({ preventScroll: true }); }
  return v;
}
async function render() {
  clearTimers();
  S.keys = null;
  $("#a11yPop")?.remove();
  const h = location.hash.slice(1) || "/";
  document.documentElement.lang = LOCALE[S.lang];
  document.title = L.appName;
  for (const r of ROUTES) {
    const m = h.match(r.re);
    if (!m) continue;
    if (r.student && !S.token) { go("#/"); return; }
    try {
      if (r.student && !S.me) await refreshMe();
    } catch { return; }
    renderHeader();
    window.scrollTo(0, 0);
    clearTimeout(S.skeleton);
    S.skeleton = setTimeout(() => { $("#view").innerHTML = SKELETON; }, 180);  // only if loading takes a moment
    try { await r.fn(...m.slice(1).map((x) => (x == null ? undefined : decodeURIComponent(x)))); }
    catch (e) { if (e.message !== "auth") { console.error(e); } }
    finally { clearTimeout(S.skeleton); }
    return;
  }
  go("#/");
}
window.addEventListener("hashchange", render);
document.addEventListener("keydown", (e) => {
  if (!S.keys || e.ctrlKey || e.metaKey || e.altKey) return;
  if (e.target.closest("input, textarea, select, dialog")) return;
  S.keys(e);
});

/* Duolingo-style bottom bar: "Check" (disabled until an answer is picked), then the result and "Continue".
   It lives inside #view, so changing page removes it. */
function checkbar({ state = "idle", title = "", sub = "", button, onClick, disabled = false, extra = "" }) {
  let bar = $("#checkbar");
  if (!bar) {
    bar = document.createElement("div");
    bar.id = "checkbar";
    $("#view").append(bar);
  }
  document.body.classList.add("has-checkbar");
  bar.className = `checkbar ${state}`;
  bar.setAttribute("role", state === "idle" ? "region" : "status");
  bar.innerHTML = `<div class="checkbar-in">
    ${state !== "idle" ? `<span class="badge-ic">${icon(state === "good" ? "check" : "x")}</span>` : ""}
    <div class="msg">${title ? `<b>${title}</b>` : ""}${sub ? `<span>${sub}</span>` : ""}</div>${extra}
    <button class="btn big ${state === "bad" ? "danger" : state === "good" ? "good" : ""}" id="cbBtn" ${disabled ? "disabled" : ""}>${esc(button)}</button></div>`;
  $("#cbBtn", bar).onclick = onClick;
  if (state !== "idle") $("#cbBtn", bar).focus({ preventScroll: true });
  return bar;
}

// ---------------------------------------------------------------- shared pieces
function optionsHTML(options, { cls = "" } = {}) {
  const short = Object.values(options).every((v) => String(v).length <= 12);
  return `<div class="options ${short ? "short" : ""} ${cls}" role="group">${Object.entries(options).map(([k, v]) =>
    `<button class="opt" data-letter="${k}"><span class="letter">${cls.includes("kahoot") ? shape(k) : ""}${k}</span><span class="val">${esc(v)}</span></button>`).join("")}</div>`;
}
function levelStars(level) { return "★".repeat(1 + Math.floor(level / 2.7)); }
function bars(values, labels, { title = (i) => "", fmt = (v) => v } = {}) {
  const max = Math.max(1, ...values);
  return `<div class="bars-v">${values.map((v, i) => `<div class="b" title="${esc(title(i))}">
    <span class="val">${v ? esc(fmt(v)) : ""}</span><span class="col ${v ? "" : "zero"}" style="height:${(100 * v) / max}%"></span>
    <span class="x">${esc(labels[i])}</span></div>`).join("")}</div>`;
}
function hbars(rows, { max = null, fmt = (v) => v } = {}) {
  const m = max ?? Math.max(1, ...rows.map((r) => r.value));
  return `<div class="hbars">${rows.map((r) => `<div class="hbar" title="${esc(r.title || r.label)}"><span class="lbl">${esc(r.label)}</span>
    <span class="track"><span class="fill" style="display:block;width:${(100 * r.value) / m}%"></span></span>
    <span class="val">${esc(fmt(r.value, r))}</span></div>`).join("")}</div>`;
}
function sparkline(values, { min = 0, max = 7, height = 70, labels = null } = {}) {
  if (!values || values.length < 2) return `<p class="muted small">${esc(L.notEnough)}</p>`;
  const w = 300, pad = 6, n = values.length;
  const x = (i) => pad + ((w - 2 * pad) * i) / (n - 1);
  const y = (v) => height - pad - ((height - 2 * pad) * (Math.min(max, Math.max(min, v)) - min)) / (max - min || 1);
  const d = values.map((v, i) => `${i ? "L" : "M"}${x(i).toFixed(1)},${y(v).toFixed(1)}`).join("");
  return `<svg class="spark" viewBox="0 0 ${w} ${height}" preserveAspectRatio="none" role="img" aria-label="${esc(labels || "")}">
    ${[0.25, 0.5, 0.75].map((f) => `<line x1="0" x2="${w}" y1="${pad + (height - 2 * pad) * f}" y2="${pad + (height - 2 * pad) * f}"/>`).join("")}
    <path class="area" d="${d}L${x(n - 1)},${height}L${x(0)},${height}Z"/><path class="line" d="${d}" vector-effect="non-scaling-stroke"/>
    <circle cx="${x(n - 1)}" cy="${y(values[n - 1])}" r="4"/></svg>`;
}
const BADGE_ICONS = { first: "👣", ten_right: "🎯", streak5: "🔥", no_hints: "🧠", level3: "⛰️", level5: "🏔️", explorer: "🧭", tester: "📋", winner: "🏆", learner: "📚" };
function badgesHTML(list) {
  return `<div class="badges">${list.map((b) => {
    const [name, desc] = L.badgeInfo[b.code] || [b.code, ""];
    return `<div class="badge ${b.earned ? "on" : ""}" title="${esc(desc)}"><span class="i">${BADGE_ICONS[b.code] || "🏅"}</span><b>${esc(name)}</b><small>${esc(desc)}</small></div>`;
  }).join("")}</div>`;
}
function podiumHTML(rows, { scoreLabel = (r) => r.points, big = false } = {}) {
  const top = [rows[1], rows[0], rows[2]];
  return `<div class="podium ${big ? "big-podium" : ""}">${top.map((r, i) => r ? `<div class="pl p${[2, 1, 3][i]}">
      ${avatar(r.avatar)}<span class="nm">${esc(r.name)}</span><span class="sc">${esc(scoreLabel(r))}</span>
      <div class="block">${[2, 1, 3][i]}</div></div>` : "<div></div>").join("")}</div>`;
}

applyA11y();
