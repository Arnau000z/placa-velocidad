"use strict";
/* The teacher console: the AI assistant's report, students, response times, errors and
   misconceptions, tests, games, and the class roster with PINs. The board computes the facts
   (insights.py); this page turns them into sentences in the teacher's language. */

const T = { classes: [], cid: Number(store.get("t_class")) || 0, ov: null, ovAt: 0, sort: store.get("t_sort") || "level" };
const famLabel = (f) => `«${f.topic}: ${(f.words || []).join(", ")}»`;
const LOGIT_HALF = Math.log(0.375 / 0.625);
const abilityToLevel = (a) => Math.min(7, Math.max(0, (a - LOGIT_HALF) / 0.7 + 3.5));
const studentLink = (s) => `<a href="#/teacher/student/${s.sid}">${esc(s.name)}</a>`;
const namesList = (list) => {
  const n = list.map(studentLink);
  return n.length <= 1 ? n.join("") : `${n.slice(0, -1).join(", ")} ${esc(L.and)} ${n[n.length - 1]}`;
};

function teacherLogout() {
  S.tt = ""; sess.set("tt", ""); T.ov = null;
  go("#/");
}

route(/^\/teacher(?:\/(summary|students|student|time|errors|skills|items|model|report|tests|test|games|class))?(?:\/(\d+))?$/, async (section = "summary", id) => {
  if (!S.tt) return teacherLogin();
  const cl = await tapi("t_class", { action: "list" });
  T.classes = cl.classes;
  if (!T.classes.some((c) => c.id === T.cid)) T.cid = (T.classes.find((c) => c.students.length) || T.classes[0] || {}).id || 0;
  const needsOv = !["class"].includes(section);
  if (needsOv) await loadOv();
  const nav = [["summary", "sparkles", L.navSummary], ["students", "users", L.navStudents], ["skills", "brain", L.navSkills], ["time", "timer", L.navTime],
               ["errors", "puzzle", L.navErrors], ["items", "microscope", L.navItems], ["model", "shield-check", L.navModel], ["report", "printer", L.navReport],
               ["tests", "clipboard-list", L.navTests], ["games", "gamepad-2", L.navGames], ["class", "school", L.navClass]];
  const alerts = T.ov ? Object.values(T.ov.students).filter((s) => s.alerts.some((a) => ["need_help", "guessing", "falling"].includes(a.code))).length : 0;
  const active = section === "student" ? "students" : section === "test" ? "tests" : section;
  const v = page(`<div class="console">
    <nav class="side" aria-label="${esc(L.teacherMode)}">
      <div class="cls"><label class="lab" for="clsSel">${esc(L.classLabel)}</label><select class="field" id="clsSel">${T.classes.map((c) =>
        `<option value="${c.id}" ${c.id === T.cid ? "selected" : ""}>${esc(c.name)} (${c.students.length})</option>`).join("")}</select></div>
      ${nav.map(([k, ic, name]) => `<a href="#/teacher/${k}" ${k === active ? 'aria-current="page"' : ""}>${icon(ic)}${esc(name)}
        ${k === "summary" && alerts ? `<span class="count">${alerts}</span>` : ""}</a>`).join("")}
    </nav><div id="tc"></div></div>`);
  $("#clsSel", v).onchange = (e) => { T.cid = Number(e.target.value); store.set("t_class", T.cid); T.ov = null; render(); };
  const tc = $("#tc", v);
  const views = { summary: vSummary, students: vStudents, student: vStudent, time: vTime, errors: vErrors, skills: vSkills, items: vItems,
                  model: vModel, report: vReport, tests: vTests, test: vTest, games: vGames, class: vClass };
  await views[section](tc, id);
  if (["summary", "students", "time", "errors", "skills"].includes(section)) {
    every(15000, async () => {
      if ($("dialog")) return;
      try { await loadOv(true); const y = window.scrollY; await views[section](tc, id); window.scrollTo(0, y); } catch {}
    });
  }
});

async function loadOv(force = false) {
  if (!force && T.ov && T.ov._cid === T.cid && T.ov._lang === S.lang && Date.now() - T.ovAt < 5000) return T.ov;
  T.ov = await tapi("t_overview", { class_id: T.cid, lang: S.lang });
  T.ov._cid = T.cid; T.ov._lang = S.lang; T.ovAt = Date.now();
  return T.ov;
}

function teacherLogin() {
  const v = page(`<section class="hero"><div><h1>${icon("graduation-cap")} ${esc(L.teacherAccess)}</h1><p>${esc(L.teacherIntro)}</p>
      <div class="row"><button class="btn big" id="pinBtn">${icon("key-round")} ${esc(L.enterPin)}</button><a class="btn ghost" href="#/">${icon("arrow-left")} ${esc(L.studentsDoor)}</a>
      <a class="btn ghost" href="como-funciona.html">${icon("info")} ${esc(L.howItWorks)}</a></div></div>
      <svg aria-hidden="true"><use href="#roo"/></svg></section>
    <div class="grid3">${[["🤖", L.sell1t, L.sell1], ["⏱️", L.sell2t, L.sell2], ["🔒", L.sell3t, L.sell3]].map(([i, t, d]) =>
      `<section class="card"><h2>${iconFor(i)} ${esc(t)}</h2><p class="muted" style="margin:0">${esc(d)}</p></section>`).join("")}</div>`);
  const ask = () => pinPad({
    title: L.teacherAccess, subtitle: L.pinWhere,
    submit: async (pin) => {
      const r = await api("teacher_login", { pin });
      if (r.error) return L.wrongPin;
      S.tt = r.token; sess.set("tt", r.token); T.classes = r.classes;
      setTimeout(render, 50);
      return "";
    },
  });
  $("#pinBtn", v).onclick = ask;
  ask();
}

// ---------------------------------------------------------------- the AI assistant's report
function insights(ov) {
  const studs = Object.values(ov.students);
  const out = [];
  const add = (tone, icon, html, acts = "") => out.push({ tone, icon, html, acts });
  if (!ov.answers) {
    add("info", "🌱", esc(studs.length ? L.aiNoData : L.aiNoStudents));
    return out;
  }
  const active = studs.filter((s) => s.answers > 0);
  add("info", "📊", L.aiOverview(ov.answers, pct(ov.correct, ov.answers), ov.today, active.length, studs.length));
  const by = {};
  for (const s of studs) for (const a of s.alerts) (by[a.code] = by[a.code] || []).push(s);
  if (by.need_help) add("bad", "🆘", L.aiNeedHelp(namesList(by.need_help)));
  if (by.guessing) add("warn", "🎲", L.aiGuessing(namesList(by.guessing)));
  if (by.falling) add("warn", "📉", L.aiFalling(namesList(by.falling)));
  if (by.hints) add("warn", "💡", L.aiHints(namesList(by.hints)));
  const w = ov.weak.find((x) => x.n >= 3 && x.rate >= 0.4);
  if (w) add("bad", "🧩", L.aiWeak(esc(famLabel(w)), Math.round(w.rate * 100), w.failers, w.students),
    `<button class="btn small" data-mk="${w.family}" data-lv="${w.example ? w.example.level : 2}">${icon("clipboard-list")} ${esc(L.makeTest)}</button><a class="btn small ghost" href="#/teacher/errors">${esc(L.seeDetail)}</a>`);
  const m = ov.hardest.find((x) => x.common_wrong_count >= 2);
  if (m) add("warn", "🧠", L.aiMisconception(m.common_wrong_count, esc(`${m.common_wrong}) ${m.common_wrong_value}`), esc(m.text.slice(0, 110)),
    esc(`${m.label}) ${m.value}`)));
  for (const g of ov.groups.slice(0, 2)) {
    const members = g.students.map((sid) => ov.students[sid]).filter(Boolean);
    add("info", "👥", L.aiGroup(namesList(members), esc(famLabel(g))),
      `<button class="btn small" data-mk="${g.family}" data-lv="${Math.max(0, Math.floor(Math.min(...members.map((s) => s.level ?? 3))))}">${icon("clipboard-list")} ${esc(L.makeTest)}</button>`);
  }
  if (ov.slow_families.length && ov.median_seconds) {
    const sf = ov.slow_families[0];
    add("info", "⏱️", L.aiSlow(esc(famLabel(sf)), fmtSecs(sf.median_s), fmtSecs(ov.median_seconds)), `<a class="btn small ghost" href="#/teacher/time">${esc(L.seeDetail)}</a>`);
  }
  const prof = Object.entries(ov.profiles);
  if (prof.length) {
    const txt = prof.sort((a, b) => b[1] - a[1]).map(([k, n]) => `${n} ${(L.profiles[k] || [k])[0]}`).join(" · ");
    add("info", "🧭", `${L.aiProfiles(esc(txt))}${ov.profiles.impulsive ? " " + esc(L.aiImpulsiveTip) : ""}${ov.profiles.stuck ? " " + esc(L.aiStuckTip) : ""}`);
  }
  if (by.ready_up) add("good", "🚀", L.aiReadyUp(namesList(by.ready_up)));
  if (by.rising) add("good", "📈", L.aiRising(namesList(by.rising)));
  if (ov.harder.length) add("info", "🎚️", L.aiHarder(ov.harder.length, ov.harder[0].level, fmtNum(ov.harder[0].felt_level, 1)));
  for (const x of ov.weak.filter((x) => x.prev_rate != null && Math.abs(x.rate - x.prev_rate) >= 0.15).slice(0, 2)) {
    const better = x.rate < x.prev_rate;
    add(better ? "good" : "warn", better ? "✅" : "⚠️", L.aiChange(esc(famLabel(x)), Math.round(x.prev_rate * 100), Math.round(x.rate * 100), better));
  }
  const idle = studs.filter((s) => !s.answers);
  if (idle.length && idle.length < studs.length) add("info", "💤", L.aiIdle(namesList(idle)));
  return out;
}
/* "What to do today": the few actions with the most impact, each with its button (teacher-dashboard research:
   lead with the decision, not with the data). */
