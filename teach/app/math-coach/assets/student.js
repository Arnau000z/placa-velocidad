"use strict";
/* The student side: pick your name and type your PIN, the hub, practice with the hint ladder,
   tests, live games with friends, learn step by step, and my progress. */

/* Mastery levels per topic, as Khan Academy shows them (Attempted, Familiar, Proficient, Mastered).
   Rules: mastered >= 85% with >= 6 answers; proficient >= 70% with >= 4; familiar >= 50%; otherwise attempted. */
const MASTERY = ["attempted", "familiar", "proficient", "mastered"];
function masteryOf(ok, n) {
  const a = n ? ok / n : 0;
  return a >= 0.85 && n >= 6 ? 3 : a >= 0.7 && n >= 4 ? 2 : a >= 0.5 ? 1 : 0;
}
function masteryIcon(level) {
  const C = 2 * Math.PI * 12;  // a ring that fills a quarter per level
  return `<svg class="mlevel ${MASTERY[level]}" viewBox="0 0 30 30" aria-hidden="true"><circle class="ring" cx="15" cy="15" r="12"/>
    ${level ? `<circle cx="15" cy="15" r="12" fill="none" stroke="${level === 3 ? "var(--good)" : "var(--brand)"}" stroke-width="3"
      stroke-dasharray="${(C * (level + 1)) / 4} ${C}" transform="rotate(-90 15 15)" stroke-linecap="round"/>` : ""}
    ${level === 3 ? `<path d="m10 15.5 3.2 3.2 6.8-7" fill="none" stroke="var(--good)" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"/>` : `<circle class="fill" cx="15" cy="15" r="${2 + level * 1.6}"/>`}</svg>`;
}
function masteryHTML(byTopic) {
  const rows = Object.entries(byTopic).map(([t, [ok, n]]) => ({ t, ok, n, lv: masteryOf(ok, n) })).sort((a, b) => b.lv - a.lv || b.n - a.n);
  if (!rows.length) return `<p class="muted">${esc(L.noAnswersYet)}</p>`;
  const count = MASTERY.map((_, i) => rows.filter((r) => r.lv === i).length);
  return `<p class="small" style="margin-top:0"><b>${esc(L.masterySummary(count[2] + count[3], rows.length))}</b></p>
    <div class="mastery">${rows.map((r) => `<div class="mastery-row" title="${esc(r.t)}: ${r.ok}/${r.n}">${masteryIcon(r.lv)}<span>${esc(r.t)}</span>
      <span class="lvl-name">${esc(L.masteryLevels[MASTERY[r.lv]])}</span><span class="small muted num">${r.ok}/${r.n}</span></div>`).join("")}</div>
    <div class="mastery-legend">${MASTERY.map((m, i) => `<span>${masteryIcon(i)}${esc(L.masteryLevels[m])}</span>`).join("")}</div>
    <p class="tiny muted" style="margin:8px 0 0">${esc(L.masteryNote)}</p>`;
}

const explanationHTML = (text, lang = "eng") => text
  ? `<div class="explain"><p style="margin:0">${esc(text)}</p>${S.lang !== "eng" && lang === "eng" ? `<p class="tiny muted" style="margin:6px 0 0">${esc(L.inEnglish)}</p>` : ""}</div>`
  : `<p class="muted small">${esc(L.noExplanation)}</p>`;

// ================================================================ login: who are you?
route(/^\/$/, async () => {
  if (S.token) { go("#/home"); return; }
  if (!S.info) S.info = await api("info").catch(() => null);
  let data = await api("classes");
  let cid = Number(store.get("class")) || 0;
  const v = page(`<section class="hero"><div><h1>${esc(L.whoAreYou)}</h1><p>${esc(L.loginIntro)}</p></div>
      <svg aria-hidden="true"><use href="#roo"/></svg></section>
    <div class="class-tabs" role="tablist" id="classTabs"></div>
    <div class="roster" id="roster"></div>
    <div class="teacher-door row" style="justify-content:center"><a class="btn ghost" href="#/teacher">${icon("graduation-cap")} ${esc(L.iAmTeacher)}</a>
      <a class="btn ghost" href="como-funciona.html">${icon("info")} ${esc(L.howItWorks)}</a></div>`);
  function draw() {
    const classes = data.classes.filter((c) => c.students.length);
    if (!classes.length) {
      $("#classTabs", v).innerHTML = "";
      $("#roster", v).outerHTML = `<div class="card empty" id="roster"><span class="big">${icon("school")}</span><h2>${esc(L.noStudentsYet)}</h2><p>${esc(L.noStudentsHelp)}</p></div>`;
      return;
    }
    if (!classes.some((c) => c.id === cid)) cid = classes[0].id;
    $("#classTabs", v).innerHTML = classes.length > 1 ? classes.map((c) =>
      `<button class="class-tab" role="tab" aria-selected="${c.id === cid}" data-c="${c.id}">${esc(c.name)} <span class="muted small">· ${c.students.length}</span></button>`).join("") : "";
    const cls = classes.find((c) => c.id === cid);
    $("#roster", v).innerHTML = cls.students.map((s) => `<button class="student-card" data-s="${s.id}" ${s.has_pin ? "" : "disabled"}
        style="--hue:${hue(s.id)}" aria-label="${esc(s.name)}">
        ${s.online ? `<span class="dot on" title="${esc(L.online)}"></span>` : ""}${avatar(s.avatar)}<b>${esc(s.name)}</b>
        ${s.has_pin ? "" : `<span class="tiny muted">${esc(L.askPin)}</span>`}</button>`).join("");
  }
  draw();
  v.addEventListener("click", (e) => {
    const tab = e.target.closest("[data-c]");
    if (tab) { cid = Number(tab.dataset.c); store.set("class", cid); Sound.play("click"); draw(); return; }
    const card = e.target.closest("[data-s]");
    if (!card) return;
    const s = data.classes.flatMap((c) => c.students).find((x) => x.id === Number(card.dataset.s));
    Sound.play("click");
    pinPad({
      title: L.hello(s.name), subtitle: L.typePin, av: s.avatar,
      submit: async (pin) => {
        const r = await api("login", { sid: s.id, pin });
        if (r.error) return r.locked ? L.locked(r.locked) : L.wrongPin;
        S.token = r.token; sess.set("token", r.token); S.me = null; S.badges = null;
        if (r.student.lang) { S.lang = r.student.lang; store.set("lang", S.lang); }
        Sound.play("join");
        setTimeout(() => go("#/home"), 50);
        return "";
      },
    });
  });
  every(15000, async () => { try { data = await api("classes"); if (!$("dialog")) draw(); } catch {} });
});

