"""Static site: public/ = HTML shells + assets + month-sharded JSON data."""
from __future__ import annotations

import datetime as dt
import html
import shutil

from .common import DATA, PUBLIC, ROOT, latex_to_unicode, load_yaml, read_json, today, write_json
from .score import get_scorer

SITE_TITLE = "Thermal Materials Academic Radar"
PAGES = {
    "home": ("", "Overview", "Daily radar for phonon & thermal transport, MLIPs, electronics cooling and the venues that publish them."),
    "papers": ("papers/", "Papers & Preprints", "Journal articles and preprints matching the research themes, newest week first."),
    "industry": ("industry/", "Industry & Tools", "Company and trade-press news, code releases, and fast-rising GitHub repositories."),
    "conferences": ("conferences/", "Conferences & Calls", "US conferences, special issues and calls for papers, with deadlines."),
}


def _shell(page: str) -> str:
    path, title, lede = PAGES[page]
    depth = "../" if path else ""
    nav = "".join(
        f'<a href="{depth}{p}" class="{"active" if k == page else ""}">{html.escape(t)}</a>'
        for k, (p, t, _) in PAGES.items())
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{html.escape(title)} · {SITE_TITLE}</title>
<meta name="description" content="{html.escape(lede)}">
<meta name="robots" content="noindex">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Funnel+Sans:ital,wght@0,300;0,400;0,500;0,600;0,700;1,400&family=Instrument+Serif:ital@0;1&display=swap">
<link rel="icon" type="image/svg+xml" href="{depth}assets/favicon.svg">
<link rel="stylesheet" href="{depth}assets/style.css">
<link rel="alternate" type="application/rss+xml" title="{SITE_TITLE}" href="{depth}feed.xml">
</head>
<body data-page="{page}" data-root="{depth}">
<div class="haze" aria-hidden="true"></div>
<header class="top">
  <a class="brand" href="{depth}"><span class="dot"></span>Thermal Materials <em>Academic Radar</em></a>
  <nav>{nav}</nav>
  <button class="theme-toggle" type="button" aria-label="Toggle dark mode">◐</button>
</header>
<main>
  <section class="hero">
    <h1>{html.escape(title)}</h1>
    <p class="lede">{html.escape(lede)}</p>
    <p class="runinfo" id="runinfo"></p>
  </section>
  <div id="app"><p class="loading">Loading…</p></div>
</main>
<footer>
  <p>Updated daily, around 6 am US Eastern. Always check the original source.</p>
  <p id="health"></p>
</footer>
<dialog id="detail"><article id="detail-body"></article></dialog>
<script src="{depth}assets/app.js" defer></script>
</body>
</html>
"""


def _meta() -> dict:
    sc = get_scorer()
    conf = load_yaml("conferences.yaml")
    health = read_json(DATA / "health.json", {})
    sugg = read_json(DATA / "topic_suggestions.json", {})
    rows = health.get("sources", [])
    deadlines = []
    for c in conf["conferences"]:
        nx = c.get("next") or {}
        if nx.get("abstract_deadline") and nx["abstract_deadline"] >= today().isoformat():
            deadlines.append({"name": c["name"], "edition": nx.get("edition", ""), "deadline": nx["abstract_deadline"],
                              "dates": nx.get("dates", ""), "location": nx.get("location", ""), "url": c["url"]})
    deadlines.sort(key=lambda d: d["deadline"])
    return {
        "title": SITE_TITLE,
        "built": dt.datetime.now(dt.timezone.utc).isoformat(timespec="minutes"),
        "last_run": health.get("run", ""),
        "themes": [{"id": t["id"], "name": t["name"], "color": t["color"]} for t in sc.themes],
        "health": {"ok": sum(r["ok"] for r in rows), "total": len(rows),
                   "failed": [r for r in rows if not r["ok"]]},
        "deadlines": deadlines,
        "conferences": [{k: c.get(k) for k in ("name", "url", "area", "fit", "why", "next")} for c in conf["conferences"]],
        "suggestions": sugg.get("candidates", [])[:20],
    }


def _feed(items: list[dict]) -> str:
    def esc(s):
        return html.escape(s or "", quote=True)
    entries = "".join(
        f"<item><title>{esc(i['title'])}</title><link>{esc(i['url'])}</link><guid>{esc(i['id'])}</guid>"
        f"<pubDate>{esc(i['first_seen'])}</pubDate><description>{esc((i.get('summary') or {}).get('what', ''))}</description></item>"
        for i in items[:80])
    return (f'<?xml version="1.0" encoding="UTF-8"?><rss version="2.0"><channel><title>{SITE_TITLE}</title>'
            f"<link>https://benz666.github.io/thermal-materials-academic-radar/</link>"
            f"<description>Daily research radar</description>{entries}</channel></rss>")


def build() -> None:
    if PUBLIC.exists():
        shutil.rmtree(PUBLIC)
    (PUBLIC / "assets").mkdir(parents=True)
    for f in (ROOT / "web").iterdir():
        shutil.copy(f, PUBLIC / "assets" / f.name)
    for page, (path, _, _) in PAGES.items():
        out = PUBLIC / path / "index.html"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(_shell(page), encoding="utf-8")

    recent = []
    for cat in ("papers", "industry", "conferences"):
        months = []
        for f in sorted((DATA / "archive" / cat).glob("*.json"), reverse=True):
            items = read_json(f, [])
            for it in items:
                it.pop("page_excerpt", None)
                for k in ("title", "abstract"):
                    it[k] = latex_to_unicode(it.get(k, ""))
                if isinstance(it.get("summary"), dict):
                    it["summary"] = {k: latex_to_unicode(v) if isinstance(v, str) else v for k, v in it["summary"].items()}
            write_json(PUBLIC / "data" / cat / f.name, items)
            months.append({"month": f.stem, "count": len(items)})
            if len(recent) < 300:
                recent += items
        write_json(PUBLIC / "data" / cat / "index.json", months)
    write_json(PUBLIC / "data" / "meta.json", _meta())
    recent.sort(key=lambda i: (i["first_seen"], i.get("score", 0)), reverse=True)
    (PUBLIC / "feed.xml").write_text(_feed(recent), encoding="utf-8")
    (PUBLIC / ".nojekyll").write_text("")
    print(f"built site → {PUBLIC}")