function todayHTML(ov) {
  if (!ov.answers) return "";
  const studs = Object.values(ov.students);
  const acts = [];
  const urgent = studs.filter((s) => s.alerts.some((a) => ["need_help", "guessing", "falling"].includes(a.code)));
  if (urgent.length) acts.push({ text: L.actAttend(namesList(urgent.slice(0, 4))), btn: `<a class="btn small" href="#/teacher/student/${urgent[0].sid}">${icon("user-round")} ${esc(L.btnOpenFile)}</a>` });
  const m = ov.hardest.find((x) => x.common_wrong_count >= 2);
  if (m) acts.push({ text: L.actDiscuss(m.common_wrong_count, esc(`${m.common_wrong}) ${m.common_wrong_value}`), esc(m.text.slice(0, 70))),
                     btn: `<a class="btn small ghost" href="#/teacher/errors">${icon("eye")} ${esc(L.btnSee)}</a>` });
  const w = ov.weak.find((x) => x.n >= 3 && x.rate >= 0.4);
  if (w) acts.push({ text: L.actReinforce(esc(famLabel(w))),
                     btn: `<button class="btn small" data-mk="${w.family}" data-lv="${w.example ? w.example.level : 2}">${icon("clipboard-list")} ${esc(L.makeTest)}</button>` });
  const up = studs.filter((s) => s.alerts.some((a) => a.code === "ready_up"));
  if (up.length) acts.push({ text: L.actUp(namesList(up.slice(0, 4))), btn: `<a class="btn small ghost" href="#/teacher/student/${up[0].sid}">${icon("rocket")} ${esc(L.btnOpenFile)}</a>` });
  if (!acts.length) return "";
  return `<section class="card today" style="margin-bottom:18px"><div class="card-head"><h2>${icon("list-checks")} ${esc(L.todayTitle)}</h2>
    <span class="small muted">${esc(L.todaySub)}</span></div><ol>${acts.slice(0, 4).map((a) => `<li><p>${a.text}</p>${a.btn}</li>`).join("")}</ol></section>`;
}

function insightHTML(list) {
  return `<div class="stack">${list.map((i) => `<div class="insight ${i.tone}"><span class="ic-box" aria-hidden="true">${iconFor(i.icon)}</span>
    <div><p>${i.html}</p>${i.acts ? `<div class="acts">${i.acts}</div>` : ""}</div></div>`).join("")}</div>`;
}
function bindMakeTest(root) {
  root.addEventListener("click", (e) => {
    const b = e.target.closest("[data-mk]");
    if (b) testDialog({ family: Number(b.dataset.mk), level: Number(b.dataset.lv) });
  });
}

function kpis(ov) {
  const studs = Object.values(ov.studs || ov.students);
  const lv = studs.map((s) => s.level).filter((x) => x != null);
  const k = (ico, label, value, note = "") => `<div class="stat"><span class="k">${iconFor(ico)} ${esc(label)}</span><span class="v">${value}</span><span class="d">${esc(note)}</span></div>`;
  return `<div class="kpis">
    ${k("👥", L.kStudents, studs.length, L.kOnline(ov.online))}
    ${k("✍️", L.kAnswers, fmtNum(ov.answers), L.kToday(ov.today))}
    ${k("🎯", L.kAccuracy, pct(ov.correct, ov.answers), L.kAccNote)}
    ${k("⏱️", L.kTime, ov.median_seconds ? fmtSecs(ov.median_seconds) : "–", L.kTimeNote)}
    ${k("🧭", L.kLevel, lv.length ? fmtNum(lv.reduce((a, b) => a + b, 0) / lv.length, 1) : "–", L.kLevelNote)}</div>`;
}

async function vSummary(tc) {
  const ov = T.ov;
  const lv = [0, 1, 2, 3, 4, 5, 6, 7].map((l) => ov.levels[l] || 0);
  const dayNames = Array.from({ length: 7 }, (_, i) => new Date(Date.now() - (6 - i) * 86400000).toLocaleDateString(LOCALE[S.lang], { weekday: "short" }));
  tc.innerHTML = `<div class="page-head"><div><h1>${esc(L.navSummary)}</h1><p class="sub">${esc(className())} · <span class="live">${esc(L.live)}</span></p></div></div>
    ${kpis(ov)}
    ${todayHTML(ov)}
    <section class="card"><div class="ai-head"><span class="ai-orb" aria-hidden="true">${icon("sparkles")}</span><div><h2 style="margin:0">${esc(L.aiTitle)}</h2>
      <p class="small muted" style="margin:0">${esc(L.aiSub(ov.answers))}</p></div></div>${insightHTML(insights(ov))}</section>
    <div class="grid2" style="margin-top:18px">
      <section class="card"><h2>${icon("gauge")} ${esc(L.levelDist)}</h2>${bars(lv, lv.map((_, i) => `${i}`), { title: (i) => L.nStudentsAtLevel(lv[i], i) })}
        <p class="small muted" style="margin:8px 0 0">${esc(L.levelDistNote)}</p></section>
      <section class="card"><h2>${icon("chart-column")} ${esc(L.activity7)}</h2>${bars(ov.days, dayNames, { title: (i) => `${dayNames[i]}: ${ov.days[i]}` })}
        <p class="small muted" style="margin:8px 0 0">${esc(L.sources(ov.sources))}</p></section>
    </div>
    <details class="card" style="margin-top:18px"><summary>${icon("microscope")} ${esc(L.howAI)}</summary><div class="stack" style="margin-top:12px">${L.howAIList.map(([t, d]) =>
      `<div><b>${esc(t)}</b><p class="muted small" style="margin:2px 0 0">${esc(d)}</p></div>`).join("")}
      <p class="small muted">${esc(L.modelState(ov.model))}</p></div></details>`;
  bindMakeTest(tc);
}
const className = () => (T.classes.find((c) => c.id === T.cid) || {}).name || "";

// ---------------------------------------------------------------- students
function profileChip(p) {
  if (!p) return `<span class="muted small">–</span>`;
  const [name, desc] = L.profiles[p] || [p, ""];
  const tone = { confident: "good", thoughtful: "brand", stuck: "warn", impulsive: "bad", struggling: "bad" }[p] || "";
  return `<span class="chip ${tone} prof" title="${esc(desc)}">${esc(name)}</span>`;
}
const trendHTML = (t) => (t >= 0.3 ? `<span class="trend-up" title="${esc(L.rising)}">▲</span>` : t <= -0.3 ? `<span class="trend-down" title="${esc(L.falling)}">▼</span>` : "");
async function vStudents(tc) {
  const ov = T.ov;
  const studs = Object.values(ov.students);
  const keyf = {
    name: (s) => s.name.toLowerCase(), level: (s) => -(s.level ?? -1), acc: (s) => (s.answers ? s.acc10 : 2), answers: (s) => -s.answers,
    time: (s) => -(s.median_seconds ?? -1), alerts: (s) => -s.alerts.length,
  };
  const f = keyf[T.sort] || keyf.level;
  studs.sort((a, b) => (f(a) < f(b) ? -1 : f(a) > f(b) ? 1 : 0));
  const th = (k, label, cls = "") => `<th class="${cls}"><button data-sort="${k}">${esc(label)}${T.sort === k ? " ↓" : ""}</button></th>`;
  tc.innerHTML = `<div class="page-head"><div><h1>${esc(L.navStudents)}</h1><p class="sub">${esc(L.studentsSub)}</p></div><span class="spacer"></span>
      <button class="btn ghost small" id="csv">${icon("download")} CSV</button></div>
    ${studs.length ? `<div class="table-wrap"><table class="t"><thead><tr>${th("name", L.cStudent)}${th("level", L.cLevel, "num")}${th("acc", L.cRecent, "num")}
      ${th("answers", L.cAnswers, "num")}${th("time", L.cTime, "num")}<th>${esc(L.cProfile)}</th><th>${esc(L.cWeak)}</th>${th("alerts", L.cAlerts)}</tr></thead>
      <tbody>${studs.map((s) => `<tr class="click" data-sid="${s.sid}" tabindex="0"><td><span class="who">${avatar(s.avatar)}${esc(s.name)} ${s.online ? '<span class="dot on"></span>' : ""}</span></td>
        <td class="num">${s.level == null ? "–" : `${fmtNum(s.level, 1)} ${trendHTML(s.trend)}`}</td>
        <td class="num">${s.answers ? `${Math.round(s.acc10 * 100)}%` : "–"}</td><td class="num">${s.answers}</td>
        <td class="num">${s.median_seconds ? fmtSecs(s.median_seconds) : "–"}</td><td>${profileChip(s.profile)}</td>
        <td class="small">${s.weakest ? `${esc(s.weakest.topic)} <span class="muted">(${s.weakest.ok}/${s.weakest.n})</span>` : "–"}</td>
        <td>${s.alerts.map((a) => `<span title="${esc(L.alertNames[a.code] || a.code)}">${(L.alertNames[a.code] || "•").split(" ")[0]}</span>`).join(" ")}</td></tr>`).join("")}</tbody></table></div>`
      : `<div class="card empty"><span class="big">${icon("users")}</span><p>${esc(L.noStudentsYet)}</p><a class="btn" href="#/teacher/class">${esc(L.addStudents)}</a></div>`}
    <p class="small muted" style="margin-top:10px">${esc(L.studentsLegend)}</p>`;
  tc.onclick = (e) => {
    const s = e.target.closest("[data-sort]");
    if (s) { T.sort = s.dataset.sort; store.set("t_sort", T.sort); vStudents(tc); return; }
    const r = e.target.closest("[data-sid]");
    if (r) go(`#/teacher/student/${r.dataset.sid}`);
  };
  tc.onkeydown = (e) => { const r = e.target.closest("[data-sid]"); if (r && e.key === "Enter") go(`#/teacher/student/${r.dataset.sid}`); };
  $("#csv", tc)?.addEventListener("click", () => csv(`students-${className()}.csv`, [
    [L.cStudent, L.cLevel, L.cRecent, L.cAnswers, L.cTime, L.cProfile, L.cWeak, L.cAlerts],
    ...studs.map((s) => [s.name, s.level ?? "", s.answers ? Math.round(s.acc10 * 100) + "%" : "", s.answers, s.median_seconds ?? "",
      s.profile ? L.profiles[s.profile][0] : "", s.weakest ? famLabel(s.weakest) : "", s.alerts.map((a) => L.alertNames[a.code]).join("; ")])]));
}