// ================================================================ the hub
route(/^\/home$/, async () => {
  const me = await refreshMe();
  renderHeader();
  const st = me.stats, name = me.student.name.split(" ")[0];
  const est = st.est_level;
  const greet = st.answered === 0 ? L.firstTime : st.streak >= 3 ? L.onFire(st.streak) : L.welcomeBack;
  const v = page(`
    <section class="card welcome">
      ${avatar(me.student.avatar)}
      <div><h1>${esc(L.hi(name))}</h1><p>${esc(greet)}</p></div>
      <div class="lvl-box">${est == null ? `<span class="small">${esc(L.levelUnknown)}</span>` : `
        <div class="row between"><span class="small">${esc(L.yourLevel)}</span><b>${fmtNum(est, 1)}</b></div>
        <div class="meter" style="margin:6px 0"><i style="width:${Math.round((est % 1) * 100)}%"></i></div>
        <span class="tiny">${esc(est >= 7 ? L.topLevel : L.toNext(Math.floor(est) + 1))}</span>`}</div>
    </section>
    <div class="stats">
      <div class="stat"><span class="k">${icon("star")} ${esc(L.points)}</span><span class="v">${fmtNum(st.points)}</span></div>
      <div class="stat"><span class="k">${icon("target")} ${esc(L.accuracy)}</span><span class="v">${pct(st.correct, st.answered)}</span><span class="d">${esc(L.ofAnswers(st.correct, st.answered))}</span></div>
      <div class="stat"><span class="k">${icon("flame")} ${esc(L.streak)}</span><span class="v">${st.streak}</span><span class="d">${esc(L.best(st.best_streak))}</span></div>
      <div class="stat"><span class="k">${icon("trophy")} ${esc(L.wins)}</span><span class="v">${st.wins}</span><span class="d">${esc(L.lessonsDone(st.lessons))}</span></div>
    </div>
    <nav class="tiles" aria-label="${esc(L.activities)}">
      <a class="tile practice" href="#/practice"><span class="go">${icon("chevron-right")}</span><span class="tile-icon">${icon("mountain")}</span><b>${esc(L.practice)}</b><span>${esc(L.practiceDesc)}</span></a>
      <a class="tile test" href="#/test"><span class="go">${icon("chevron-right")}</span><span class="tile-icon">${icon("file-text")}</span><b>${esc(L.test)}</b><span>${esc(L.testDesc)}</span></a>
      <a class="tile game" href="#/game"><span class="go">${icon("chevron-right")}</span><span class="tile-icon">${icon("gamepad-2")}</span><b>${esc(L.game)}</b><span>${esc(L.gameDesc)}</span></a>
      <a class="tile learn" href="#/learn"><span class="go">${icon("chevron-right")}</span><span class="tile-icon">${icon("book-open")}</span><b>${esc(L.learn)}</b><span>${esc(L.learnDesc)}</span></a>
    </nav>
    <div id="liveBoxes" class="grid2"></div>
    <div class="grid2" style="margin-top:18px">
      <section class="card"><div class="card-head"><h2>${icon("award")} ${esc(L.badges)}</h2><a href="#/me" class="small">${esc(L.seeAll)}</a></div>${badgesHTML(me.badges)}</section>
      <section class="card"><div class="card-head"><h2>${icon("trophy")} ${esc(L.ranking)}</h2><span class="muted small" id="onlineN"></span></div><div id="rankBox"></div></section>
    </div>`);
  function live(me) {
    const boxes = [];
    if (me.tests.length) boxes.push(`<section class="card"><h2>${icon("clipboard-list")} ${esc(L.teacherTests)}</h2><div class="list">${me.tests.map((t) => `
      <div class="item"><span style="font-size:1.6rem">${icon("file-text")}</span><div class="grow"><div class="t">${esc(t.title)}</div>
      <div class="small muted">${esc(L.lvl)} ${t.level} · ${esc(L.nQuestions(t.n))}${t.minutes ? ` · ⏱ ${t.minutes} min` : ""}</div></div>
      <a class="btn small" href="#/test/t/${t.id}">${esc(L.start)}</a></div>`).join("")}</div></section>`);
    if (me.rooms.length) boxes.push(`<section class="card"><h2>${icon("gamepad-2")} ${esc(L.openRooms)}</h2><div class="list">${me.rooms.map((r) => `
      <div class="item"><span class="chip" style="font-family:var(--mono);font-size:1rem">${esc(r.code)}</span><div class="grow">
      <div class="t">${esc(L.roomOf(r.host))}</div><div class="small muted">${esc(L.nPlayers(r.players))} · ${esc(L.nRounds(r.rounds))}</div></div>
      <button class="btn small" data-join="${esc(r.code)}">${esc(L.join)}</button></div>`).join("")}</div></section>`);
    $("#liveBoxes", v).innerHTML = boxes.join("");
    $("#liveBoxes", v).style.gridTemplateColumns = boxes.length === 1 ? "1fr" : "";
  }
  live(me);
  v.addEventListener("click", async (e) => {
    const b = e.target.closest("[data-join]");
    if (!b) return;
    const r = await my("room_join", { code: b.dataset.join });
    if (r.error) { toast(r.error === "started" ? L.roomStarted : L.roomGone, "bad"); return; }
    go(`#/game/${r.code}`);
  });
  async function rank() {
    const r = await my("leaderboard");
    $("#onlineN", v).textContent = L.nOnline(r.online);
    $("#rankBox", v).innerHTML = r.rows.length ? podiumHTML(r.rows, { scoreLabel: (x) => `${fmtNum(x.points)} ${L.pts}` }) +
      r.rows.slice(3, 10).map((x) => `<div class="rank-row ${x.me ? "me" : ""}"><span class="r">${x.rank}</span>${avatar(x.avatar)}
        <span><b>${esc(x.name)}</b> ${x.online ? '<span class="dot on"></span>' : ""}</span><span class="p">${fmtNum(x.points)}</span></div>`).join("")
      : `<p class="muted">${esc(L.noRanking)}</p>`;
  }
  await rank();
  every(8000, async () => { try { live(await refreshMe()); renderHeader(); await rank(); } catch {} });
}, { student: true });

