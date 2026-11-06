(() => {
  const tg = window.Telegram && Telegram.WebApp;
  const $ = (id) => document.getElementById(id);
  const COLORS = ["#4f8cff", "#3ecf8e", "#f5a524", "#f31260", "#a78bfa", "#22d3ee", "#fb7185", "#facc15"];

  // ---------- Telegram mavzusi ----------
  function applyTheme() {
    if (!tg) return;
    const p = tg.themeParams || {}, r = document.documentElement.style;
    if (p.bg_color) r.setProperty("--bg", p.bg_color);
    if (p.secondary_bg_color) r.setProperty("--card", p.secondary_bg_color);
    if (p.text_color) r.setProperty("--text", p.text_color);
    if (p.hint_color) r.setProperty("--hint", p.hint_color);
    if (p.button_color) r.setProperty("--accent", p.button_color);
  }
  if (tg) { tg.ready(); tg.expand(); applyTheme(); tg.onEvent("themeChanged", () => { applyTheme(); redrawAll(); }); }

  // ---------- Formatlash ----------
  const fmtBytes = (n) => { if (n == null) return "—"; const u = ["B", "KB", "MB", "GB", "TB"]; let i = 0; while (n >= 1024 && i < 4) { n /= 1024; i++; } return n.toFixed(n < 10 && i ? 1 : 0) + " " + u[i]; };
  const fmtRate = (n) => (n == null ? "—" : fmtBytes(n) + "/s");
  const fmtPct = (n) => (n == null ? "—" : n.toFixed(n < 10 ? 1 : 0) + "%");
  const fmtNum = (n, d = 1) => (n == null ? "—" : Number(n).toFixed(d));
  const fmtInt = (n) => (n == null ? "—" : Math.round(n).toLocaleString("en-US").replace(/,/g, " "));
  const fmtDur = (s) => { s = Math.floor(s); const d = Math.floor(s / 86400), h = Math.floor(s % 86400 / 3600), m = Math.floor(s % 3600 / 60); return d ? `${d} kun ${h} soat` : h ? `${h} soat ${m} daq` : `${m} daq`; };
  const pad = (n) => String(n).padStart(2, "0");
  const fmtTime = (t, sec) => { const d = new Date(t * 1000); return `${pad(d.getHours())}:${pad(d.getMinutes())}` + (sec ? `:${pad(d.getSeconds())}` : ""); };
  const level = (v, warn, bad) => (v == null ? "" : v >= bad ? "bad" : v >= warn ? "warn" : "ok");
  const esc = (s) => String(s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

  // ---------- Holat ----------
  const state = { fast: [], slow: [], range: 600, last: null };
  const FAST_MAX = 300, SLOW_MAX = 1440;

  function unpack(h) { return h.rows.map((row) => { const o = { t: row[0] }; h.keys.forEach((k, i) => { o[k] = row[i + 1]; }); return o; }); }
  function windowData() {
    const since = Date.now() / 1000 - state.range;
    if (state.range <= 600) return state.fast.filter((p) => p.t >= since);
    const lastSlow = state.slow.length ? state.slow[state.slow.length - 1].t : 0;
    return state.slow.filter((p) => p.t >= since).concat(state.fast.filter((p) => p.t > lastSlow));
  }

  // ---------- Grafik ----------
  const CHARTS = [
    { id: "cpu", title: "CPU", series: [["cpu", "Band", 0], ["iowait", "IO kutish", 2], ["steal", "Steal", 3]], max: 100, fmt: fmtPct, area: true },
    { id: "mem", title: "Xotira (RAM / Swap)", series: [["mem", "RAM", 1], ["swap", "Swap", 2]], max: 100, fmt: fmtPct, area: true },
    { id: "load", title: "Yuklama (load average)", series: [["load1", "1 daq", 0], ["load5", "5 daq", 1]], fmt: (v) => fmtNum(v, 2) },
    { id: "net", title: "Tarmoq (tashqi)", series: [["rx", "Kirish", 1], ["tx", "Chiqish", 0]], fmt: fmtRate },
    { id: "dio", title: "Disk I/O", series: [["dr", "O'qish", 1], ["dw", "Yozish", 2]], fmt: fmtRate },
    { id: "disk", title: "Disk to'lganligi", series: [["disk", "Disk", 0]], max: 100, fmt: fmtPct, area: true },
    { id: "ccpu", title: "Konteynerlar CPU", prefix: "cc:", fmt: (v) => fmtNum(v, 2) + "%" },
    { id: "cmem", title: "Konteynerlar xotirasi", prefix: "cm:", fmt: (v) => fmtNum(v, 0) + " MB" },
    { id: "q", title: "Redis navbati (bot_queue)", series: [["q", "Navbat", 3]], fmt: fmtInt },
    { id: "rmem", title: "Redis xotirasi / amallar", series: [["rmem", "MB", 0], ["rops", "amal/s", 2]], fmt: (v) => fmtNum(v, 1) },
    { id: "pgc", title: "Postgres ulanishlari", series: [["pgc", "Jami", 0], ["pga", "Faol", 2]], fmt: fmtInt },
    { id: "tps", title: "Postgres tranzaksiya/s", series: [["tps", "TPS", 1]], fmt: (v) => fmtNum(v, 1) },
  ];

  class Chart {
    constructor(def) {
      this.def = def; this.hover = null; this.pts = []; this.keys = [];
      this.el = document.createElement("div"); this.el.className = "card";
      this.el.innerHTML = `<h3>${esc(def.title)}</h3><div class="legend"></div><canvas></canvas><div class="tip"></div>`;
      this.legend = this.el.querySelector(".legend"); this.cv = this.el.querySelector("canvas"); this.tip = this.el.querySelector(".tip");
      this.ctx = this.cv.getContext("2d");
      const move = (e) => { const r = this.cv.getBoundingClientRect(); this.hover = (e.touches ? e.touches[0].clientX : e.clientX) - r.left; this.draw(); };
      const leave = () => { this.hover = null; this.tip.style.display = "none"; this.draw(); };
      this.cv.addEventListener("pointermove", move); this.cv.addEventListener("pointerleave", leave); this.cv.addEventListener("pointerup", () => setTimeout(leave, 1500));
      new ResizeObserver(() => this.draw()).observe(this.cv);
    }
    seriesList() {
      if (this.def.series) return this.def.series.map(([k, l, c]) => ({ k, l, c: COLORS[c] }));
      const set = new Set();
      this.pts.forEach((p) => Object.keys(p).forEach((k) => { if (k.startsWith(this.def.prefix)) set.add(k); }));
      return [...set].sort().slice(0, COLORS.length).map((k, i) => ({ k, l: k.slice(this.def.prefix.length).replace(/^my_bot_/, ""), c: COLORS[i] }));
    }
    update(pts) { this.pts = pts; this.draw(); }
    draw() {
      const cv = this.cv, ctx = this.ctx, dpr = window.devicePixelRatio || 1;
      const W = cv.clientWidth, H = cv.clientHeight; if (!W) return;
      if (cv.width !== W * dpr || cv.height !== H * dpr) { cv.width = W * dpr; cv.height = H * dpr; }
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0); ctx.clearRect(0, 0, W, H);
      const css = getComputedStyle(document.documentElement), hint = css.getPropertyValue("--hint").trim() || "#888", line = css.getPropertyValue("--line").trim() || "#333";
      const series = this.seriesList(), pts = this.pts, f = this.def.fmt;
      const L = 46, R = 6, T = 6, B = 18, w = W - L - R, h = H - T - B;

      let ymax = this.def.max || 0;
      if (!this.def.max) { pts.forEach((p) => series.forEach((s) => { if (p[s.k] != null && p[s.k] > ymax) ymax = p[s.k]; })); ymax = niceMax(ymax * 1.1); }
      if (!ymax) ymax = 1;
      const t1 = pts.length ? pts[pts.length - 1].t : Date.now() / 1000, t0 = Math.min(pts.length ? pts[0].t : t1 - state.range, t1 - 5);
      const X = (t) => L + (t - t0) / (t1 - t0) * w, Y = (v) => T + h - Math.min(v / ymax, 1) * h;

      ctx.font = "11px sans-serif"; ctx.fillStyle = hint; ctx.strokeStyle = line; ctx.lineWidth = 1; ctx.textAlign = "right";
      for (let i = 0; i <= 4; i++) { const v = ymax * i / 4, y = Y(v); ctx.beginPath(); ctx.moveTo(L, y + .5); ctx.lineTo(W - R, y + .5); ctx.stroke(); ctx.fillText(shortAxis(f, v), L - 5, y + 4); }
      ctx.textAlign = "left"; ctx.fillText(fmtTime(t0, state.range <= 600), L, H - 4);
      ctx.textAlign = "right"; ctx.fillText(fmtTime(t1, state.range <= 600), W - R, H - 4);

      series.forEach((s, si) => {
        ctx.beginPath(); let open = false, lastX = 0, firstX = 0;
        pts.forEach((p) => {
          const v = p[s.k]; if (v == null) { open = false; return; }
          const x = X(p.t), y = Y(v);
          if (!open) { ctx.moveTo(x, y); open = true; firstX = x; } else ctx.lineTo(x, y); lastX = x;
        });
        ctx.strokeStyle = s.c; ctx.lineWidth = 1.6; ctx.lineJoin = "round"; ctx.stroke();
        if (this.def.area && si === 0 && open) {
          ctx.lineTo(lastX, T + h); ctx.lineTo(firstX, T + h); ctx.closePath();
          const g = ctx.createLinearGradient(0, T, 0, T + h); g.addColorStop(0, s.c + "55"); g.addColorStop(1, s.c + "05"); ctx.fillStyle = g; ctx.fill();
        }
      });

      // Legend: oxirgi qiymatlar
      const latest = pts.length ? pts[pts.length - 1] : {};
      const shown = this.hover != null && pts.length ? nearest(pts, t0 + (this.hover - L) / w * (t1 - t0)) : latest;
      this.legend.innerHTML = series.map((s) => `<span><i style="background:${s.c}"></i>${esc(s.l)}: <b>${shown[s.k] != null ? esc(f(shown[s.k])) : "—"}</b></span>`).join("");

      if (this.hover != null && pts.length) {
        const x = Math.max(L, Math.min(X(shown.t), W - R));
        ctx.strokeStyle = hint; ctx.lineWidth = 1; ctx.beginPath(); ctx.moveTo(x, T); ctx.lineTo(x, T + h); ctx.stroke();
        series.forEach((s) => { if (shown[s.k] != null) { ctx.fillStyle = s.c; ctx.beginPath(); ctx.arc(x, Y(shown[s.k]), 3, 0, 7); ctx.fill(); } });
        this.tip.textContent = fmtTime(shown.t, true); this.tip.style.display = "block";
        this.tip.style.left = Math.min(Math.max(x - 30, 0), this.el.clientWidth - 70) + "px"; this.tip.style.top = (this.cv.offsetTop - 6) + "px";
      }
    }
  }
  function nearest(pts, t) { let lo = 0, hi = pts.length - 1; while (hi - lo > 1) { const m = (lo + hi) >> 1; if (pts[m].t < t) lo = m; else hi = m; } return Math.abs(pts[lo].t - t) <= Math.abs(pts[hi].t - t) ? pts[lo] : pts[hi]; }
  function niceMax(v) { if (v <= 0) return 1; const e = Math.pow(10, Math.floor(Math.log10(v))), n = v / e; return (n <= 1 ? 1 : n <= 2 ? 2 : n <= 5 ? 5 : 10) * e; }
  function shortAxis(f, v) { const s = f(v); return s.length > 8 ? s.replace(" ", "") : s; }

  const charts = CHARTS.map((d) => new Chart(d));
  charts.forEach((c) => $("charts").appendChild(c.el));
  let raf = 0;
  function redrawAll() { cancelAnimationFrame(raf); raf = requestAnimationFrame(() => { const d = windowData(); charts.forEach((c) => c.update(d)); }); }

  // ---------- Kartochkalar ----------
  const TILES = [
    ["cpu", "CPU", (m) => fmtPct(m.host.cpu && m.host.cpu.busy), (m) => `${m.host.ncpu} yadro · steal ${fmtPct(m.host.cpu && m.host.cpu.steal)}`, (m) => level(m.host.cpu && m.host.cpu.busy, 70, 90)],
    ["ram", "RAM", (m) => fmtPct(m.host.mem.pct), (m) => `${fmtNum(m.host.mem.used, 0)} / ${fmtNum(m.host.mem.total, 0)} MB`, (m) => level(m.host.mem.pct, 80, 92)],
    ["swap", "Swap", (m) => fmtPct(m.host.mem.swap_pct), (m) => `${fmtNum(m.host.mem.swap_used, 0)} / ${fmtNum(m.host.mem.swap_total, 0)} MB`, (m) => level(m.host.mem.swap_pct, 25, 50)],
    ["disk", "Disk", (m) => fmtPct(m.host.disk.pct), (m) => `${m.host.disk.used_gb} / ${m.host.disk.total_gb} GB`, (m) => level(m.host.disk.pct, 70, 85)],
    ["load", "Load avg", (m) => fmtNum(m.host.load[0], 2), (m) => `${fmtNum(m.host.load[1], 2)} · ${fmtNum(m.host.load[2], 2)}`, (m) => level(m.host.load[0] / m.host.ncpu, 0.7, 1.5)],
    ["net", "Tarmoq", (m) => fmtRate(m.host.net && m.host.net.rx), (m) => `↑ ${fmtRate(m.host.net && m.host.net.tx)}`, () => ""],
    ["up", "Ishlash vaqti", (m) => fmtDur(m.host.uptime), (m) => `${m.host.procs} jarayon · ${m.host.tcp} TCP`, () => ""],
    ["queue", "Redis navbati", (m) => fmtInt(m.svc.redis && m.svc.redis.queue), (m) => `Redis ${fmtNum(m.svc.redis && m.svc.redis.mem_mb, 1)} MB`, (m) => level(m.svc.redis && m.svc.redis.queue, 100, 500)],
  ];
  const tileEls = TILES.map(([id, label]) => { const el = document.createElement("div"); el.className = "tile"; el.innerHTML = `<div class="k">${label}</div><div class="v">—</div><div class="s"></div>`; $("tiles").appendChild(el); return el; });

  function kv(rows) { return rows.map(([k, v]) => `<div class="kv"><span>${esc(k)}</span><span>${esc(v)}</span></div>`).join(""); }

  function render(m) {
    state.last = m;
    TILES.forEach((t, i) => { const el = tileEls[i]; el.className = "tile " + (t[4](m) || ""); el.querySelector(".v").textContent = t[2](m); el.querySelector(".s").textContent = t[3](m); });

    const al = $("alerts"); al.hidden = !m.alerts.length; al.innerHTML = m.alerts.map((a) => `<div>${esc(a)}</div>`).join("");

    const dk = m.svc.docker || [];
    $("containers").innerHTML = `<tr><th></th><th>Nomi</th><th>CPU</th><th>Xotira</th><th>Tarmoq ↓/↑</th><th>Holat</th></tr>` + dk.map((c) =>
      `<tr><td>${c.state === "running" ? "🟢" : "🔴"}</td><td>${esc(c.name)}</td><td>${c.cpu == null ? "—" : fmtNum(c.cpu, 2) + "%"}</td><td>${c.mem == null ? "—" : fmtNum(c.mem, 0) + " MB"}</td><td>${c.rx == null ? "—" : fmtBytes(c.rx) + " / " + fmtBytes(c.tx)}</td><td>${esc(c.status)}</td></tr>`).join("");

    const pg = m.svc.postgres, rd = m.svc.redis, bot = m.svc.bot, aws = m.aws;
    const cards = [];
    cards.push(`<div class="card"><h3>🐘 Postgres</h3>${pg ? kv([["Ulanishlar", `${pg.conns} / ${pg.max_conns} (faol ${pg.active})`], ["Tranzaksiya/s", fmtNum(pg.tps, 1)], ["Kesh hit", pg.hit_pct == null ? "—" : pg.hit_pct + "%"], ["Baza hajmi", fmtNum(pg.size_mb, 1) + " MB"]]) : "<div class='hint'>Ma'lumot yo'q</div>"}</div>`);
    cards.push(`<div class="card"><h3>🧠 Redis</h3>${rd ? kv([["Navbat", fmtInt(rd.queue)], ["Xotira", `${fmtNum(rd.mem_mb, 2)} / ${rd.max_mb || "∞"} MB`], ["Amal/s", fmtInt(rd.ops)], ["Mijozlar", fmtInt(rd.clients)], ["Kalitlar", fmtInt(rd.keys)], ["Kesh hit", rd.hit_pct == null ? "—" : rd.hit_pct + "%"], ["Chiqarib tashlangan", fmtInt(rd.evicted)]]) : "<div class='hint'>Ma'lumot yo'q</div>"}</div>`);
    cards.push(`<div class="card"><h3>🎬 Bot</h3>${bot ? kv([["Foydalanuvchilar", fmtInt(bot.users)], ["Kinolar", fmtInt(bot.movies)], ["Yangi (24 soat)", fmtInt(bot.new_users_24h)], ["Ko'rishlar (24 soat)", fmtInt(bot.views_24h)]]) : "<div class='hint'>Ma'lumot yo'q</div>"}</div>`);
    if (aws) {
      const pctLeft = aws.remaining != null && aws.total ? Math.max(0, Math.min(100, aws.remaining / aws.total * 100)) : null;
      cards.push(`<div class="card"><h3>💳 AWS kredit</h3>${aws.remaining != null ? kv([["Qolgan", "$" + fmtNum(aws.remaining, 2)], ["Kredit bilan qoplangan", "$" + fmtNum(aws.credits_used, 2)], ["Sarf (7 kun o'rtacha)", "$" + fmtNum(aws.avg_daily, 2) + "/kun"], ["Yetadi", aws.days_left == null ? "—" : "~" + Math.round(aws.days_left) + " kun"]]) : kv([["Sarflangan", "$" + fmtNum(aws.credits_used, 2)]])}${pctLeft == null ? "" : `<div class="bar"><div style="width:${pctLeft}%;background:${aws.low ? "var(--bad)" : "var(--ok)"}"></div></div>`}</div>`);
    }
    $("info").innerHTML = cards.join("");
  }

  // ---------- Ulanish ----------
  function show(msg) { const el = $("message"); el.hidden = !msg; el.textContent = msg || ""; }
  function setLive(s) { $("dot").className = "dot " + (s || ""); }
  let ws, retry = 1000, stop = false;
  function connect() {
    const initData = tg && tg.initData;
    if (!initData) { show("Bu sahifa faqat Telegram ichida (botdagi «📊 Server» tugmasi orqali) ochiladi."); return; }
    ws = new WebSocket((location.protocol === "https:" ? "wss://" : "ws://") + location.host + "/ws");
    ws.onopen = () => ws.send(JSON.stringify({ type: "auth", initData }));
    ws.onmessage = (ev) => {
      const m = JSON.parse(ev.data);
      if (m.type === "hello") { retry = 1000; setLive("live"); show(null); $("app").hidden = false; }
      else if (m.type === "history") { state.fast = unpack(m.fast); state.slow = unpack(m.slow); redrawAll(); }
      else if (m.type === "tick") {
        state.fast.push(m.point); if (state.fast.length > FAST_MAX) state.fast.shift();
        if (m.history_point) { state.slow.push(m.history_point); if (state.slow.length > SLOW_MAX) state.slow.shift(); }
        render(m); redrawAll(); $("clock").textContent = fmtTime(m.point.t, true);
      } else if (m.type === "denied") { stop = true; show("⛔ Ruxsat yo'q yoki sessiya eskirgan. Ilovani botdan qayta oching."); }
      else if (m.type === "busy") { stop = true; show("Juda ko'p ochiq sessiya. Keyinroq urinib ko'ring."); }
    };
    ws.onclose = () => {
      setLive("off");
      if (stop) return;
      setTimeout(connect, retry); retry = Math.min(retry * 2, 15000);
    };
  }

  $("ranges").addEventListener("click", (e) => {
    const b = e.target.closest("button"); if (!b) return;
    state.range = +b.dataset.r; [...$("ranges").children].forEach((x) => x.classList.toggle("on", x === b)); redrawAll();
  });
  document.addEventListener("visibilitychange", () => { if (!document.hidden && ws && ws.readyState > 1 && !stop) connect(); });
  connect();
})();