function csv(name, rows) {
  const text = rows.map((r) => r.map((x) => `"${String(x ?? "").replace(/"/g, '""')}"`).join(",")).join("\r\n");
  const a = document.createElement("a");
  a.href = URL.createObjectURL(new Blob(["﻿" + text], { type: "text/csv;charset=utf-8" }));
  a.download = name.replace(/[^\w.-]+/g, "_");
  a.click();
  setTimeout(() => URL.revokeObjectURL(a.href), 1000);
}

function studentSentences(rep, name) {
  const out = [];
  const add = (tone, icon, html) => out.push({ tone, icon, html });
  if (!rep.answers) { add("info", "🌱", esc(L.sNoData(name))); return out; }
  add("info", "🧭", L.sLevel(esc(name), fmtNum(rep.level, 1), rep.answers, Math.round(rep.acc10 * 100)));
  if (rep.trend >= 0.5) add("good", "📈", esc(L.sRising));  // same thresholds as the alerts (insights.py)
  if (rep.trend <= -0.5) add("warn", "📉", esc(L.sFalling));
  if (rep.profile) { const [pn, pd] = L.profiles[rep.profile]; add(["stuck", "impulsive", "struggling"].includes(rep.profile) ? "warn" : "good", "⏱️", L.sProfile(esc(pn), esc(pd), rep.speed)); }
  if (rep.weakest) add("bad", "🧩", L.sWeak(esc(famLabel(rep.weakest)), rep.weakest.ok, rep.weakest.n));
  if (rep.strongest) add("good", "💪", L.sStrong(esc(famLabel(rep.strongest)), rep.strongest.ok, rep.strongest.n));
  if (rep.slowest) add("info", "🐢", L.sSlowest(esc(famLabel(rep.slowest)), fmtNum(rep.slowest.factor, 1)));
  if (rep.hints_per_answer >= 1) add("warn", "💡", L.sHints(fmtNum(rep.hints_per_answer, 1)));
  for (const m of rep.misconceptions) add("warn", "🧠", L.sMisc(esc(`${m.chose}) ${m.chose_value}`), m.others, esc(m.text.slice(0, 100)), esc(`${m.label}) ${m.value}`)));
  for (const a of rep.alerts) if (a.code === "ready_up") add("good", "🚀", esc(L.sReady));
  for (const a of rep.alerts) if (a.code === "guessing") add("warn", "🎲", esc(L.sGuess(a.seconds)));
  return out;
}

async function vStudent(tc, sid) {
  const d = await tapi("t_student", { sid, lang: S.lang });
  if (d.error) { go("#/teacher/students"); return; }
  const rep = d.report, st = d.student;
  const hist = rep.history.map(abilityToLevel);
  tc.innerHTML = `<div class="page-head"><a class="back" href="#/teacher/students" aria-label="${esc(L.back)}">${icon("arrow-left")}</a>${avatar(st.avatar)}
      <div><h1>${esc(st.name)}</h1><p class="sub">${esc(className())} · ${esc(L.lastSeen(ago(rep.last)))}</p></div><span class="spacer"></span>
      <button class="btn ghost small" id="newPin">${icon("key-round")} ${esc(L.newPin)}</button></div>
    <div class="stats">
      <div class="stat"><span class="k">${icon("gauge")} ${esc(L.cLevel)}</span><span class="v">${rep.level == null ? "–" : fmtNum(rep.level, 1)}</span><span class="d">${esc(L.levelModel)}</span></div>
      <div class="stat"><span class="k">${icon("target")} ${esc(L.cRecent)}</span><span class="v">${rep.answers ? Math.round(rep.acc10 * 100) + "%" : "–"}</span><span class="d">${esc(L.ofAnswers(rep.correct, rep.answers))}</span></div>
      <div class="stat"><span class="k">${icon("timer")} ${esc(L.cTime)}</span><span class="v">${rep.median_seconds ? fmtSecs(rep.median_seconds) : "–"}</span><span class="d">${rep.speed ? esc(L.speedVs(rep.speed)) : ""}</span></div>
      <div class="stat"><span class="k">${icon("star")} ${esc(L.points)}</span><span class="v">${fmtNum(d.stats.points)}</span><span class="d">${icon("trophy")} ${d.stats.wins} · 📖 ${d.stats.lessons}</span></div>
    </div>
    <div class="grid2" style="margin-top:16px">
      <section class="card"><div class="ai-head"><span class="ai-orb" aria-hidden="true">${icon("sparkles")}</span><h2 style="margin:0">${esc(L.aiAbout(st.name))}</h2></div>${insightHTML(studentSentences(rep, st.name))}</section>
      <div class="stack">
        <section class="card"><h2>${icon("trending-up")} ${esc(L.levelOverTime)}</h2>${sparkline(hist, { labels: L.levelOverTime })}<p class="small muted" style="margin:6px 0 0">${esc(L.levelOverTimeNote)}</p></section>
        <section class="card"><h2>${icon("target")} ${esc(L.practiceFor)}</h2>${rep.practice.length ? `<div class="list">${rep.practice.map((p) =>
          `<div class="item"><span class="chip brand">${esc(L.lvl)} ${p.level}</span><div class="grow small">${esc(p.text.slice(0, 150))}…</div></div>`).join("")}</div>
          <p class="small muted" style="margin:8px 0 0">${esc(L.practiceForNote)}</p>` : `<p class="muted">${esc(L.notEnough)}</p>`}</section>
        <section class="card"><h2>${icon("chart-column")} ${esc(L.bySource)}</h2><div class="chips">${Object.entries(rep.by_source).map(([k, n]) => `<span class="chip">${esc(L.sourceNames[k] || k)}: ${n}</span>`).join("") || "–"}</div></section>
      </div></div>
    ${d.analysis ? `<div class="grid2" style="margin-top:16px">
      <section class="card"><h2>${icon("target")} ${esc(L.successByLevel)}</h2>${bars(d.analysis.curve.map((p) => Math.round(p * 100)), d.analysis.curve.map((_, i) => `${i}`),
        { title: (i) => L.successAt(i, Math.round(d.analysis.curve[i] * 100)), fmt: (x) => `${x}%` })}
        <p class="small muted" style="margin:8px 0 0">${esc(L.successByLevelNote)}</p></section>
      <section class="card"><h2>${icon("triangle-alert")} ${esc(L.riskTitle)}: ${d.analysis.risk}/100</h2>${riskHTML(d.analysis)}
        <p class="small muted" style="margin:8px 0 0">${esc(L.riskNote)}</p></section></div>
    <section class="card" style="margin-top:16px"><h2>${icon("brain")} ${esc(L.skillsOf(st.name))}</h2>${skillBars(d.skills)}
      <p class="small muted" style="margin:8px 0 0">${esc(L.skillsNote)}</p></section>` : ""}
    <h2 class="section-title">${icon("clock")} ${esc(L.recentAnswers)}</h2>
    ${d.recent.length ? `<div class="table-wrap"><table class="t"><thead><tr><th></th><th>${esc(L.cProblem)}</th><th class="num">${esc(L.lvl)}</th><th class="num">${esc(L.cTime)}</th>
      <th>${esc(L.cSource)}</th><th class="num">${esc(L.cHints)}</th><th>${esc(L.cWhen)}</th></tr></thead><tbody>${d.recent.map((r) => `<tr><td>${r.correct ? "✅" : "❌"}</td>
      <td class="small">${esc(r.text)}…</td><td class="num">${r.level}</td><td class="num">${fmtSecs(r.seconds)}</td><td class="small">${esc(L.sourceNames[r.source] || r.source)}</td>
      <td class="num">${r.hints}</td><td class="small muted">${esc(ago(r.ts))}</td></tr>`).join("")}</tbody></table></div>` : `<p class="muted">${esc(L.noAnswersYet)}</p>`}
    ${d.tests.length ? `<h2 class="section-title">${icon("clipboard-list")} ${esc(L.testsDone)}</h2><div class="list">${d.tests.map((t) => `<div class="item"><span>${icon("file-text")}</span><div class="grow">
      <b>${esc(L.lvl)} ${t.level} · ${t.correct}/${t.n}</b><div class="small muted">${esc(when(t.started))}${t.test_id ? ` · ${esc(L.fromTeacher)}` : ""}</div></div>
      <span class="chip ${t.correct / t.n >= 0.6 ? "good" : "bad"}">${pct(t.correct, t.n)}</span></div>`).join("")}</div>` : ""}
    <section class="card" style="margin-top:16px"><h2>${icon("award")} ${esc(L.badges)}</h2>${badgesHTML(d.badges)}</section>`;
  $("#newPin", tc).onclick = async () => {
    if (!(await confirmBox(L.newPinQ(st.name), L.newPinWarn, L.newPin))) return;
    const r = await tapi("t_student_edit", { action: "pin", sid: st.id });
    pinCardsDialog([{ name: st.name, avatar: st.avatar, pin: r.pin }]);
  };
}