// ================================================================ practice: adaptive trainer + hint ladder
route(/^\/practice$/, async () => {
  const SESSION = 10;
  const P = { problem: null, answered: false, next: null, sel: null, done: Number(sess.get("session_done")) || 0 };
  const v = page(`<div class="page-head"><a class="back" href="#/home" aria-label="${esc(L.back)}">${icon("arrow-left")}</a>
      <div><h1>${icon("mountain")} ${esc(L.practice)}</h1><p class="sub">${esc(L.practiceSub)}</p></div><span class="spacer"></span>
      <span class="chip sun" id="ptsChip"></span><span class="chip" id="streakChip"></span>
      <select class="field" id="lvlSel" style="width:auto" aria-label="${esc(L.changeLevel)}"><option value="">${esc(L.changeLevel)}</option>
        ${[0, 1, 2, 3, 4, 5, 6, 7].map((l) => `<option value="${l}">${esc(L.lvl)} ${l}</option>`).join("")}</select></div>
    <div class="session" title="${esc(L.sessionHelp)}"><span class="small muted">${esc(L.session)}</span>
      <div class="meter" role="progressbar" aria-valuemin="0" aria-valuemax="${SESSION}" id="sessBar"><i></i></div><b id="sessN"></b></div>
    <div class="play">
      <section class="card" id="pcard" aria-live="polite"></section>
      <aside class="card"><h2>${icon("lightbulb")} ${esc(L.ladder)}</h2><p class="small muted">${esc(L.ladderHelp)}</p><div class="ladder" id="rungs"></div><div id="hints"></div></aside>
    </div>`);
  const stats = (s) => {
    $("#ptsChip", v).textContent = `⭐ ${fmtNum(s.points)} ${L.pts}`;
    $("#streakChip", v).textContent = `🔥 ${s.streak}`;
    $("#streakChip", v).classList.toggle("hidden", s.streak < 2);
    if (S.me) { S.me.stats = s; renderHeader(); }
  };
  const session = () => {
    $("#sessN", v).textContent = `${P.done}/${SESSION}`;
    $("i", $("#sessBar", v)).style.width = `${(100 * P.done) / SESSION}%`;
    $("#sessBar", v).setAttribute("aria-valuenow", P.done);
  };
  function pick(letter) {
    if (P.answered) return;
    P.sel = letter;
    $$("#pcard .opt", v).forEach((b) => b.classList.toggle("sel", b.dataset.letter === letter));
    Sound.play("click");
    idleBar();
  }
  const idleBar = () => checkbar({ title: "", sub: esc(P.sel ? L.readyToCheck : L.pickAnswer), button: L.check, disabled: !P.sel,
                                   onClick: () => answer(P.sel) });
  function show(p) {
    P.problem = p; P.answered = false; P.next = null; P.sel = null;
    $("#pcard", v).innerHTML = `<div class="problem-meta"><span class="chip brand">${esc(L.lvl)} ${p.level} ${levelStars(p.level)}</span>
        <span class="chip sun">+${p.worth} ${esc(L.pts)}</span>${p.reason && L.reasons[p.reason] ? `<span class="small muted">${esc(L.reasons[p.reason])}</span>` : ""}
        <span class="spacer"></span><button class="icon-btn" id="readBtn" title="${esc(L.readAloud)}" aria-label="${esc(L.readAloud)}">${icon("volume-2")}</button></div>
      <p class="question">${esc(p.text)}</p>${optionsHTML(p.options)}<div id="fb"></div>
      <p class="small muted keys-help">${L.keysHelp}</p>`;
    $("#readBtn", v).onclick = () => speak(`${p.text}. ${Object.entries(p.options).map(([k, x]) => `${k}: ${x}`).join(". ")}`);
    $$("#pcard .opt", v).forEach((b) => (b.onclick = () => pick(b.dataset.letter)));
    $("#hints", v).innerHTML = "";
    rungs();
    session();
    idleBar();
  }
  function rungs() {
    const used = P.problem ? P.problem.rung : 0;
    $("#rungs", v).innerHTML = L.rungs.map((name, i) => {
      const n = i + 1, state = n <= used ? "used" : n === used + 1 ? "next" : "";
      const dis = !P.problem || P.answered || n !== used + 1;
      return `<button class="rung ${state}" data-r="${n}" ${dis ? "disabled" : ""}><span class="n">${n <= used ? "✓" : n}</span><span>${esc(name)}</span>
        <span class="cost">${esc(L.rungCost[i])}</span></button>`;
    }).join("");
    $$(".rung", v).forEach((b) => (b.onclick = () => (b.dataset.r === "4" ? askSolution() : hint())));
  }
  function hintCard(title, html) {
    const d = document.createElement("div");
    d.className = "hintcard";
    d.innerHTML = `<h4>${esc(title)}</h4>${html}`;
    $("#hints", v).append(d);
    d.scrollIntoView({ behavior: reducedMotion() ? "auto" : "smooth", block: "nearest" });
    return d;
  }
  async function hint() {
    if (!P.problem || P.answered || P.problem.rung >= 3) return;
    P.problem.rung += 1; rungs();
    const r = await my("hint");
    if (r.rung === 1) {
      const p = r.problem;
      hintCard(L.r1, `<p class="tiny muted">${esc(L.lvl)} ${p.level} · ${esc(r.topic)}</p><p>${esc(p.text)}</p>
        <p class="small muted">${Object.entries(p.options).map(([k, x]) => `${k}) ${esc(x)}`).join(" · ")}</p>
        <p><b>${esc(L.answer)}: ${p.label}) ${esc(p.value)}</b></p>${explanationHTML(p.explanation, p.explanation_lang)}`);
    } else if (r.rung === 2) {
      hintCard(L.r2, `<p><b>${esc(r.topic)}</b></p><p style="margin:0">${esc(r.method)}</p>`);
    } else if (r.rung === 3) {
      const box = hintCard(L.r3, `<p class="muted"><span class="typing"><span></span><span></span><span></span></span> <span class="msg">${esc(L.thinking)}</span></p>`);
      pollHint(box);
    }
    Sound.play("hint");
  }
  function pollHint(box) {
    let id = null;
    const tick = async () => {
      let r;
      try { r = await my("hint_status"); } catch { clearInterval(id); return; }
      if (r.pending) { const m = $(".msg", box); if (m) m.textContent = r.ahead > 0 ? L.queue(r.ahead) : `${L.thinking} ${r.waited ?? ""} s`; return; }
      clearInterval(id);
      const res = r.result || {};
      const body = res.hint ? `<p style="font-size:1.08rem">${esc(res.hint)}</p>` : res.error ? `<p>${esc(L.modelError)}</p>`
        : `<p>${esc(L.hintWithheld)}</p><p>${esc(res.fallback || "")}</p>`;
      box.innerHTML = `<h4>${esc(L.r3)}</h4>${body}<p class="tiny muted" style="margin:0">${res.cached ? "⚡ " : ""}${res.seconds ?? ""} s</p>`;
      say(res.hint || "");
      Sound.play("hint");
    };
    tick();
    id = every(1000, tick);
  }
  async function askSolution() {
    if (!P.problem || P.answered) return;
    if (!(await confirmBox(L.solutionQ, L.solutionWarn, L.showIt))) return;
    const r = await my("solution");
    if (r.error) return;
    P.problem.rung = 4; P.problem.solution_shown = true; rungs();
    hintCard(L.r4, `<p><b>${r.label}) ${esc(r.value)}</b></p>${explanationHTML(r.explanation, r.explanation_lang)}
      ${r.has_lesson ? `<p style="margin:8px 0 0"><a href="#/learn/${encodeURIComponent(r.problem_id)}">${icon("book-open")} ${esc(L.learnIt)}</a></p>` : ""}`);
  }
  async function answer(letter) {
    if (!P.problem || P.answered || !letter) return;
    P.answered = true; rungs();
    $$("#pcard .opt", v).forEach((b) => (b.disabled = true));
    const r = await my("answer", { letter });
    if (r.error) { P.answered = false; return; }
    $$("#pcard .opt", v).forEach((b) => {
      b.classList.remove("sel");
      if (b.dataset.letter === r.label) b.classList.add("good");
      else if (b.dataset.letter === letter) b.classList.add("bad");
    });
    const up = r.next_reason === "up";
    P.done += 1;
    const sessionDone = P.done >= SESSION;
    if (r.correct) {
      Sound.play(up || sessionDone ? "levelup" : r.stats.streak >= 3 ? "streak" : "right");
      confetti();
    } else Sound.play("wrong");
    // the card keeps the worked solution; the bottom bar gives the verdict and the one next step
    $("#fb", v).innerHTML = `<div class="feedback ${r.correct ? "good" : "bad"}"><svg aria-hidden="true" class="${r.correct ? "bounce" : ""}"><use href="#roo"/></svg>
      <div><h3>${esc(r.correct ? L.howSolved : L.rightWas + " " + r.label + ") " + r.value)}</h3>
      ${explanationHTML(r.explanation, r.explanation_lang)}
      <p class="small muted" style="margin:10px 0 0">${icon("timer")} ${esc(L.youTook(fmtSecs(r.seconds)))}</p>
      ${r.has_lesson ? `<p style="margin:10px 0 0"><a class="btn small ghost" href="#/learn/${encodeURIComponent(r.problem_id)}">${icon("book-open")} ${esc(L.learnIt)}</a></p>` : ""}</div></div>`;
    const cheer = L.cheers[Math.floor(Math.random() * L.cheers.length)];
    const sub = r.correct
      ? [r.points ? `<span class="pop">+${r.points} ${esc(L.pts)}</span>` : "", r.stats.streak >= 2 ? esc(L.inARow(r.stats.streak)) : "",
         up ? esc(L.levelUp(r.next.level)) : ""].filter(Boolean).join(" · ")
      : `${esc(L.rightWas)} <b>${r.label}) ${esc(r.value)}</b>`;
    checkbar({ state: r.correct ? "good" : "bad", title: esc(r.correct ? cheer : L.almost), sub,
               button: sessionDone ? L.finishSession : L.continue, onClick: next });
    say(r.correct ? `${cheer} +${r.points}` : `${L.rightWas} ${r.label}`);
    P.next = r.next;
    stats(r.stats);
    session();
    noticeBadges(r.badges);
    if (sessionDone) {
      setTimeout(() => { toast(L.sessionComplete(SESSION), "sun", "🏁"); confetti(70); }, 400);
      P.done = 0;
    }
    sess.set("session_done", String(P.done));
  }
  function next() {
    if (!P.next) return;
    show(P.next);
    window.scrollTo({ top: 0, behavior: reducedMotion() ? "auto" : "smooth" });
    my("shown").catch(() => {});
  }
  $("#lvlSel", v).onchange = async (e) => {
    if (e.target.value === "") return;
    const r = await my("practice", { level: e.target.value, restart: 1 });
    e.target.value = "";
    show(r.problem); stats(r.stats);
  };
  S.keys = (e) => {
    const k = e.key.toUpperCase();
    if ("ABCDE".includes(k) && k.length === 1 && P.problem && !P.answered && P.problem.options[k]) pick(k);
    else if (k === "H") hint();
    else if (e.key === "Enter" && !P.answered && P.sel) answer(P.sel);
    else if (e.key === "Enter" && P.answered) next();
  };
  const r = await my("practice");
  show(r.problem); stats(r.stats);
}, { student: true });

