/* Thermal Materials Academic Radar — client.
   Pages: home | papers | industry | conferences.
   Data: data/meta.json, data/<cat>/index.json (months), data/<cat>/<YYYY-MM>.json (items). */
(() => {
  const PAGE = document.body.dataset.page;
  const ROOT = document.body.dataset.root || "";
  const app = document.getElementById("app");
  const dlg = document.getElementById("detail");
  const dlgBody = document.getElementById("detail-body");
  const cache = {};
  let META = null;
  const filters = { themes: new Set(), kinds: new Set(), q: "", comp: false };
  const TZ = "America/New_York";
  // today's date in US Eastern time, YYYY-MM-DD
  const todayET = () => new Intl.DateTimeFormat("en-CA", { timeZone: TZ, year: "numeric", month: "2-digit", day: "2-digit" }).format(new Date());
  const fmtET = (iso) => new Date(iso).toLocaleString("en-US", { timeZone: TZ, month: "short", day: "numeric", year: "numeric",
    hour: "numeric", minute: "2-digit", timeZoneName: "short" });
  const FOCUS = { computational: "Theory / computation", mixed: "Computation + experiment", experimental: "Experimental" };

  const KIND_LABEL = { paper: "Journal", preprint: "Preprint", news: "News", tool: "Release", repo: "Hot repo",
    conference: "Conference", cfp: "Call", "special-issue": "Special issue" };
  const KINDS = { papers: ["paper", "preprint"], industry: ["news", "tool", "repo"], conferences: ["conference", "special-issue", "cfp"] };

  // ---------- theme toggle (per-viewer convenience only)
  const store = { get(k) { try { return localStorage.getItem(k); } catch { return null; } },
                  set(k, v) { try { localStorage.setItem(k, v); } catch { /* ignore */ } } };
  const saved = store.get("tmar-theme");
  if (saved) document.documentElement.dataset.theme = saved;
  document.querySelector(".theme-toggle")?.addEventListener("click", () => {
    const dark = document.documentElement.dataset.theme
      ? document.documentElement.dataset.theme === "dark"
      : matchMedia("(prefers-color-scheme: dark)").matches;
    document.documentElement.dataset.theme = dark ? "light" : "dark";
    store.set("tmar-theme", document.documentElement.dataset.theme);
  });

  // ---------- helpers
  const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const getJSON = async (p) => {
    if (!cache[p]) cache[p] = fetch(ROOT + p).then((r) => (r.ok ? r.json() : null)).catch(() => null);
    return cache[p];
  };
  const parse = (d) => new Date(d + "T00:00:00Z");
  const fmt = (d, o) => parse(d).toLocaleDateString("en-US", { timeZone: "UTC", ...o });
  const monday = (d) => { const t = parse(d); const wd = (t.getUTCDay() + 6) % 7; t.setUTCDate(t.getUTCDate() - wd); return t.toISOString().slice(0, 10); };
  const addDays = (d, n) => { const t = parse(d); t.setUTCDate(t.getUTCDate() + n); return t.toISOString().slice(0, 10); };
  const isoWeek = (d) => { const t = parse(d); const day = (t.getUTCDay() + 6) % 7; t.setUTCDate(t.getUTCDate() - day + 3);
    const y = new Date(Date.UTC(t.getUTCFullYear(), 0, 4)); return 1 + Math.round(((t - y) / 864e5 - 3 + ((y.getUTCDay() + 6) % 7)) / 7); };
  const themeById = (id) => META.themes.find((t) => t.id === id);
  const color = (id) => themeById(id)?.color || "#2b6eff";
  const daysLeft = (d) => Math.ceil((parse(d) - parse(todayET())) / 864e5);

  // ---------- cards
  function card(it) {
    const th = it.themes || [];
    const c1 = th[0] ? color(th[0]) : "var(--main)";
    const c2 = th[1] ? color(th[1]) : "var(--accent)";
    const extra = it.kind === "repo" ? ` · ★ ${it.stars ?? ""}${it.star_delta ? ` (+${it.star_delta})` : ""}` : "";
    const el = document.createElement("button");
    el.type = "button";
    el.className = "card";
    el.style.setProperty("--c1", c1);
    el.style.setProperty("--c2", c2);
    el.dataset.themes = th.join(" ");
    el.dataset.kind = it.kind;
    el.dataset.focus = it.focus || "";
    el.dataset.text = `${it.title} ${it.venue} ${(it.authors || []).join(" ")} ${(it.matched || []).join(" ")}`.toLowerCase();
    el.innerHTML = `
      <div class="meta"><span class="badge">${esc(KIND_LABEL[it.kind] || it.kind)}</span>
        ${it.focus === "computational" ? `<span class="badge comp" title="${FOCUS.computational}">Theory</span>` : ""}
        ${it.focus === "experimental" ? `<span class="badge expt" title="${FOCUS.experimental}">Expt.</span>` : ""}
        ${it.watched?.length ? `<span class="badge star" title="${esc(it.watched.join(", "))}">★ watched</span>` : ""}
        <span>${esc(fmt(it.first_seen, { month: "short", day: "numeric" }))}</span>
        <span class="dots">${th.map((t) => `<i style="background:${color(t)}" title="${esc(themeById(t)?.name || t)}"></i>`).join("")}</span></div>
      <h3>${esc(it.title)}</h3>
      <p>${esc(it.venue || "")}${esc(extra)}</p>
      <p>${esc(it.summary?.what || "")}</p>`;
    el.addEventListener("click", () => openDetail(it));
    return el;
  }

  function openDetail(it) {
    const s = it.summary || {};
    const row = (k, v, cls = "") => (v ? `<dt>${k}</dt><dd class="${cls}">${esc(v)}</dd>` : "");
    const authors = (it.authors || []).join(", ");
    dlgBody.innerHTML = `
      <button class="close" aria-label="Close">×</button>
      <div class="meta"><span class="badge">${esc(KIND_LABEL[it.kind] || it.kind)}</span>
        ${(it.themes || []).map((t) => `<span class="badge" style="border-color:${color(t)}">${esc(themeById(t)?.name || t)}</span>`).join(" ")}
        ${it.focus ? `<span class="badge">${esc(FOCUS[it.focus])}</span>` : ""}</div>
      <h2>${esc(it.title)}</h2>
      <p class="sub">${esc(it.venue || "")}${it.published ? " · " + esc(it.published) : ""}${authors ? "<br>" + esc(authors) : ""}
        ${it.watched?.length ? `<br>★ Watched: ${esc(it.watched.join(", "))}` : ""}${it.deadline ? `<br>Deadline: <b>${esc(it.deadline)}</b>` : ""}</p>
      <dl class="qa">
        ${row("What", s.what)}${row("Why", s.why)}${row("How", s.how)}${row("Impact on me", s.impact, "impact")}
      </dl>
      ${it.matched?.length ? `<p class="kw">Matched: ${esc(it.matched.join(" · "))}</p>` : ""}
      <div class="actions">
        <a class="btn" href="${esc(it.url)}" target="_blank" rel="noopener">Open original ↗</a>
        <button class="btn ghost" type="button" id="copy">Copy link</button>
        <span class="by by-${s.by === "claude" ? "claude" : "rules"}">${s.by === "claude" ? "Summary by Claude" : "Rule-based summary"}</span>
      </div>`;
    dlgBody.querySelector(".close").onclick = () => dlg.close();
    dlgBody.querySelector("#copy").onclick = (e) => {
      navigator.clipboard?.writeText(it.url).then(() => { e.target.textContent = "Copied"; }).catch(() => {});
    };
    dlg.showModal();
  }
  dlg.addEventListener("click", (e) => { if (e.target === dlg) dlg.close(); });

  // ---------- filters
  function toolbar(cat) {
    const bar = document.createElement("div");
    bar.className = "toolbar";
    const themes = META.themes.map((t) =>
      `<button class="chip" type="button" data-theme="${t.id}" aria-pressed="false"><span class="sw" style="background:${t.color}"></span>${esc(t.name)}</button>`).join("");
    const kinds = KINDS[cat].map((k) => `<button class="chip" type="button" data-kind="${k}" aria-pressed="false">${KIND_LABEL[k]}</button>`).join("");
    bar.innerHTML = `<div class="chips">${kinds}<button class="chip" type="button" data-watched aria-pressed="false">★ Watched authors</button>${cat === "papers" ? `<button class="chip" type="button" data-comp aria-pressed="false">Theory &amp; computation only</button>` : ""}</div>
      <div class="chips">${themes}</div>
      <input class="search" type="search" placeholder="Search titles, venues, authors, keywords…" aria-label="Search">`;
    bar.addEventListener("click", (e) => {
      const b = e.target.closest(".chip");
      if (!b) return;
      const on = b.getAttribute("aria-pressed") !== "true";
      b.setAttribute("aria-pressed", on);
      if (b.dataset.theme) on ? filters.themes.add(b.dataset.theme) : filters.themes.delete(b.dataset.theme);
      if (b.dataset.kind) on ? filters.kinds.add(b.dataset.kind) : filters.kinds.delete(b.dataset.kind);
      if (b.hasAttribute("data-watched")) filters.watched = on;
      if (b.hasAttribute("data-comp")) filters.comp = on;
      applyFilters();
    });
    bar.querySelector(".search").addEventListener("input", (e) => { filters.q = e.target.value.trim().toLowerCase(); applyFilters(); });
    return bar;
  }

  function applyFilters() {
    document.querySelectorAll(".card").forEach((c) => {
      const th = c.dataset.themes.split(" ");
      const ok = (!filters.themes.size || th.some((t) => filters.themes.has(t))) &&
        (!filters.kinds.size || filters.kinds.has(c.dataset.kind)) &&
        (!filters.watched || c.querySelector(".badge.star")) &&
        (!filters.comp || c.dataset.focus === "computational" || c.dataset.focus === "mixed") &&
        (!filters.q || c.dataset.text.includes(filters.q));
      c.hidden = !ok;
    });
    document.querySelectorAll("details.week").forEach((w) => {
      const n = w.querySelectorAll(".card:not([hidden])").length;
      w.querySelector(".count").textContent = n;
      w.hidden = n === 0;
    });
  }

  // ---------- timeline
  async function timeline(cat, mount) {
    const months = (await getJSON(`data/${cat}/index.json`)) || [];
    if (!months.length) { mount.insertAdjacentHTML("beforeend", `<p class="empty">Nothing collected yet.</p>`); return; }
    let openWeeks = 4;
    const years = {};
    months.forEach((m) => (years[m.month.slice(0, 4)] ||= []).push(m));
    let firstYear = true;
    for (const [y, ms] of Object.entries(years).sort((a, b) => b[0] - a[0])) {
      const yd = document.createElement("details");
      yd.className = "year";
      yd.open = firstYear;
      yd.innerHTML = `<summary>${y} <span class="count">${ms.reduce((s, m) => s + m.count, 0)}</span></summary>`;
      mount.appendChild(yd);
      ms.forEach((m, i) => {
        const md = document.createElement("details");
        md.className = "month";
        md.innerHTML = `<summary>${fmt(m.month + "-01", { month: "long", year: "numeric" })} <span class="count">${m.count}</span></summary>`;
        yd.appendChild(md);
        let loaded = false;
        const load = async () => {
          if (loaded) return;
          loaded = true;
          const items = (await getJSON(`data/${cat}/${m.month}.json`)) || [];
          const weeks = {};
          items.forEach((it) => (weeks[monday(it.first_seen)] ||= []).push(it));
          Object.keys(weeks).sort().reverse().forEach((wk) => {
            const wd = document.createElement("details");
            wd.className = "week";
            wd.open = openWeeks-- > 0;
            const end = addDays(wk, 6);
            wd.innerHTML = `<summary><b>Week ${isoWeek(wk)}</b> ${fmt(wk, { month: "short", day: "numeric" })} – ${fmt(end, { month: "short", day: "numeric" })} <span class="count">${weeks[wk].length}</span></summary>`;
            const grid = document.createElement("div");
            grid.className = "grid";
            weeks[wk].sort((a, b) => (b.score - a.score) || (b.first_seen.localeCompare(a.first_seen))).forEach((it) => grid.appendChild(card(it)));
            wd.appendChild(grid);
            md.appendChild(wd);
          });
          applyFilters();
        };
        md.addEventListener("toggle", () => md.open && load());
        if (firstYear && i < 2) { md.open = true; load(); }
      });
      firstYear = false;
    }
  }

  // ---------- page-specific
  function conferencePanels(mount) {
    const dl = META.deadlines || [];
    mount.insertAdjacentHTML("beforeend", `
      <div class="panels">
        <div class="panel"><h2>Upcoming abstract deadlines</h2>
          ${dl.length ? `<ul>${dl.map((d) => `<li><span class="countdown">${daysLeft(d.deadline)}d</span> &nbsp;
            <a href="${esc(d.url)}" target="_blank" rel="noopener"><b>${esc(d.edition || d.name)}</b></a><br>
            <small>Abstracts due ${esc(d.deadline)} · ${esc(d.dates)} · ${esc(d.location)}</small></li>`).join("")}</ul>`
            : `<p class="empty">No confirmed open deadlines. Watched pages are checked daily below.</p>`}
        </div>
      </div>
      <h2 class="section-title">Watch list (US-held)</h2>
      <div class="table-wrap"><table class="watch"><thead><tr><th>Conference</th><th>Fit</th><th>Why</th><th>Next edition</th></tr></thead><tbody>
      ${META.conferences.map((c) => `<tr><td><a href="${esc(c.url)}" target="_blank" rel="noopener">${esc(c.name)}</a><br><small>${esc(c.area || "")}</small></td>
        <td><span class="fit fit-${esc(c.fit)}">${esc(c.fit)}</span></td><td>${esc(c.why || "")}</td>
        <td>${c.next ? `${esc(c.next.edition || "")}<br><small>${esc(c.next.dates || "")}${c.next.location ? " · " + esc(c.next.location) : ""}</small>` : "<small>check site</small>"}</td></tr>`).join("")}
      </tbody></table></div>
      <h2 class="section-title">Timeline · calls, special issues & site updates</h2>`);
  }

  async function home() {
    app.innerHTML = "";
    const cats = [["papers", "Papers & Preprints"], ["industry", "Industry & Tools"], ["conferences", "Conferences & Calls"]];
    const wk = monday(todayET());
    const panels = document.createElement("div");
    panels.className = "panels";
    app.appendChild(panels);
    for (const [cat, label] of cats) {
      const months = (await getJSON(`data/${cat}/index.json`)) || [];
      let items = [];
      for (const m of months.slice(0, 2)) items = items.concat((await getJSON(`data/${cat}/${m.month}.json`)) || []);
      const week = items.filter((i) => i.first_seen >= wk);
      const top = (week.length ? week : items).slice().sort((a, b) => b.score - a.score).slice(0, 6);
      const p = document.createElement("div");
      p.className = "panel";
      p.innerHTML = `<h2><a href="${cat}/">${label} →</a></h2><span class="big">${week.length}</span> <small>new this week</small><ul></ul>`;
      top.forEach((it) => {
        const li = document.createElement("li");
        const a = document.createElement("a");
        a.href = "#";
        a.textContent = it.title;
        a.onclick = (e) => { e.preventDefault(); openDetail(it); };
        li.appendChild(a);
        li.insertAdjacentHTML("beforeend", ` <small>· ${esc(it.venue || "")}</small>`);
        p.querySelector("ul").appendChild(li);
      });
      panels.appendChild(p);
    }
    if (META.deadlines?.length) {
      const d = META.deadlines[0];
      panels.insertAdjacentHTML("beforeend", `<div class="panel"><h2>Next deadline</h2><span class="countdown">${daysLeft(d.deadline)} days</span>
        <p><a href="${esc(d.url)}" target="_blank" rel="noopener"><b>${esc(d.edition || d.name)}</b></a><br><small>Abstracts due ${esc(d.deadline)} · ${esc(d.location)}</small></p></div>`);
    }
    if (META.suggestions?.length) {
      panels.insertAdjacentHTML("beforeend", `<div class="panel"><h2>Keyword suggestions</h2>
        <small>Frequent phrases this week that are not in the topic list yet — review before adding.</small>
        <ul>${META.suggestions.slice(0, 10).map((s) => `<li>${esc(s.term)} <small>(${s.count})</small></li>`).join("")}</ul></div>`);
    }
  }

  // ---------- boot
  (async () => {
    META = await getJSON("data/meta.json");
    if (!META) { app.innerHTML = `<p class="empty">Data not available yet.</p>`; return; }
    if (META.last_run) document.getElementById("runinfo").textContent =
      `Last run ${fmtET(META.last_run)} · ${META.health.ok}/${META.health.total} sources OK · cards sorted by relevance`;
    if (META.health.failed?.length) document.getElementById("health").textContent =
      `Sources with errors in the last run: ${META.health.failed.map((f) => f.source).join(", ")}.`;
    if (PAGE === "home") return home();
    app.innerHTML = "";
    if (PAGE === "conferences") conferencePanels(app);
    app.appendChild(toolbar(PAGE));
    const tl = document.createElement("div");
    app.appendChild(tl);
    await timeline(PAGE, tl);
  })();
})();