// ---------------------------------------------------------------- time
async function vTime(tc) {
  const ov = T.ov;
  const studs = Object.values(ov.students).filter((s) => s.median_seconds);
  studs.sort((a, b) => (b.speed ?? 0) - (a.speed ?? 0));
  const groups = {};
  for (const s of Object.values(ov.students)) if (s.profile) (groups[s.profile] = groups[s.profile] || []).push(s);
  tc.innerHTML = `<div class="page-head"><div><h1>${esc(L.navTime)}</h1><p class="sub">${esc(L.timeSub)}</p></div></div>
    <section class="card" style="margin-bottom:18px"><div class="ai-head"><span class="ai-orb" aria-hidden="true">${icon("timer")}</span><div><h2 style="margin:0">${esc(L.timeHow)}</h2>
      <p class="small muted" style="margin:0">${esc(L.timeHowText)}</p></div></div>
      <div class="chips"><span class="chip brand">${esc(L.classMedian)}: ${ov.median_seconds ? fmtSecs(ov.median_seconds) : "–"}</span></div></section>
    <div class="grid2">
      <section class="card"><h2>${icon("hourglass")} ${esc(L.slowFamilies)}</h2>${ov.slow_families.length ? hbars(ov.slow_families.map((f) =>
        ({ label: `${f.topic}: ${f.words.join(", ")}`, value: f.median_s, n: f.n })), { fmt: (x, r) => `${fmtSecs(x)} · ${r.n}` })
        + `<p class="small muted" style="margin:8px 0 0">${esc(L.slowFamiliesNote)}</p>` : `<p class="muted">${esc(L.notEnough)}</p>`}</section>
      <section class="card"><h2>${icon("hourglass")} ${esc(L.slowProblems)}</h2>${ov.slow_problems.length ? `<div class="list">${ov.slow_problems.map((p) => `<div class="item">
        <span class="chip warn">${fmtSecs(p.median_s)}</span><div class="grow small">${esc(p.text)}…<div class="tiny muted">${esc(L.lvl)} ${p.level} · ${esc(L.nAnswers(p.n))}</div></div></div>`).join("")}</div>`
        : `<p class="muted">${esc(L.notEnough)}</p>`}</section>
    </div>
    <h2 class="section-title">${icon("gauge")} ${esc(L.profilesTitle)}</h2>
    <div class="grid3">${["confident", "thoughtful", "stuck", "impulsive", "struggling"].map((k) => `<section class="card"><h3>${profileChip(k)}</h3>
      <p class="small muted">${esc(L.profiles[k][1])}</p><p class="small" style="margin:0"><b>${esc(L.whatToDo)}</b> ${esc(L.profileTips[k])}</p>
      <p style="margin:8px 0 0">${(groups[k] || []).map(studentLink).join(", ") || `<span class="muted small">${esc(L.nobody)}</span>`}</p></section>`).join("")}</div>
    <h2 class="section-title">${icon("users")} ${esc(L.speedByStudent)}</h2>
    ${studs.length ? `<div class="table-wrap"><table class="t"><thead><tr><th>${esc(L.cStudent)}</th><th class="num">${esc(L.cTime)}</th><th class="num">${esc(L.cSpeed)}</th>
      <th>${esc(L.cProfile)}</th><th>${esc(L.cSlowest)}</th></tr></thead><tbody>${studs.map((s) => `<tr class="click" data-sid="${s.sid}">
      <td><span class="who">${avatar(s.avatar)}${esc(s.name)}</span></td><td class="num">${fmtSecs(s.median_seconds)}</td>
      <td class="num">${s.speed ? esc(L.speedVs(s.speed)) : "–"}</td><td>${profileChip(s.profile)}</td>
      <td class="small">${s.slowest ? `${esc(s.slowest.topic)} (×${fmtNum(s.slowest.factor, 1)})` : "–"}</td></tr>`).join("")}</tbody></table></div>`
      : `<p class="muted">${esc(L.notEnough)}</p>`}`;
  tc.onclick = (e) => { const r = e.target.closest("[data-sid]"); if (r) go(`#/teacher/student/${r.dataset.sid}`); };
}

// ---------------------------------------------------------------- errors and misconceptions
async function vErrors(tc) {
  const ov = T.ov;
  tc.innerHTML = `<div class="page-head"><div><h1>${esc(L.navErrors)}</h1><p class="sub">${esc(L.errorsSub)}</p></div><span class="spacer"></span>
      <button class="btn ghost small" id="snap">${icon("camera")} ${esc(L.snapshot)}</button><button class="btn ghost small" id="csvF">${icon("download")} CSV</button></div>
    <p class="small muted">${esc(ov.snapshots.length ? L.snapInfo(ov.snapshots.length, when(ov.snapshots[0].ts)) : L.noSnap)}</p>
    <h2 class="section-title">${icon("puzzle")} ${esc(L.weakFamilies)}</h2>
    ${ov.weak.length ? ov.weak.map((w) => `<article class="fam-card"><div class="row between"><b>${esc(famLabel(w))}</b>
        <span class="chip ${w.rate >= 0.5 ? "bad" : w.rate >= 0.3 ? "warn" : "good"}">${Math.round(w.rate * 100)}% ${esc(L.errorsWord)}</span></div>
      <div class="meter" style="margin:8px 0"><i style="width:${Math.round(w.rate * 100)}%;background:var(--bad)"></i></div>
      <p class="small muted" style="margin:0">${esc(L.errorsOf(w.wrong, w.n))} · ${esc(L.failersOf(w.failers, w.students))}
        ${w.prev_rate != null ? ` · ${w.rate < w.prev_rate ? "▼" : w.rate > w.prev_rate ? "▲" : "="} ${esc(L.vsSnap(Math.round(w.prev_rate * 100)))}` : ""}</p>
      ${w.example ? `<details style="margin-top:8px"><summary>${esc(L.mostFailed(w.example_fails))}</summary><p class="quote">${esc(w.example.text)}</p>
        <p class="small">${esc(L.rightAnswer)}: <b>${w.example.label}) ${esc(w.example.value)}</b></p>
        ${w.practice.length ? `<p class="small" style="margin:8px 0 4px"><b>${esc(L.toPractise)}</b></p><div class="list">${w.practice.map((p) =>
          `<div class="item small"><span class="chip brand">${esc(L.lvl)} ${p.level}</span><span class="grow">${esc(p.text.slice(0, 140))}…</span></div>`).join("")}</div>` : ""}</details>` : ""}
      <div class="acts" style="margin-top:8px"><button class="btn small" data-mk="${w.family}" data-lv="${w.example ? w.example.level : 2}">${icon("clipboard-list")} ${esc(L.makeTest)}</button></div></article>`).join("")
      : `<p class="muted">${esc(L.notEnough)}</p>`}
    <h2 class="section-title">${icon("brain")} ${esc(L.misconceptions)}</h2><p class="small muted">${esc(L.misconceptionsNote)}</p>
    ${ov.hardest.length ? `<div class="stack">${ov.hardest.map((h) => `<article class="fam-card"><div class="row between"><span class="chip brand">${esc(L.lvl)} ${h.level} · ${esc(h.topic)}</span>
      <span class="small muted">${esc(L.errorsOf(h.wrong, h.n))}</span></div><p class="quote">${esc(h.text)}</p>
      <div class="chips"><span class="chip bad">${esc(L.mostChosen)}: ${esc(h.common_wrong)}) ${esc(h.common_wrong_value)} (${h.common_wrong_count}×)</span>
      <span class="chip good">${esc(L.rightAnswer)}: ${esc(h.label)}) ${esc(h.value)}</span></div></article>`).join("")}</div>` : `<p class="muted">${esc(L.notEnough)}</p>`}
    <div class="grid2" style="margin-top:18px">
      <section class="card"><h2>${icon("trending-up")} ${esc(L.harderThan)}</h2>${calib(ov.harder)}</section>
      <section class="card"><h2>${icon("trending-down")} ${esc(L.easierThan)}</h2>${calib(ov.easier)}</section>
    </div><p class="small muted" style="margin-top:8px">${esc(L.calibNote)}</p>`;
  bindMakeTest(tc);
  $("#snap", tc).onclick = async () => { await tapi("t_snapshot", { class_id: T.cid, lang: S.lang }); toast(L.snapSaved, "good", "📸"); await loadOv(true); vErrors(tc); };
  $("#csvF", tc).onclick = () => csv(`families-${className()}.csv`, [[L.cFamily, L.cAnswers, L.errorsWord, "%", L.cStudents],
    ...ov.weak.map((w) => [famLabel(w), w.n, w.wrong, Math.round(w.rate * 100), `${w.failers}/${w.students}`])]);
}
const calib = (rows) => rows.length ? `<div class="list">${rows.map((r) => `<div class="item small"><span class="chip">${esc(L.lvl)} ${r.level} → ${fmtNum(r.felt_level, 1)}</span>
  <span class="grow">${esc(r.text)}…</span></div>`).join("")}</div>` : `<p class="muted">${esc(L.notEnough)}</p>`;