// ================================================================ tests
let TEST = null;
route(/^\/test$/, async () => {
  const est = S.me.stats.est_level;
  let level = est == null ? 0 : Math.floor(est), n = 10;
  const v = page(`<div class="page-head"><a class="back" href="#/home" aria-label="${esc(L.back)}">${icon("arrow-left")}</a>
      <div><h1>${icon("file-text")} ${esc(L.test)}</h1><p class="sub">${esc(L.testSub)}</p></div></div>
    <section class="card stack">
      <div><h2>${esc(L.chooseLevel)}</h2><p class="small muted">${esc(est == null ? L.levelUnknown : L.recommended(Math.floor(est)))}</p><div class="levels" id="lv"></div></div>
      <div><h2>${esc(L.howMany)}</h2><div class="chips" id="nq">${[5, 10, 15].map((k) => `<button class="chip" data-n="${k}" aria-pressed="${k === n}">${esc(L.nQuestions(k))}</button>`).join("")}</div></div>
      <div class="row"><button class="btn big" id="go">${icon("play")} ${esc(L.startTest)}</button><span class="small muted">${esc(L.testRules)}</span></div>
    </section>
    ${S.me.recent_tests.length ? `<h2 class="section-title">${icon("list-checks")} ${esc(L.myTests)}</h2><div class="list">${S.me.recent_tests.map(testRow).join("")}</div>` : ""}`);
  const drawLv = () => ($("#lv", v).innerHTML = [0, 1, 2, 3, 4, 5, 6, 7].map((l) => `<button class="lvl ${est != null && l === Math.floor(est) ? "rec" : ""}"
      data-l="${l}" aria-pressed="${l === level}"><b>${l}</b><span>${levelStars(l)} · +${10 * (l + 1)} ${esc(L.pts)}</span></button>`).join(""));
  drawLv();
  $("#lv", v).onclick = (e) => { const b = e.target.closest("[data-l]"); if (b) { level = Number(b.dataset.l); drawLv(); Sound.play("click"); } };
  $("#nq", v).onclick = (e) => { const b = e.target.closest("[data-n]"); if (!b) return; n = Number(b.dataset.n); $$("[data-n]", v).forEach((x) => x.setAttribute("aria-pressed", x === b)); };
  $("#go", v).onclick = async () => {
    const r = await my("test_start", { level, n });
    if (r.error) return;
    TEST = { ...r, title: L.test, answered: 0, started: Date.now(), n: r.question.total };
    Sound.play("start");
    go("#/test/run");
  };
}, { student: true });

function testRow(t) {
  return `<a class="item" href="#/test/result/${t.id}" style="text-decoration:none;color:inherit"><span style="font-size:1.5rem">${t.correct / t.n >= 0.8 ? "🌟" : "📝"}</span>
    <div class="grow"><div class="t">${esc(L.lvl)} ${t.level} · ${t.correct}/${t.n}</div><div class="small muted">${esc(when(t.started))} · ⭐ ${t.points}</div></div>
    <span class="chip ${t.correct / t.n >= 0.6 ? "good" : "bad"}">${pct(t.correct, t.n)}</span></a>`;
}

route(/^\/test\/t\/(\d+)$/, async (id) => {
  const t = S.me.tests.find((x) => x.id === Number(id));
  if (!t) { toast(L.testClosed, "bad"); go("#/home"); return; }
  const v = page(`<div class="page-head"><a class="back" href="#/home" aria-label="${esc(L.back)}">${icon("arrow-left")}</a><div><h1>${icon("clipboard-list")} ${esc(t.title)}</h1>
      <p class="sub">${esc(L.fromTeacher)}</p></div></div>
    <section class="card stack" style="max-width:640px"><div class="chips"><span class="chip brand">${esc(L.lvl)} ${t.level}</span>
      <span class="chip">${esc(L.nQuestions(t.n))}</span>${t.minutes ? `<span class="chip warn">${icon("timer")} ${t.minutes} min</span>` : ""}</div>
      <p>${esc(L.testIntro)}</p><div><button class="btn big" id="go">${icon("play")} ${esc(L.startTest)}</button></div></section>`);
  $("#go", v).onclick = async () => {
    const r = await my("test_start", { test_id: id });
    if (r.error) { toast(L.testClosed, "bad"); return; }
    TEST = { ...r, title: t.title, answered: 0, started: Date.now(), n: r.question.total };
    Sound.play("start");
    go("#/test/run");
  };
}, { student: true });

route(/^\/test\/run$/, async () => {
  if (!TEST) { go("#/test"); return; }
  let chosen = null, busy = false;
  const v = page(`<div class="page-head"><div><h1>${icon("file-text")} ${esc(TEST.title)}</h1><p class="sub" id="qn"></p></div><span class="spacer"></span>
      <span class="chip"><span aria-hidden="true">${icon("timer")}</span> <span class="clock" id="clk">0:00</span></span></div>
    <div class="qbar" id="qbar" aria-hidden="true"></div><section class="card" id="qcard"></section>`);
  function draw() {
    const q = TEST.question;
    chosen = null;
    $("#qn", v).textContent = L.questionOf(q.index + 1, q.total);
    $("#qbar", v).innerHTML = Array.from({ length: q.total }, (_, i) => `<i class="${i < q.index ? "done" : i === q.index ? "now" : ""}"></i>`).join("");
    $("#qcard", v).innerHTML = `<div class="problem-meta"><span class="chip brand">${esc(L.lvl)} ${q.level}</span><span class="spacer"></span>
        <button class="icon-btn" id="readBtn" aria-label="${esc(L.readAloud)}">${icon("volume-2")}</button></div>
      <p class="question">${esc(q.text)}</p>${optionsHTML(q.options)}`;
    $("#readBtn", v).onclick = () => speak(`${q.text}. ${Object.entries(q.options).map(([k, x]) => `${k}: ${x}`).join(". ")}`);
    $$(".opt", v).forEach((b) => (b.onclick = () => pick(b.dataset.letter)));
    bar();
  }
  const bar = () => checkbar({ sub: esc(chosen ? L.testHelp : L.pickAnswer), disabled: !chosen, onClick: send,
                               button: TEST.question.index + 1 === TEST.question.total ? L.finish : L.confirmNext });
  function pick(letter) {
    chosen = letter;
    $$(".opt", v).forEach((b) => b.classList.toggle("sel", b.dataset.letter === letter));
    Sound.play("click");
    bar();
  }
  async function send() {
    if (!chosen || busy) return;
    busy = true;
    const r = await my("test_answer", { session: TEST.session, letter: chosen }).finally(() => (busy = false));
    if (r.error) return;
    if (r.done) {
      const sid = TEST.session; TEST = null;
      go(`#/test/result/${sid}`);
      return;
    }
    TEST.question = r.question;
    draw();
    window.scrollTo({ top: 0 });
  }
  const tick = () => {
    const el = (Date.now() - TEST.started) / 1000;
    if (TEST.minutes) {
      const left = TEST.minutes * 60 - el;
      $("#clk", v).textContent = left > 0 ? clock(left) : L.timeUp;
      $("#clk", v).classList.toggle("late", left < 60);
    } else $("#clk", v).textContent = clock(el);
  };
  S.keys = (e) => {
    const k = e.key.toUpperCase();
    if (k.length === 1 && "ABCDE".includes(k) && TEST.question.options[k]) pick(k);
    else if (e.key === "Enter") send();
  };
  draw(); tick();
  every(1000, () => TEST && tick());
}, { student: true });