// ---------------------------------------------------------------- tests
function testDialog({ family = -1, level = 2 } = {}) {
  const fams = T.ov ? T.ov.families : [];
  const d = dialog(`<h2>${icon("clipboard-list")} ${esc(L.newTest)}</h2><form class="stack" id="tf">
    <div><label class="lab" for="tTitle">${esc(L.testTitle)}</label><input class="field" id="tTitle" required maxlength="60"
      value="${esc(family >= 0 ? `${L.reinforce}: ${(fams.find((f) => f.family === family) || {}).topic || ""}` : L.defaultTestTitle)}"></div>
    <div class="form-grid">
      <div><label class="lab" for="tLevel">${esc(L.level)}</label><select class="field" id="tLevel">${[0, 1, 2, 3, 4, 5, 6, 7].map((l) => `<option ${l === level ? "selected" : ""}>${l}</option>`).join("")}</select></div>
      <div><label class="lab" for="tN">${esc(L.questions)}</label><select class="field" id="tN">${[5, 8, 10, 15, 20].map((n) => `<option ${n === 8 ? "selected" : ""}>${n}</option>`).join("")}</select></div>
      <div><label class="lab" for="tMin">${esc(L.timeLimit)}</label><select class="field" id="tMin"><option value="0">${esc(L.noLimit)}</option>${[10, 15, 20, 30, 45].map((m) => `<option value="${m}">${m} min</option>`).join("")}</select></div>
    </div>
    <div><label class="lab" for="tFam">${esc(L.familyOpt)}</label><select class="field" id="tFam"><option value="-1">${esc(L.anyFamily)}</option>${fams.map((f) =>
      `<option value="${f.family}" ${f.family === family ? "selected" : ""}>${esc(`${f.topic}: ${f.words.join(", ")}`)} (${f.size})</option>`).join("")}</select>
      <p class="tiny muted" style="margin:4px 0 0">${esc(L.familyHelp)}</p></div>
    <div class="row" style="justify-content:flex-end"><button type="button" class="btn ghost" data-close>${esc(L.cancel)}</button><button class="btn">${esc(L.createTest)}</button></div></form>`);
  $("#tf", d).onsubmit = async (e) => {
    e.preventDefault();
    const r = await tapi("t_test_create", { class_id: T.cid, title: $("#tTitle", d).value, level: $("#tLevel", d).value, n: $("#tN", d).value,
                                           family: $("#tFam", d).value, minutes: $("#tMin", d).value });
    d.close();
    toast(L.testCreated, "good", "📋");
    T.ov = null;
    go("#/teacher/tests");
  };
}

async function vTests(tc) {
  const ov = T.ov;
  tc.innerHTML = `<div class="page-head"><div><h1>${esc(L.navTests)}</h1><p class="sub">${esc(L.testsSub)}</p></div><span class="spacer"></span>
      <button class="btn" id="newT">＋ ${esc(L.newTest)}</button></div>
    ${ov.tests.length ? `<div class="table-wrap"><table class="t"><thead><tr><th>${esc(L.testTitle)}</th><th class="num">${esc(L.lvl)}</th><th class="num">${esc(L.questions)}</th>
      <th>${esc(L.cWhen)}</th><th class="num">${esc(L.done)}</th><th>${esc(L.state)}</th><th></th></tr></thead><tbody>${ov.tests.map((t) => `<tr>
      <td><b>${esc(t.title)}</b>${t.minutes ? ` <span class="chip warn">${icon("timer")} ${t.minutes}′</span>` : ""}</td><td class="num">${t.level}</td><td class="num">${t.n}</td>
      <td class="small muted">${esc(when(t.created))}</td><td class="num">${t.results}</td>
      <td><button class="chip ${t.active ? "good" : ""}" data-toggle="${t.id}" data-active="${t.active}">${t.active ? "🟢 " + esc(L.open) : "⚪ " + esc(L.closed)}</button></td>
      <td><a class="btn small ghost" href="#/teacher/test/${t.id}">${esc(L.results)}</a></td></tr>`).join("")}</tbody></table></div>`
      : `<div class="card empty"><span class="big">${icon("clipboard-list")}</span><p>${esc(L.noTests)}</p></div>`}`;
  $("#newT", tc).onclick = () => testDialog({ level: Math.round(Object.values(ov.students).map((s) => s.level).filter((x) => x != null).reduce((a, b, _, arr) => a + b / arr.length, 0) || 2) });
  tc.onclick = async (e) => {
    const b = e.target.closest("[data-toggle]");
    if (!b) return;
    await tapi("t_test", { test_id: b.dataset.toggle, action: b.dataset.active === "1" ? "close" : "open", lang: S.lang });
    await loadOv(true); vTests(tc);
  };
}

async function vTest(tc, id) {
  const d = await tapi("t_test", { test_id: id, lang: S.lang });
  if (d.error) { go("#/teacher/tests"); return; }
  const t = d.test, res = d.results;
  const avg = res.length ? res.reduce((a, r) => a + r.correct / r.n, 0) / res.length : 0;
  tc.innerHTML = `<div class="page-head"><a class="back" href="#/teacher/tests" aria-label="${esc(L.back)}">${icon("arrow-left")}</a><div><h1>${icon("clipboard-list")} ${esc(t.title)}</h1>
      <p class="sub">${esc(L.lvl)} ${t.level} · ${esc(L.nQuestions(t.n))} · ${t.active ? esc(L.open) : esc(L.closed)}</p></div></div>
    <div class="stats"><div class="stat"><span class="k">${icon("users")} ${esc(L.done)}</span><span class="v">${res.length}</span></div>
      <div class="stat"><span class="k">${icon("target")} ${esc(L.avgScore)}</span><span class="v">${res.length ? Math.round(avg * 100) + "%" : "–"}</span></div></div>
    <div class="grid2" style="margin-top:16px">
      <section class="card"><h2>${icon("users")} ${esc(L.results)}</h2>${res.length ? `<div class="list" style="gap:4px">${res.map((r, i) => `<div class="board-row"><b class="muted">${i + 1}</b>
        ${avatar(r.avatar)}<span><b>${esc(r.name)}</b> <span class="small muted">· ${fmtNum(r.minutes, 1)} min</span></span><b class="num">${r.correct}/${r.n}</b></div>`).join("")}</div>`
        : `<p class="muted">${esc(L.noResults)}</p>`}</section>
      <section class="card"><h2>${icon("circle-help")} ${esc(L.perQuestion)}</h2>${hbars(d.questions.map((q, i) => ({ label: `${i + 1}. ${q.text}`, value: q.n ? q.correct / q.n : 0, n: q.n, c: q.correct, title: q.text })),
        { max: 1, fmt: (x, r) => (r.n ? `${Math.round(x * 100)}% · ${r.c}/${r.n}` : "–") })}</section></div>`;
}

// ---------------------------------------------------------------- games
async function vGames(tc) {
  const g = T.ov.games;
  tc.innerHTML = `<div class="page-head"><div><h1>${esc(L.navGames)}</h1><p class="sub">${esc(L.gamesSub)}</p></div></div>
    ${g.length ? `<div class="grid2">${g.map((x) => `<section class="card"><div class="row between"><b>${icon("gamepad-2")} ${esc(x.code)}</b><span class="small muted">${esc(when(x.created))} · ${esc(L.nRounds(x.rounds))}</span></div>
      <div class="list" style="gap:4px;margin-top:8px">${x.players.map((p, i) => `<div class="board-row"><b>${["🥇", "🥈", "🥉"][i] || i + 1}</b>
      ${avatar((T.classes.flatMap((c) => c.students).find((s) => s.id === p.sid) || {}).avatar)}<span>${esc(p.name)} <span class="small muted">· ${p.correct} ✓</span></span>
      <b class="num">${fmtNum(p.score)}</b></div>`).join("")}</div></section>`).join("")}</div>`
      : `<div class="card empty"><span class="big">${icon("gamepad-2")}</span><p>${esc(L.noGames)}</p></div>`}`;
}

// ---------------------------------------------------------------- class roster and PINs
function pinCardsDialog(cards) {
  const d = dialog(`<h2>${icon("key-round")} ${esc(L.pinCards)}</h2><p class="small muted">${esc(L.pinCardsNote)}</p>
    <div class="pin-cards">${cards.map((c) => `<div class="pin-card">${avatar(c.avatar)}<b>${esc(c.name)}</b><div class="tiny muted">${esc(className())}</div>
      <div class="code">${esc(c.pin)}</div></div>`).join("")}</div>
    <div class="row" style="justify-content:flex-end;margin-top:16px"><button class="btn ghost" id="printP">${icon("printer")} ${esc(L.print)}</button><button class="btn" data-close>${esc(L.doneBtn)}</button></div>`, { wide: true });
  $("#printP", d).onclick = () => {
    const w = window.open("", "_blank");
    if (!w) { toast(L.popupBlocked, "bad"); return; }
    w.document.write(`<!doctype html><meta charset="utf-8"><title>PIN</title><style>body{font-family:system-ui,sans-serif;margin:20px}
      .g{display:grid;grid-template-columns:repeat(3,1fr);gap:12px}.c{border:2px dashed #555;border-radius:14px;padding:14px;text-align:center;break-inside:avoid}
      .a{font-size:40px}.p{font:900 30px ui-monospace,monospace;letter-spacing:.2em}</style>
      <div class="g">${cards.map((c) => `<div class="c"><div class="a">${esc(c.avatar)}</div><b>${esc(c.name)}</b><div>${esc(className())}</div>
      <div class="p">${esc(c.pin)}</div><small>${esc(L.appName)}</small></div>`).join("")}</div>`);
    w.document.close(); w.focus(); w.print();
  };
}