route(/^\/test\/result\/(\d+)$/, async (sid) => {
  const r = await my("test_review", { session: sid });
  if (r.error) { go("#/test"); return; }
  const f = r.n ? r.correct / r.n : 0, C = 2 * Math.PI * 70;
  const msg = f >= 0.9 ? L.resultTop : f >= 0.6 ? L.resultGood : f >= 0.3 ? L.resultOk : L.resultLow;
  const v = page(`<div class="page-head"><a class="back" href="#/home" aria-label="${esc(L.back)}">${icon("arrow-left")}</a><div><h1>${icon("file-text")} ${esc(L.results)}</h1>
      <p class="sub">${esc(L.lvl)} ${r.level} · ${esc(L.nQuestions(r.n))}</p></div></div>
    <section class="card row" style="gap:28px;align-items:center">
      <div class="score-ring"><svg viewBox="0 0 160 160" aria-hidden="true"><circle cx="80" cy="80" r="70" fill="none" stroke="var(--surface-3)" stroke-width="14"/>
        <circle cx="80" cy="80" r="70" fill="none" stroke="${f >= 0.6 ? "var(--good)" : f >= 0.3 ? "var(--sun)" : "var(--bad)"}" stroke-width="14" stroke-linecap="round"
        stroke-dasharray="${C}" stroke-dashoffset="${C * (1 - f)}" style="transition:stroke-dashoffset 1s"/></svg>
        <div class="lab"><div><b>${r.correct}/${r.n}</b><span class="small muted">${pct(r.correct, r.n)}</span></div></div></div>
      <div class="grow" style="flex:1;min-width:220px"><h2>${esc(msg)}</h2>
        <div class="chips"><span class="chip sun">${icon("star")} +${r.points} ${esc(L.pts)}</span><span class="chip">${icon("timer")} ${esc(L.medianTime(fmtSecs(r.median_seconds)))}</span>
        ${r.est_level != null ? `<span class="chip brand">${icon("trending-up")} ${esc(L.yourLevel)} ${fmtNum(r.est_level, 1)}</span>` : ""}</div>
        ${r.weak.length ? `<p style="margin-top:12px"><b>${esc(L.toReview)}</b></p><div class="chips">${r.weak.map((w) =>
          `<span class="chip warn">${esc(w.topic)} · ${esc(w.words.join(", "))} (${w.ok}/${w.n})</span>`).join("")}</div>` : ""}
        <div class="row" style="margin-top:16px"><a class="btn" href="#/test">${esc(L.anotherTest)}</a><a class="btn ghost" href="#/home">${esc(L.home)}</a></div></div>
    </section>
    <h2 class="section-title">${icon("eye")} ${esc(L.review)}</h2>
    <div class="stack">${r.items.map((it, i) => `<article class="review-item ${it.correct ? "good" : "bad"}">
      <div class="row between"><b>${it.correct ? "✅" : "❌"} ${esc(L.questionN(i + 1))} · ${esc(L.lvl)} ${it.level}</b><span class="small muted">${icon("timer")} ${esc(fmtSecs(it.seconds))}</span></div>
      <p style="margin:8px 0">${esc(it.text)}</p>
      <p class="small">${esc(L.yourAnswer)}: <b>${it.answer}) ${esc(it.options[it.answer] ?? "")}</b>${it.correct ? "" : ` · ${esc(L.rightAnswer)}: <b>${it.label}) ${esc(it.value)}</b>`}</p>
      <details><summary>${esc(L.seeExplanation)}</summary>${explanationHTML(it.explanation, it.explanation_lang)}
        ${it.has_lesson ? `<p style="margin:8px 0 0"><a href="#/learn/${encodeURIComponent(it.id)}">${icon("book-open")} ${esc(L.learnIt)}</a></p>` : ""}</details></article>`).join("")}</div>`);
  if (f >= 0.8) { confetti(60); Sound.play("win"); } else Sound.play(f >= 0.5 ? "right" : "hint");
  try { noticeBadges((await refreshMe()).badges); renderHeader(); } catch {}
}, { student: true });

// ================================================================ live games with friends
route(/^\/game$/, async () => {
  const me = await refreshMe();
  const v = page(`<div class="page-head"><a class="back" href="#/home" aria-label="${esc(L.back)}">${icon("arrow-left")}</a>
      <div><h1>${icon("gamepad-2")} ${esc(L.game)}</h1><p class="sub">${esc(L.gameSub)}</p></div></div>
    <div class="grid2">
      <section class="card stack"><h2>${icon("sparkles")} ${esc(L.createRoom)}</h2>
        <div class="form-grid">
          <div><label class="lab" for="gRounds">${esc(L.rounds)}</label><select class="field" id="gRounds">${[3, 5, 6, 8, 10].map((k) => `<option ${k === 6 ? "selected" : ""}>${k}</option>`).join("")}</select></div>
          <div><label class="lab" for="gSecs">${esc(L.secondsPerQ)}</label><select class="field" id="gSecs">${[30, 45, 60, 90, 120].map((k) => `<option ${k === 60 ? "selected" : ""}>${k}</option>`).join("")}</select></div>
          <div><label class="lab" for="gLvl">${esc(L.level)}</label><select class="field" id="gLvl"><option value="-1">${esc(L.autoLevel)}</option>
            ${[0, 1, 2, 3, 4, 5, 6, 7].map((l) => `<option value="${l}">${esc(L.lvl)} ${l}</option>`).join("")}</select></div>
        </div>
        <p class="small muted" style="margin:0">${esc(L.gameRules)}</p>
        <div><button class="btn big" id="create" style="background:var(--game);box-shadow:none">${icon("sparkles")} ${esc(L.createRoom)}</button></div></section>
      <section class="card stack"><h2>${icon("key-round")} ${esc(L.joinRoom)}</h2>
        <form class="row" id="joinForm"><input class="field" id="code" maxlength="4" placeholder="ABCD" autocomplete="off"
          style="font-family:var(--mono);font-size:1.6rem;letter-spacing:.3em;text-transform:uppercase;max-width:200px" aria-label="${esc(L.roomCode)}">
          <button class="btn">${esc(L.join)}</button></form>
        <div id="openRooms">${me.rooms.length ? `<div class="list">${me.rooms.map((r) => `<div class="item"><span class="chip" style="font-family:var(--mono)">${esc(r.code)}</span>
          <div class="grow"><b>${esc(L.roomOf(r.host))}</b><div class="small muted">${esc(L.nPlayers(r.players))}</div></div>
          <button class="btn small" data-join="${esc(r.code)}">${esc(L.join)}</button></div>`).join("")}</div>` : `<p class="muted small">${esc(L.noRooms)}</p>`}</div>
      </section></div>`);
  $("#create", v).onclick = async () => {
    const r = await my("room_create", { rounds: $("#gRounds", v).value, seconds: $("#gSecs", v).value, level: $("#gLvl", v).value });
    if (!r.error) { Sound.play("join"); go(`#/game/${r.code}`); }
  };
  const join = async (code) => {
    const r = await my("room_join", { code });
    if (r.error) { toast(r.error === "started" ? L.roomStarted : L.roomGone, "bad"); return; }
    Sound.play("join"); go(`#/game/${r.code}`);
  };
  $("#joinForm", v).onsubmit = (e) => { e.preventDefault(); const c = $("#code", v).value.trim(); if (c.length === 4) join(c); };
  v.addEventListener("click", (e) => { const b = e.target.closest("[data-join]"); if (b) join(b.dataset.join); });
}, { student: true });

route(/^\/game\/([A-Za-z]{4})$/, async (code) => {
  code = code.toUpperCase();
  let key = "", lastPlayers = 0, revealed = "", ended = false, lastTick = -1;
  const v = page(`<div id="room"></div>`);
  const boardHTML = (s, gains = false) => `<div class="list" style="gap:4px">${s.players.map((p, i) => `<div class="board-row ${p.me ? "me" : ""}">
      <b class="muted">${i + 1}</b>${avatar(p.avatar)}<span><b>${esc(p.name)}</b> ${gains && p.last ? `<span class="gain">+${p.last}</span>` : ""}</span>
      <b class="num">${fmtNum(p.score)}</b></div>`).join("")}</div>`;
  const strip = (s) => s.players.map((p) => `<span class="av ${p.answered ? "yes" : ""}" title="${esc(p.name)}">${esc(p.avatar)}</span>`).join("");
  function full(s) {
    const room = $("#room", v);
    if (s.phase === "lobby") {
      room.innerHTML = `<div class="page-head"><button class="back" id="leave" aria-label="${esc(L.leave)}">${icon("arrow-left")}</button>
          <div><h1>${icon("gamepad-2")} ${esc(L.waitingRoom)}</h1><p class="sub">${esc(L.shareCode)}</p></div></div>
        <section class="card" style="text-align:center"><div class="room-code" aria-label="${esc(L.roomCode)} ${esc(s.code.split("").join(" "))}">${esc(s.code)}</div>
          <p class="muted" style="margin-top:10px">${esc(L.nRounds(s.rounds))} · ${s.seconds} s · ${esc(s.level < 0 ? L.autoLevel : `${L.lvl} ${s.level}`)}</p>
          <div class="players" id="pl" style="margin:18px 0"></div>
          <div id="startBox"></div></section>`;
      $("#leave", v).onclick = async () => { await my("room_leave", { code }).catch(() => {}); go("#/game"); };
    } else if (s.phase === "question" || s.phase === "reveal") {
      const p = s.problem;
      room.innerHTML = `<div class="page-head"><div><h1>${icon("gamepad-2")} ${esc(L.roundOf(s.round + 1, s.rounds))}</h1><p class="sub">${esc(L.lvl)} ${p.level} · ${esc(L.room)} ${esc(s.code)}</p></div>
          <span class="spacer"></span><span class="chip" id="left"></span></div>
        <div class="timer big ${s.phase === "reveal" ? "hidden" : ""}" id="tbar"><i style="width:${(100 * s.left) / s.seconds}%"></i></div>
        <div class="play"><section class="card"><p class="question">${esc(p.text)}</p>${optionsHTML(p.options, { cls: "kahoot" })}<div id="gstate"></div></section>
          <aside class="card"><h2>${icon("trophy")} ${esc(L.scores)}</h2><div id="board"></div></aside></div>`;
      $$(".opt", v).forEach((b) => (b.onclick = () => send(b.dataset.letter)));
      if (s.phase === "reveal") reveal(s);
    } else if (s.phase === "end") {
      const mine = s.players.findIndex((p) => p.me);
      room.innerHTML = `<div class="page-head"><a class="back" href="#/home" aria-label="${esc(L.home)}">${icon("arrow-left")}</a><div><h1>${icon("trophy")} ${esc(L.gameOver)}</h1>
          <p class="sub">${esc(mine === 0 ? L.youWon : L.youPlace(mine + 1))}</p></div></div>
        <section class="card">${podiumHTML(s.players, { scoreLabel: (p) => `${fmtNum(p.score)} ${L.pts}`, big: true })}
          ${boardHTML(s)}<div class="row" style="justify-content:center;margin-top:18px"><a class="btn" href="#/game">${icon("sparkles")} ${esc(L.playAgain)}</a>
          <a class="btn ghost" href="#/home">${esc(L.home)}</a></div></section>`;
      if (!ended) { ended = true; confetti(mine === 0 ? 90 : 40); Sound.play(mine === 0 ? "win" : "levelup"); }
    }
  }
  function partial(s) {
    if (s.phase === "lobby") {
      $("#pl", v).innerHTML = s.players.map((p) => `<div class="player ${p.me ? "me" : ""}">
        ${p.sid === s.host_sid ? `<span class="tag" title="${esc(L.hostTag)}">${icon("crown")}</span>` : ""}${avatar(p.avatar)}<b>${esc(p.name)}</b></div>`).join("");
      if (s.players.length > lastPlayers && lastPlayers) Sound.play("join");
      lastPlayers = s.players.length;
      $("#startBox", v).innerHTML = s.host
        ? `<button class="btn big" id="startG" style="background:var(--game);box-shadow:none">${icon("play")} ${esc(L.startGame)}</button>
           <p class="small muted" style="margin-top:8px">${esc(s.players.length < 2 ? L.waitFriends : L.readyToStart(s.players.length))}</p>`
        : `<p class="game-wait">${icon("hourglass")} ${esc(L.waitHost)}</p>`;
      const b = $("#startG", v);
      if (b) b.onclick = async () => { const r = await my("room_start", { code }); if (!r.error) { Sound.play("start"); draw(r); } };
      return;
    }
    if (s.phase === "question") {
      const left = Math.ceil(s.left);
      $("#left", v).textContent = `⏱ ${left} s`;
      const bar = $("#tbar", v);
      $("i", bar).style.width = `${(100 * s.left) / s.seconds}%`;
      bar.classList.toggle("low", s.left <= 10);
      if (left <= 5 && left > 0 && left !== lastTick && !s.my_answer) { lastTick = left; Sound.play("tick"); }
      if (s.my_answer) {
        $$(".opt", v).forEach((b) => { b.disabled = true; b.classList.toggle("sel", b.dataset.letter === s.my_answer); });
        $("#gstate", v).innerHTML = `<p class="game-wait">${icon("circle-check")} ${esc(L.answerSent)}</p><div class="answered-strip" style="justify-content:center">${strip(s)}</div>`;
      } else {
        $("#gstate", v).innerHTML = `<div class="answered-strip">${strip(s)}</div>`;
      }
      $("#board", v).innerHTML = boardHTML(s);
    }
    if (s.phase === "reveal") {
      $("#left", v).textContent = `⏭ ${Math.ceil(s.next_in)} s`;
      const nb = $("#nextR", v);
      if (nb) nb.textContent = `${L.nextRound} (${Math.ceil(s.next_in)})`;
    }
  }
  function reveal(s) {
    const p = s.problem, me = s.players.find((x) => x.me), mineL = s.my_answer;
    const byLetter = {};
    for (const pl of s.players) { const l = s.round_answers[pl.sid]; if (l) (byLetter[l] = byLetter[l] || []).push(pl.avatar); }
    $$(".opt", v).forEach((b) => {
      b.disabled = true;
      const l = b.dataset.letter;
      if (l === p.label) b.classList.add("good"); else if (l === mineL) b.classList.add("bad");
      if (byLetter[l]) b.insertAdjacentHTML("beforeend", `<span class="who" aria-hidden="true">${byLetter[l].map(esc).join("")}</span>`);
    });
    $(".options", v).classList.add("revealed");
    const right = mineL === p.label;
    $("#gstate", v).innerHTML = `<div class="feedback ${right ? "good" : "bad"}"><svg aria-hidden="true"><use href="#roo"/></svg><div>
      <h3>${right ? `${esc(L.cheers[0])} <span class="pop">+${me ? me.last : 0}</span>` : mineL ? esc(L.notThisTime) : esc(L.noAnswer)}</h3>
      <p style="margin:0">${esc(L.rightWas)} <b>${p.label}) ${esc(p.value)}</b></p>
      ${s.host ? `<button class="btn small" id="nextR" style="margin-top:10px">${esc(L.nextRound)}</button>` : ""}</div></div>`;
    const nb = $("#nextR", v);
    if (nb) nb.onclick = async () => { const r = await my("room_next", { code }); if (!r.error) draw(r); };
    $("#board", v).innerHTML = boardHTML(s, true);
    if (revealed !== `${s.round}`) { revealed = `${s.round}`; Sound.play(right ? "right" : "wrong"); if (right) confetti(24); }
  }
  async function send(letter) {
    const r = await my("room_answer", { code, letter });
    if (!r.error) { Sound.play("click"); draw(r); }
  }
  function draw(s) {
    const k = `${s.phase}:${s.round}`;
    if (k !== key) { key = k; full(s); }
    partial(s);
  }
  const tick = async () => {
    let s;
    try { s = await my("room_state", { code }); } catch { return; }
    if (s.error) { toast(L.roomGone, "bad"); go("#/game"); return; }
    draw(s);
    if (s.phase === "end") clearTimers();
  };
  await tick();
  every(1000, tick);
  S.keys = (e) => {
    const k = e.key.toUpperCase();
    if (k.length === 1 && "ABCDE".includes(k) && key.startsWith("question")) send(k);
  };
}, { student: true });