async function vClass(tc) {
  const cls = T.classes.find((c) => c.id === T.cid);
  tc.innerHTML = `<div class="page-head"><div><h1>${esc(L.navClass)}</h1><p class="sub">${esc(L.classSub)}</p></div></div>
    <div class="grid2">
      <section class="card stack"><h2>${icon("school")} ${esc(L.classes)}</h2>
        <div class="chips">${T.classes.map((c) => `<button class="chip" data-cls="${c.id}" aria-pressed="${c.id === T.cid}">${esc(c.name)} · ${c.students.length}</button>`).join("")}</div>
        <form class="row" id="newC"><input class="field" id="cName" placeholder="${esc(L.newClassPh)}" maxlength="40" style="flex:1;min-width:160px" required>
          <button class="btn">＋ ${esc(L.createClass)}</button></form>
        ${cls ? `<div class="row"><button class="btn ghost small" id="renC">${icon("pencil")} ${esc(L.rename)}</button>
          <button class="btn ghost small" id="delC" ${cls.students.length ? "disabled" : ""} title="${esc(L.deleteClassNote)}">${icon("trash-2")} ${esc(L.deleteClass)}</button></div>` : ""}</section>
      <section class="card stack"><h2>${icon("plus")} ${esc(L.addStudent)}</h2>
        <form class="row" id="addS"><input class="field" id="sName" placeholder="${esc(L.studentNamePh)}" maxlength="24" style="flex:1;min-width:160px" required>
          <button class="btn" ${cls ? "" : "disabled"}>${esc(L.add)}</button></form>
        <p class="small muted" style="margin:0">${esc(L.addStudentNote)}</p>
        <div><button class="btn ghost small" id="allPins" ${cls && cls.students.length ? "" : "disabled"}>${icon("key-round")} ${esc(L.allPins)}</button></div></section>
    </div>
    <h2 class="section-title">${icon("users")} ${esc(cls ? cls.name : "")}</h2>
    ${cls && cls.students.length ? `<div class="table-wrap"><table class="t"><thead><tr><th>${esc(L.cStudent)}</th><th>PIN</th><th></th></tr></thead><tbody>${cls.students.map((s) => `<tr>
      <td><span class="who">${avatar(s.avatar)}${esc(s.name)}</span></td><td>${s.has_pin ? `<span class="chip good">${icon("check")} ${esc(L.hasPin)}</span>` : `<span class="chip warn">${esc(L.noPin)}</span>`}</td>
      <td style="text-align:right;white-space:nowrap"><button class="btn small ghost" data-pin="${s.id}">${icon("key-round")} ${esc(L.newPin)}</button>
        <button class="btn small ghost" data-ren="${s.id}">${icon("pencil")}</button><button class="btn small ghost" data-del="${s.id}" aria-label="${esc(L.delete)}">${icon("trash-2")}</button></td></tr>`).join("")}</tbody></table></div>`
      : `<div class="card empty"><span class="big">${icon("users", "lg")}</span><p>${esc(L.emptyClass)}</p></div>`}`;
  const reload = async (r) => { T.classes = r.classes || (await tapi("t_class", { action: "list" })).classes; T.ov = null; vClass(tc); };
  $("#newC", tc).onsubmit = async (e) => {
    e.preventDefault();
    const r = await tapi("t_class", { action: "create", name: $("#cName", tc).value });
    T.cid = r.id; store.set("t_class", T.cid); toast(L.classCreated, "good", "🏫"); render();
  };
  $("#addS", tc).onsubmit = async (e) => {
    e.preventDefault();
    const name = $("#sName", tc).value.trim();
    const r = await tapi("t_student_edit", { action: "add", class_id: T.cid, name });
    if (r.error) { toast(L.nameTaken, "bad"); return; }
    await reload(r);
    const s = r.classes.flatMap((c) => c.students).find((x) => x.id === r.sid);
    pinCardsDialog([{ name, avatar: s ? s.avatar : "", pin: r.pin }]);
    $("#sName", tc)?.focus();
  };
  $("#renC", tc)?.addEventListener("click", async () => {
    const name = await promptBox(L.renameClass, cls.name);
    if (name) await reload(await tapi("t_class", { action: "rename", class_id: T.cid, name }));
  });
  $("#delC", tc)?.addEventListener("click", async () => {
    if (!(await confirmBox(L.deleteClassQ(cls.name), L.cannotUndo, L.deleteClass, { danger: true }))) return;
    const r = await tapi("t_class", { action: "delete", class_id: T.cid });
    if (r.error) { toast(L.deleteClassNote, "bad"); return; }
    T.cid = 0; store.set("t_class", 0); await reload(r);
  });
  $("#allPins", tc)?.addEventListener("click", async () => {
    if (!(await confirmBox(L.allPinsQ, L.allPinsWarn, L.allPins))) return;
    const cards = [];
    for (const s of cls.students) {
      const r = await tapi("t_student_edit", { action: "pin", sid: s.id });
      cards.push({ name: s.name, avatar: s.avatar, pin: r.pin });
    }
    await reload();
    pinCardsDialog(cards);
  });
  tc.onclick = async (e) => {
    const c = e.target.closest("[data-cls]");
    if (c) { T.cid = Number(c.dataset.cls); store.set("t_class", T.cid); render(); return; }
    const p = e.target.closest("[data-pin]"), rn = e.target.closest("[data-ren]"), dl = e.target.closest("[data-del]");
    const el = p || rn || dl;
    if (!el) return;
    const sid = Number(el.dataset.pin || el.dataset.ren || el.dataset.del);
    const s = cls && cls.students.find((x) => x.id === sid);
    if (!s) return;
    if (p) {
      if (s.has_pin && !(await confirmBox(L.newPinQ(s.name), L.newPinWarn, L.newPin))) return;
      const r = await tapi("t_student_edit", { action: "pin", sid });
      await reload(r);
      pinCardsDialog([{ name: s.name, avatar: s.avatar, pin: r.pin }]);
    } else if (rn) {
      const name = await promptBox(L.renameStudent, s.name);
      if (name) await reload(await tapi("t_student_edit", { action: "rename", sid, name }));
    } else if (dl) {
      if (!(await confirmBox(L.deleteStudentQ(s.name), L.deleteStudentWarn, L.delete, { danger: true }))) return;
      await reload(await tapi("t_student_edit", { action: "delete", sid }));
      toast(L.deleted, "", "🗑️");
    }
  };
}

function promptBox(title, value = "") {
  return new Promise((resolve) => {
    let out = null;
    const d = dialog(`<h2>${esc(title)}</h2><form id="pf"><input class="field" id="pv" value="${esc(value)}" maxlength="40" required>
      <div class="row" style="justify-content:flex-end;margin-top:14px"><button type="button" class="btn ghost" data-close>${esc(L.cancel)}</button>
      <button class="btn">${esc(L.save)}</button></div></form>`, { onClose: () => resolve(out) });
    const input = $("#pv", d);
    input.focus(); input.select();
    $("#pf", d).onsubmit = (e) => { e.preventDefault(); out = input.value.trim(); d.close(); };
  });
}

// ================================================================ the complete analysis
/* Diverging colour for "better or worse than the model expected": orange below, blue above, grey near 0.
   Text always stays in ink colours; the cell colour only carries the sign and size. */
function divColor(rel, n = 9) {
  const t = Math.max(-1, Math.min(1, rel / 0.25)) * (n < 3 ? 0.45 : 1);  // fewer than 3 answers: paler, weak evidence
  if (Math.abs(t) < 0.12) return "var(--surface-3)";
  return `color-mix(in srgb, var(${t < 0 ? "--div-neg" : "--div-pos"}) ${Math.round(18 + 52 * Math.abs(t))}%, var(--surface))`;
}
const famShort = (f) => `${f.topic.split(/[,:(]/)[0]}: ${(f.words || []).slice(0, 2).join(", ")}`;
const signed = (x, d = 2) => `${x > 0 ? "+" : ""}${fmtNum(x, d)}`;

function skillBars(skills) {
  const rows = skills.filter((s) => s.n);
  if (!rows.length) return `<p class="muted">${esc(L.notEnough)}</p>`;
  return `<div class="hbars">${rows.sort((a, b) => a.rel - b.rel).map((s) => `<div class="hbar div" title="${esc(famLabel(s))}: ${s.right}/${s.n}">
    <span class="lbl">${esc(famShort(s))}</span><span class="track div"><span class="mid"></span>
    <span class="fill" style="${s.rel < 0 ? "right:50%" : "left:50%"};width:${Math.min(50, Math.abs(s.rel) / 0.25 * 50)}%;background:${s.rel < 0 ? "var(--div-neg)" : "var(--div-pos)"}"></span></span>
    <span class="val">${signed(s.rel)} · ${s.right}/${s.n}</span></div>`).join("")}</div>`;
}

function riskHTML(a) {
  if (!a.factors.length) return `<p class="muted" style="margin:0">${icon("circle-check")} ${esc(L.noRisk)}</p>`;
  return `<div class="chips">${a.factors.map((f) => `<span class="chip ${f.points >= 25 ? "bad" : "warn"}">${esc(L.riskFactors[f.code] ? L.riskFactors[f.code](f.value) : f.code)} · +${f.points}</span>`).join("")}</div>`;
}