// ================================================================ learn step by step
let LESSONS = null;
route(/^\/learn$/, async () => {
  const r = await my("lessons");
  LESSONS = r.lessons;
  const est = S.me.stats.est_level;
  let level = store.get("learn_level") ?? (est == null ? "all" : String(Math.floor(est)));
  let topic = "all", todo = false, shown = 36;
  const topics = [...new Set(LESSONS.map((l) => l.topic))].sort();
  const v = page(`<div class="page-head"><a class="back" href="#/home" aria-label="${esc(L.back)}">${icon("arrow-left")}</a>
      <div><h1>${icon("book-open")} ${esc(L.learn)}</h1><p class="sub">${esc(L.learnSub)}</p></div><span class="spacer"></span>
      <span class="chip good">${icon("circle-check")} ${esc(L.lessonsDone(r.done))}</span></div>
    <section class="card stack" style="margin-bottom:16px">
      <div class="chips" id="fl"></div><div class="chips" id="ft"></div>
      <label class="row small" style="gap:8px"><input type="checkbox" id="todo"> ${esc(L.onlyPending)}</label></section>
    <div class="lessons" id="ls"></div><div class="row" style="justify-content:center;margin-top:16px"><button class="btn ghost hidden" id="more">${esc(L.showMore)}</button></div>`);
  function draw() {
    $("#fl", v).innerHTML = ["all", 0, 1, 2, 3, 4, 5, 6, 7].map((l) => `<button class="chip" data-l="${l}" aria-pressed="${String(l) === level}">${l === "all" ? esc(L.all) : `${esc(L.lvl)} ${l}`}</button>`).join("");
    $("#ft", v).innerHTML = ["all", ...topics].map((t) => `<button class="chip" data-t="${esc(t)}" aria-pressed="${t === topic}">${t === "all" ? esc(L.allTopics) : esc(t)}</button>`).join("");
    const list = LESSONS.filter((l) => (level === "all" || String(l.level) === level) && (topic === "all" || l.topic === topic) && (!todo || !l.done));
    $("#ls", v).innerHTML = list.length ? list.slice(0, shown).map((l) => `<a class="lesson-card ${l.done ? "done" : ""}" href="#/learn/${encodeURIComponent(l.id)}" style="text-decoration:none;color:inherit">
        <div class="row between"><span class="chip brand">${esc(L.lvl)} ${l.level}</span>${l.done ? `<span title="${esc(L.done)}">${l.guessed ? "⭐" : "✅"}</span>` : ""}</div>
        <b class="small">${esc(l.topic)}</b><p>${esc(l.text)}…</p></a>`).join("") : `<div class="card empty"><span class="big">${icon("eye", "lg")}</span>${esc(L.noLessons)}</div>`;
    $("#more", v).classList.toggle("hidden", list.length <= shown);
  }
  v.addEventListener("click", (e) => {
    const l = e.target.closest("[data-l]"), t = e.target.closest("[data-t]");
    if (l) { level = l.dataset.l; store.set("learn_level", level); shown = 36; draw(); }
    if (t) { topic = t.dataset.t; shown = 36; draw(); }
  });
  $("#todo", v).onchange = (e) => { todo = e.target.checked; draw(); };
  $("#more", v).onclick = () => { shown += 36; draw(); };
  draw();
}, { student: true });