function heatmapHTML(an, ov) {
  const fams = an.matrix.families;
  const studs = Object.keys(an.roster).map(Number).filter((s) => Object.keys(an.matrix.cells[s] || {}).length)
    .sort((a, b) => (an.students[b].level ?? -1) - (an.students[a].level ?? -1));
  if (!fams.length || !studs.length) return `<p class="muted">${esc(L.notEnough)}</p>`;
  return `<div class="table-wrap heat"><table class="t heat"><thead><tr><th>${esc(L.cStudent)}</th><th class="num">${esc(L.cLevel)}</th>
    ${fams.map((f, i) => `<th class="hc" title="${esc(famLabel(f))}">F${i + 1}</th>`).join("")}</tr></thead><tbody>
    ${studs.map((s) => `<tr><td><a class="who" href="#/teacher/student/${s}">${avatar(an.roster[s].avatar)}${esc(an.roster[s].name)}</a></td>
      <td class="num">${an.students[s].level == null ? "–" : fmtNum(an.students[s].level, 1)}</td>
      ${fams.map((f) => { const c = (an.matrix.cells[s] || {})[f.family];
        return c ? `<td class="hcell" style="background:${divColor(c.rel, c.n)}" title="${esc(an.roster[s].name)} · ${esc(famLabel(f))}: ${c.right}/${c.n} (${signed(c.rel)})">${c.right}/${c.n}</td>`
                 : `<td class="hcell empty">·</td>`; }).join("")}</tr>`).join("")}
    <tr class="sum"><td><b>${esc(L.classWord)}</b></td><td></td>${fams.map((f) => `<td class="hcell" style="background:${divColor(f.relative)}"
      title="${esc(famLabel(f))}: ${signed(f.relative)}">${signed(f.relative)}</td>`).join("")}</tr></tbody></table></div>
    <div class="legend-div" aria-hidden="true"><span>${esc(L.belowExpected)}</span><i></i><span>${esc(L.aboveExpected)}</span><span class="muted">· ${esc(L.paleNote)}</span></div>
    <ol class="fam-legend">${fams.map((f, i) => `<li><b>F${i + 1}</b> ${esc(famLabel(f))} <span class="muted small">(${f.n})</span></li>`).join("")}</ol>`;
}

function groupsHTML(an) {
  const g = an.groups;
  if (!g.k) return `<p class="muted">${esc(L.groupsNotEnough)}</p>`;
  const strength = g.silhouette >= 0.5 ? L.silStrong : g.silhouette >= 0.25 ? L.silMedium : L.silWeak;
  return `<p class="small muted">${esc(L.groupsHow(g.students_used, g.k, fmtNum(g.silhouette, 2)))} ${esc(strength)}</p>
    <div class="grid3">${g.groups.map((x, i) => `<section class="card flat"><h3>${esc(L.groupN(i + 1))} · ${esc(L.lvl)} ${fmtNum(x.level, 1)}</h3>
      <div class="chips" style="margin-bottom:8px">${x.students.map((s) => `<a class="chip" href="#/teacher/student/${s}">${esc(an.roster[s].avatar)} ${esc(an.roster[s].name)}</a>`).join("")}</div>
      ${x.needs.length ? `<p class="small" style="margin:0 0 4px"><b>${esc(L.groupNeeds)}</b> ${x.needs.map((f) => esc(famLabel(f))).join(" · ")}</p>` : ""}
      ${x.strengths.length ? `<p class="small" style="margin:0"><b>${esc(L.groupStrengths)}</b> ${x.strengths.map((f) => esc(famLabel(f))).join(" · ")}</p>` : ""}
      ${x.needs.length ? `<div class="acts" style="margin-top:8px"><button class="btn small" data-mk="${x.needs[0].family}" data-lv="${Math.max(0, Math.floor(x.level))}">${icon("clipboard-list")} ${esc(L.makeTest)}</button></div>` : ""}
      </section>`).join("")}</div>`;
}

function riskListHTML(an) {
  const list = Object.entries(an.students).filter(([, a]) => a.risk > 0).sort((a, b) => b[1].risk - a[1].risk);
  if (!list.length) return `<p class="muted">${icon("circle-check")} ${esc(L.noRiskClass)}</p>`;
  return `<div class="list">${list.map(([s, a]) => `<div class="item"><span class="chip ${a.risk >= 40 ? "bad" : "warn"}" style="min-width:58px;justify-content:center">${a.risk}</span>
    <a class="who" href="#/teacher/student/${s}" style="min-width:150px">${avatar(an.roster[s].avatar)}${esc(an.roster[s].name)}</a>
    <div class="grow">${riskHTML(a)}</div></div>`).join("")}</div>`;
}

let ANALYSIS = null;
async function loadAnalysis() {
  ANALYSIS = await tapi("t_analysis", { class_id: T.cid, lang: S.lang });
  return ANALYSIS;
}

async function vSkills(tc) {
  const an = await loadAnalysis();
  tc.innerHTML = `<div class="page-head"><div><h1>${esc(L.navSkills)}</h1><p class="sub">${esc(L.skillsSub)}</p></div></div>
    <section class="card"><div class="ai-head"><span class="ai-orb" aria-hidden="true">${icon("sparkles")}</span><div><h2 style="margin:0">${esc(L.skillsMap)}</h2>
      <p class="small muted" style="margin:0">${esc(L.skillsMapHow)}</p></div></div>${heatmapHTML(an, T.ov)}</section>
    <section class="card" style="margin-top:18px"><div class="ai-head"><span class="ai-orb" aria-hidden="true">${icon("sparkles")}</span><div><h2 style="margin:0">${esc(L.aiGroups)}</h2>
      <p class="small muted" style="margin:0">${esc(L.aiGroupsHow)}</p></div></div>${groupsHTML(an)}</section>
    <section class="card" style="margin-top:18px"><h2>${icon("triangle-alert")} ${esc(L.riskTitle)}</h2><p class="small muted">${esc(L.riskNote)}</p>${riskListHTML(an)}</section>`;
  bindMakeTest(tc);
}

const FLAG_TONE = { negative: "bad", trap: "warn", too_easy: "good", too_hard: "bad" };
function itemHTML(i) {
  const d = i.discrimination;
  return `<article class="fam-card"><div class="row between"><span class="chip brand">${esc(L.lvl)} ${i.level} · ${esc(i.topic)}</span>
      <span class="small muted">${esc(L.nAnswers(i.n))} · ${Math.round(i.p_value * 100)}% ${esc(L.rightWord)}</span></div>
    <p class="quote">${esc(i.text)}…</p>
    <div class="row" style="gap:8px">${i.flags.map((f) => `<span class="chip ${FLAG_TONE[f]}" title="${esc(L.flagHelp[f])}">${esc(L.flagNames[f])}</span>`).join("")}
      <span class="chip ${d == null ? "" : d >= 0.3 ? "good" : d >= 0.1 ? "" : "bad"}" title="${esc(L.discHelp)}">${esc(L.discrimination)}: ${d == null ? "–" : signed(d)}</span>
      <span class="chip good">${esc(L.rightAnswer)}: ${esc(i.label)}) ${esc(i.value)}</span></div>
    ${i.distractors.length ? `<ul class="small" style="margin:8px 0 0;padding-left:18px">${i.distractors.map((x) => `<li>${esc(L.distractorLine(x.letter, i.options[x.letter] ?? "", x.n, fmtNum(x.level, 1)))}
      ${x.stronger_than_right ? `<b class="trend-down"> ${esc(L.strongerThanRight)}</b>` : ""}</li>`).join("")}</ul>` : ""}</article>`;
}

async function vItems(tc) {
  const an = await loadAnalysis();
  const s = an.items_summary;
  const flagged = an.items.filter((i) => i.flags.length), rest = an.items.filter((i) => !i.flags.length);
  tc.innerHTML = `<div class="page-head"><div><h1>${esc(L.navItems)}</h1><p class="sub">${esc(L.itemsSub)}</p></div></div>
    <section class="card" style="margin-bottom:18px"><div class="ai-head"><span class="ai-orb" aria-hidden="true">${icon("microscope")}</span><div><h2 style="margin:0">${esc(L.itemsHow)}</h2>
      <p class="small muted" style="margin:0">${esc(L.discHelp)}</p></div></div>
      <div class="chips"><span class="chip brand">${esc(L.itemsAnalysed(s.analysed))}</span>
      <span class="chip">${esc(L.discrimination)} ${esc(L.meanWord)}: ${s.mean_discrimination == null ? "–" : fmtNum(s.mean_discrimination, 2)}</span>
      <span class="chip ${s.flagged ? "warn" : "good"}">${esc(L.itemsFlagged(s.flagged))}</span></div></section>
    ${flagged.length ? `<h2 class="section-title">${icon("triangle-alert")} ${esc(L.itemsToReview)}</h2><div class="stack">${flagged.map(itemHTML).join("")}</div>` : ""}
    <h2 class="section-title">${icon("clipboard-list")} ${esc(L.itemsOthers)}</h2>
    ${rest.length ? `<div class="stack">${rest.slice(0, 15).map(itemHTML).join("")}</div>` : `<p class="muted">${esc(L.notEnough)}</p>`}`;
}

function calibrationSVG(cal) {
  const W = 310, H = 300, P = 48, x = (v) => P + v * (W - P - 10), y = (v) => H - P - v * (H - P - 10);
  const maxN = Math.max(...cal.map((c) => c.n), 1);
  return `<svg viewBox="0 0 ${W} ${H}" class="calib" role="img" aria-label="${esc(L.calibration)}">
    ${[0, 0.25, 0.5, 0.75, 1].map((t) => `<line class="grid" x1="${x(0)}" x2="${x(1)}" y1="${y(t)}" y2="${y(t)}"/><text x="${P - 6}" y="${y(t) + 4}" text-anchor="end">${t * 100}%</text>
      <text x="${x(t)}" y="${H - P + 16}" text-anchor="middle">${t * 100}%</text>`).join("")}
    <line class="diag" x1="${x(0)}" y1="${y(0)}" x2="${x(1)}" y2="${y(1)}"/>
    <path class="line" d="${cal.map((c, i) => `${i ? "L" : "M"}${x(c.predicted).toFixed(1)},${y(c.observed).toFixed(1)}`).join("")}"/>
    ${cal.map((c) => `<circle cx="${x(c.predicted)}" cy="${y(c.observed)}" r="${4 + 6 * Math.sqrt(c.n / maxN)}"><title>${esc(L.calibPoint(Math.round(c.predicted * 100), Math.round(c.observed * 100), c.n))}</title></circle>`).join("")}
    <text x="${(W + P) / 2}" y="${H - 2}" text-anchor="middle" class="ax">${esc(L.predictedAxis)}</text>
    <text x="10" y="${(H - P) / 2}" text-anchor="middle" class="ax" transform="rotate(-90 10 ${(H - P) / 2})">${esc(L.observedAxis)}</text></svg>`;
}