route(/^\/learn\/(.+)$/, async (pid) => {
  const d = await my("lesson", { pid });
  if (d.error) { go("#/learn"); return; }
  const stages = ["read", "ask", ...(d.numbers.length ? ["data"] : []), "idea", "try", ...d.steps.map((_, i) => `step${i}`), "answer"];
  let k = 0, guess = null;
  const v = page(`<div class="page-head"><a class="back" href="#/learn" aria-label="${esc(L.back)}">${icon("arrow-left")}</a>
      <div><h1>${icon("book-open")} ${esc(L.lessonTitle)}</h1><p class="sub">${esc(L.lvl)} ${d.level} · ${esc(d.topic)}</p></div><span class="spacer"></span>
      <button class="icon-btn" id="readAll" aria-label="${esc(L.readAloud)}">${icon("volume-2")} <span class="hide-s">${esc(L.readAloud)}</span></button></div>
    <div class="stepper" id="stp" aria-hidden="true"></div><div id="steps" style="max-width:860px"></div>
    <div class="row" style="max-width:860px;justify-content:flex-end" id="ctl"></div>`);
  const stepBox = (n, title, body) => `<section class="step"><span class="n">${n}</span><div><h3>${esc(title)}</h3><div class="body">${body}</div></div></section>`;
  let subOpen = null;
  function add(stage) {
    const box = $("#steps", v);
    if (stage === "read") box.insertAdjacentHTML("beforeend", stepBox(1, L.sRead, `<p>${esc(d.text)}</p><div class="chips">${Object.entries(d.options).map(([kk, x]) => `<span class="chip">${kk}) ${esc(x)}</span>`).join("")}</div>`));
    if (stage === "ask") box.insertAdjacentHTML("beforeend", stepBox(2, L.sAsk, `<p class="callout">${icon("circle-help")} ${esc(d.question)}</p><p class="small muted" style="margin:8px 0 0">${esc(L.sAskTip)}</p>`));
    if (stage === "data") box.insertAdjacentHTML("beforeend", stepBox(3, L.sData, `<div class="numchips">${d.numbers.map((x) => `<span>${esc(x)}</span>`).join("")}</div><p class="small muted" style="margin:8px 0 0">${esc(L.sDataTip)}</p>`));
    if (stage === "idea") box.insertAdjacentHTML("beforeend", stepBox(stages.indexOf("idea") + 1, L.sIdea, `<p><b>${esc(d.topic)}</b></p><p style="margin:0">${icon("lightbulb")} ${esc(d.method)}</p>`));
    if (stage === "try") {
      box.insertAdjacentHTML("beforeend", stepBox(stages.indexOf("try") + 1, L.sTry, `<p>${esc(L.sTryTip)}</p>${optionsHTML(d.options, { cls: "tryopts" })}<div id="tryFb"></div>`));
      $$(".tryopts .opt", v).forEach((b) => (b.onclick = () => {
        if (guess) return;
        guess = b.dataset.letter;
        b.classList.add("sel");
        $$(".tryopts .opt", v).forEach((x) => (x.disabled = true));
        $("#tryFb", v).innerHTML = `<p class="callout" style="margin-top:10px">${esc(guess === d.label ? L.goodHunch : L.letsSee)}</p>`;
        Sound.play("click");
        controls();
      }));
    }
    if (stage.startsWith("step")) {
      const i = Number(stage.slice(4));
      if (i === 0) {
        box.insertAdjacentHTML("beforeend", stepBox(stages.indexOf("step0") + 1, L.sSteps,
          `${d.steps_lang !== S.lang ? `<p class="tiny muted">${esc(L.inEnglish)}</p>` : ""}<div class="substeps" id="subs"></div>`));
        subOpen = $("#subs", v);
      }
      subOpen.insertAdjacentHTML("beforeend", `<div class="substep">${esc(d.steps[i])}</div>`);
    }
    if (stage === "answer") {
      $$(".tryopts .opt", v).forEach((b) => {
        if (b.dataset.letter === d.label) b.classList.add("good");
        else if (b.dataset.letter === guess) { b.classList.remove("sel"); b.classList.add("bad"); }
      });
      box.insertAdjacentHTML("beforeend", `<section class="answer-box" style="margin-bottom:12px"><p style="margin:0 0 4px">${esc(L.theAnswer)}</p>
        <b>${d.label}) ${esc(d.value)}</b><p style="margin:8px 0 0">${esc(guess === d.label ? L.youGuessed : L.nowYouKnow)}</p></section>`);
      Sound.play(guess === d.label ? "levelup" : "right");
      if (guess === d.label) confetti(40);
      my("lesson_done", { pid: d.id, guessed: guess === d.label ? 1 : 0 }).then((r) => noticeBadges(r.badges)).catch(() => {});
    }
    const last = box.lastElementChild;
    if (last && k > 0) last.scrollIntoView({ behavior: reducedMotion() ? "auto" : "smooth", block: "center" });
  }
  function controls() {
    $("#stp", v).innerHTML = stages.map((_, i) => `<i class="${i <= k ? "done" : ""}"></i>`).join("");
    const stage = stages[k];
    const ctl = $("#ctl", v);
    if (stage === "answer") {
      const list = (LESSONS || []).filter((l) => l.level === d.level && l.id !== d.id && !l.done);
      const nxt = list[0];
      ctl.innerHTML = `<a class="btn ghost" href="#/learn">${esc(L.allLessons)}</a>${nxt ? `<a class="btn" href="#/learn/${encodeURIComponent(nxt.id)}">${esc(L.nextLesson)} →</a>` : ""}`;
      if (LESSONS) { const me = LESSONS.find((l) => l.id === d.id); if (me) { me.done = true; me.guessed = guess === d.label; } }
      return;
    }
    const waiting = stage === "try" && !guess;
    ctl.innerHTML = `${waiting ? `<button class="btn ghost" id="skip">${esc(L.skipGuess)}</button>` : ""}
      <button class="btn big" id="cont" ${waiting ? "disabled" : ""}>${esc(stage.startsWith("step") && stages[k + 1] !== "answer" ? L.nextStep : stages[k + 1] === "answer" ? L.seeAnswer : L.continue)} →</button>`;
    $("#cont", v).onclick = advance;
    const sk = $("#skip", v);
    if (sk) sk.onclick = () => { guess = "-"; $$(".tryopts .opt", v).forEach((x) => (x.disabled = true)); advance(); };
  }
  function advance() {
    if (k >= stages.length - 1) return;
    k += 1;
    add(stages[k]);
    controls();
  }
  $("#readAll", v).onclick = () => {
    const shownSteps = stages.slice(0, k + 1).filter((s) => s.startsWith("step")).map((s) => d.steps[Number(s.slice(4))]);
    speak([d.text, k >= 1 ? d.question : "", k >= 3 ? d.method : "", ...shownSteps].filter(Boolean).join(". "));
  };
  S.keys = (e) => { if (e.key === "Enter" || e.key === "ArrowRight") { const b = $("#cont", v); if (b && !b.disabled) advance(); } };
  add("read");
  controls();
}, { student: true });

// ================================================================ my progress
route(/^\/me$/, async () => {
  const me = await refreshMe();
  if (!S.info) S.info = await api("info");
  renderHeader();
  const st = me.stats;
  const v = page(`<div class="page-head"><a class="back" href="#/home" aria-label="${esc(L.back)}">${icon("arrow-left")}</a><div><h1>${icon("trending-up")} ${esc(L.myProgress)}</h1>
      <p class="sub">${esc(me.student.name)}</p></div></div>
    <div class="grid2">
      <section class="card"><h2>${icon("user-round")} ${esc(L.myAvatar)}</h2><div class="chips" id="avs">${S.info.avatars.map((a) =>
        `<button class="chip" data-a="${esc(a)}" aria-pressed="${a === me.student.avatar}" style="font-size:1.5rem;padding:4px 8px">${esc(a)}</button>`).join("")}</div></section>
      <section class="card"><h2>${icon("gauge")} ${esc(L.myLevel)}</h2>${st.est_level == null ? `<p class="muted">${esc(L.levelUnknown)}</p>` : `
        <p style="font-size:2.2rem;font-weight:900;margin:0">${fmtNum(st.est_level, 1)} <span class="small muted">/ 7</span></p>
        <div class="meter"><i style="width:${(100 * st.est_level) / 7}%"></i></div><p class="small muted" style="margin-top:8px">${esc(L.levelExplain)}</p>`}</section>
    </div>
    <div class="stats">
      <div class="stat"><span class="k">${icon("star")} ${esc(L.points)}</span><span class="v">${fmtNum(st.points)}</span></div>
      <div class="stat"><span class="k">${icon("circle-check")} ${esc(L.answers)}</span><span class="v">${st.answered}</span><span class="d">${esc(L.ofAnswers(st.correct, st.answered))}</span></div>
      <div class="stat"><span class="k">${icon("flame")} ${esc(L.bestStreak)}</span><span class="v">${st.best_streak}</span></div>
      <div class="stat"><span class="k">${icon("lightbulb")} ${esc(L.hintsUsed)}</span><span class="v">${st.hints}</span></div>
    </div>
    <div class="grid2" style="margin-top:16px;align-items:start">
      <section class="card"><h2>${icon("mountain")} ${esc(L.byLevel)}</h2>${bars([0, 1, 2, 3, 4, 5, 6, 7].map((l) => (st.by_level[l] || [0, 0])[0]),
        [0, 1, 2, 3, 4, 5, 6, 7].map((l) => `${l}`), { title: (i) => `${L.lvl} ${i}: ${(st.by_level[i] || [0, 0])[0]}/${(st.by_level[i] || [0, 0])[1]}` })}
        <p class="small muted" style="margin:8px 0 0">${esc(L.byLevelNote)}</p></section>
      <section class="card"><h2>${icon("puzzle")} ${esc(L.masteryTitle)}</h2>${masteryHTML(st.by_topic)}</section>
    </div>
    <section class="card" style="margin-top:16px"><h2>${icon("route")} ${esc(L.myPath)}</h2>${st.path.length ? `<div class="dots" aria-label="${esc(L.myPath)}">${st.path.map(([lv, ok]) =>
      `<i class="${ok ? "y" : "n"}" title="${esc(L.lvl)} ${lv}"></i>`).join("")}</div><p class="small muted" style="margin:8px 0 0">${esc(L.pathNote)}</p>` : `<p class="muted">${esc(L.noAnswersYet)}</p>`}</section>
    <section class="card" style="margin-top:16px"><h2>${icon("award")} ${esc(L.badges)}</h2>${badgesHTML(me.badges)}</section>
    ${me.recent_tests.length ? `<h2 class="section-title">${icon("list-checks")} ${esc(L.myTests)}</h2><div class="list">${me.recent_tests.map(testRow).join("")}</div>` : ""}`);
  $("#avs", v).onclick = async (e) => {
    const b = e.target.closest("[data-a]");
    if (!b) return;
    await my("settings", { avatar: b.dataset.a });
    $$("[data-a]", v).forEach((x) => x.setAttribute("aria-pressed", x === b));
    S.me.student.avatar = b.dataset.a;
    renderHeader(); Sound.play("click");
  };
}, { student: true });