function evalTable(ev) {
  const row = (k, name) => `<tr class="${k === "model" ? "best" : ""}"><td><b>${esc(name)}</b></td><td class="num">${fmtNum(ev[k].auc, 3)}</td>
    <td class="num">${fmtNum(ev[k].brier, 3)}</td><td class="num">${fmtNum(ev[k].logloss, 3)}</td><td class="num">${Math.round(ev[k].accuracy * 100)}%</td></tr>`;
  return `<div class="table-wrap"><table class="t"><thead><tr><th>${esc(L.modelCol)}</th><th class="num">AUC ↑</th><th class="num">Brier ↓</th>
    <th class="num">Log-loss ↓</th><th class="num">${esc(L.accHeader)} ↑</th></tr></thead><tbody>
    ${row("model", L.mIRT)}${row("level_only", L.mLevel)}${row("student_accuracy", L.mStudent)}</tbody></table></div>`;
}

async function vModel(tc) {
  const m = await tapi("t_model", { class_id: T.cid });
  const ev = m.all;
  const tr = m.translations && m.translations.stats;
  const block = (icon, title, body) => `<section class="card"><div class="ai-head"><span class="ai-orb" aria-hidden="true">${iconFor(icon)}</span>
    <h2 style="margin:0">${esc(title)}</h2></div>${body}</section>`;
  tc.innerHTML = `<div class="page-head"><div><h1>${esc(L.navModel)}</h1><p class="sub">${esc(L.modelSub)}</p></div></div>
    <div class="stack">
    ${block("📈", L.mAbilityTitle, ev.enough ? `<p>${L.mAbilityText(ev.n, fmtNum(ev.model.auc, 2), fmtNum(ev.level_only.auc, 2), fmtNum(ev.student_accuracy.auc, 2), fmtNum(ev.ece * 100, 1))}</p>
      <div class="grid2" style="align-items:center">${evalTable(ev)}<div>${calibrationSVG(ev.calibration)}<p class="small muted" style="margin:0">${esc(L.calibNote2)}</p></div></div>
      <p class="small muted">${esc(L.mAbilityHow)}</p>` : `<p class="muted">${esc(L.mNotEnough(ev.n))}</p>`)}
    ${block("🧩", L.mFamiliesTitle, m.families ? `<p>${L.mFamiliesText(m.families.problems, m.families.families, fmtNum(m.families.within, 2), fmtNum(m.families.between, 2))}</p>
      <p class="small muted" style="margin:0">${esc(L.mFamiliesHow)}</p>` : `<p class="muted">–</p>`)}
    ${block("🌍", L.mTransTitle, tr ? `<p>${L.mTransText(tr.solutions, tr.accepted_by_lang.cat, tr.accepted_by_lang.esp, fmtNum(tr.cosine_median, 2), fmtNum(tr.cosine_unrelated_median, 2), fmtNum(tr.meaning_threshold, 2))}</p>
      <div class="chips">${Object.entries(tr.failed_checks).map(([k, n]) => `<span class="chip warn">${esc(L.checkNames[k] || k)}: ${n}</span>`).join("") || `<span class="chip good">0</span>`}</div>
      <p class="small muted" style="margin:8px 0 0">${esc(m.translations.model)} · ${esc(m.translations.verifier)}</p>` : `<p class="muted">${esc(L.mTransNone)}</p>`)}
    ${block("💡", L.mHintsTitle, `<p>${L.mHintsText(m.hints.shown, m.hints.leaked_shown, m.hints.generated, m.hints.withheld)}</p><p class="small muted" style="margin:0">${esc(L.mHintsRef)}</p>`)}
    ${block("⏱️", L.mTimeTitle, `<p style="margin:0">${L.mTimeText(m.timed_answers)}</p>`)}
    ${block("📝", L.mReportTitle, `<p style="margin:0">${esc(L.mReportText)}</p>`)}
    ${block("⚖️", L.mLimitsTitle, `<ul style="margin:0;padding-left:18px">${L.mLimits.map((x) => `<li>${esc(x)}</li>`).join("")}</ul>`)}
    </div>`;
}

function recommendation(s) {
  const codes = new Set(s.alerts.map((a) => a.code));
  if (!s.answers) return L.recNever;
  if (codes.has("need_help") || codes.has("guessing")) return L.recHelp(s.weakest ? famLabel(s.weakest) : "");
  if (codes.has("falling")) return L.recFalling;
  if (codes.has("hints")) return L.recHints;
  if (codes.has("ready_up")) return L.recUp;
  if (s.profile === "stuck") return L.recStuck;
  if (s.profile === "impulsive") return L.recImpulsive;
  if (s.weakest) return L.recWeak(famLabel(s.weakest));
  return L.recKeep;
}

async function vReport(tc) {
  const [an, m] = await Promise.all([loadAnalysis(), tapi("t_model", { class_id: T.cid })]);
  const ov = T.ov;
  const studs = Object.values(ov.students).sort((a, b) => a.name.localeCompare(b.name));
  const ev = m.all;
  const today = new Date().toLocaleDateString(LOCALE[S.lang], { dateStyle: "long" });
  tc.innerHTML = `<div class="page-head no-print"><div><h1>${esc(L.navReport)}</h1><p class="sub">${esc(L.reportSub)}</p></div><span class="spacer"></span>
      <button class="btn" id="printR">${icon("printer")} ${esc(L.printReport)}</button></div>
    <article class="report">
      <header class="rep-head"><svg aria-hidden="true"><use href="#roo"/></svg><div><h2 style="margin:0">${esc(L.reportTitle(className()))}</h2>
        <p class="muted small" style="margin:0">${esc(today)} · ${esc(L.reportBy)}</p></div></header>
      ${kpis(ov)}
      <h3>1. ${esc(L.aiTitle)}</h3>${insightHTML(insights(ov))}
      <h3>2. ${esc(L.skillsMap)}</h3><p class="small muted">${esc(L.skillsMapHow)}</p>${heatmapHTML(an, ov)}
      <h3>3. ${esc(L.aiGroups)}</h3>${groupsHTML(an)}
      <h3>4. ${esc(L.riskTitle)}</h3>${riskListHTML(an)}
      <h3>5. ${esc(L.navTime)}</h3><p>${esc(L.reportTime(ov.median_seconds ? fmtSecs(ov.median_seconds) : "–"))}</p>
        ${ov.slow_families.length ? hbars(ov.slow_families.slice(0, 5).map((f) => ({ label: `${f.topic}: ${f.words.join(", ")}`, value: f.median_s, n: f.n })), { fmt: (x, r) => `${fmtSecs(x)} · ${r.n}` }) : ""}
        <p class="small">${Object.entries(ov.profiles).map(([k, n]) => `${(L.profiles[k] || [k])[0]}: ${n}`).join(" · ")}</p>
      <h3>6. ${esc(L.itemsToReview)}</h3>${an.items.filter((i) => i.flags.length).slice(0, 5).map(itemHTML).join("") || `<p class="muted">${esc(L.noFlagged)}</p>`}
      <h3>7. ${esc(L.reportStudents)}</h3>
      <div class="table-wrap"><table class="t"><thead><tr><th>${esc(L.cStudent)}</th><th class="num">${esc(L.cLevel)}</th><th class="num">${esc(L.cRecent)}</th>
        <th class="num">${esc(L.cTime)}</th><th>${esc(L.cProfile)}</th><th class="num">${esc(L.riskShort)}</th><th>${esc(L.recommendationCol)}</th></tr></thead>
        <tbody>${studs.map((s) => `<tr><td><span class="who">${avatar(s.avatar)}${esc(s.name)}</span></td>
          <td class="num">${s.level == null ? "–" : `${fmtNum(s.level, 1)} ${trendHTML(s.trend)}`}</td><td class="num">${s.answers ? Math.round(s.acc10 * 100) + "%" : "–"}</td>
          <td class="num">${s.median_seconds ? fmtSecs(s.median_seconds) : "–"}</td><td>${profileChip(s.profile)}</td>
          <td class="num">${(an.students[s.sid] || {}).risk ?? "–"}</td><td class="small">${esc(recommendation(s))}</td></tr>`).join("")}</tbody></table></div>
      <h3>8. ${esc(L.navModel)}</h3>
      <p class="small">${ev.enough ? L.reportModel(ev.n, fmtNum(ev.model.auc, 2), fmtNum(ev.level_only.auc, 2), fmtNum(ev.ece * 100, 1)) : esc(L.mNotEnough(ev.n))}
        ${m.families ? " " + L.reportFamilies(fmtNum(m.families.within, 2), fmtNum(m.families.between, 2)) : ""}
        ${m.translations ? " " + L.reportTrans(m.translations.stats.accepted, m.translations.stats.translations) : ""}</p>
      <p class="tiny muted">${esc(L.reportFooter)}</p>
    </article>`;
  $("#printR", tc).onclick = () => window.print();
  bindMakeTest(tc);
}
