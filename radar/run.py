"""Daily pipeline.

    python -m radar.run            # fetch → score → rule summaries → archive → queue → build
    python -m radar.run --build    # rebuild the site only
    python -m radar.run --ingest   # merge Claude output from data/llm_out/ → archive → build

Categories (one page each): papers, industry, conferences.
"""
from __future__ import annotations

import argparse
import datetime as dt
import os
import re
import shutil
import time
import traceback
from collections import Counter

from . import sources as S
from .common import DATA, clean_text, item_id, iso, load_yaml, norm_title, read_json, today, write_json
from .rules import summarize
from .score import get_scorer

CAT_OF = {"preprint": "papers", "paper": "papers", "news": "industry", "tool": "industry", "repo": "industry",
          "conference": "conferences", "cfp": "conferences", "special-issue": "conferences"}
STATE = DATA / "state.json"
ARCHIVE = DATA / "archive"
QUEUE = DATA / "llm_queue.json"
LLM_OUT = DATA / "llm_out"


# ------------------------------------------------------------------ archive helpers
def archive_path(cat: str, day: str):
    return ARCHIVE / cat / f"{day[:7]}.json"


def add_to_archive(items: list[dict]) -> None:
    by_file: dict = {}
    for it in items:
        by_file.setdefault(archive_path(it["cat"], it["first_seen"]), []).append(it)
    for path, new in by_file.items():
        cur = read_json(path, [])
        ids = {x["id"] for x in cur}
        cur += [x for x in new if x["id"] not in ids]
        cur.sort(key=lambda x: (x["first_seen"], -x.get("score", 0)), reverse=True)
        write_json(path, cur)


def all_archive_files():
    return sorted(ARCHIVE.glob("*/*.json"))


# ------------------------------------------------------------------ fetching
class Health:
    def __init__(self):
        self.rows = []

    def run(self, name, fn, *a, **kw):
        t = time.time()
        try:
            res = fn(*a, **kw)
            self.rows.append({"source": name, "ok": True, "n": len(res) if isinstance(res, list) else 1,
                              "secs": round(time.time() - t, 1)})
            return res
        except Exception as e:  # noqa: BLE001 — one bad source must not stop the run
            self.rows.append({"source": name, "ok": False, "error": f"{type(e).__name__}: {str(e)[:160]}"})
            print(f"[warn] {name}: {e}")
            return []


def fetch_all(cfg: dict, conf: dict, authors: list[dict], state: dict, H: Health) -> list[dict]:
    since = today() - dt.timedelta(days=cfg["lookback_days"])
    raw: list[dict] = []
    raw += H.run("arXiv", S.fetch_arxiv, cfg["arxiv"], since)
    for j in cfg["journals"]:
        raw += H.run(f"Crossref · {j['name']}", S.fetch_crossref, j, since)
    for q in cfg["openalex"]["searches"]:
        raw += H.run(f"OpenAlex · {q}", S.fetch_openalex, q, since, cfg["openalex"]["per_search"])
    if cfg.get("watched_authors"):
        raw += H.run("OpenAlex · watched authors", S.fetch_openalex_authors, authors, since - dt.timedelta(days=10))
    for t in cfg["tools"]:
        raw += H.run(f"Release · {t['name']}", S.fetch_release, t, since)
    for f in cfg["feeds"]:
        items = H.run(f"Feed · {f['name']}", S.fetch_feed, f["url"], f["name"], "news", since)
        for i in items:
            i["filter"] = f.get("filter", True)
        raw += items
    token = os.environ.get("GITHUB_TOKEN")
    hr = cfg.get("hot_repos", {})
    for q in hr.get("queries", []):
        raw += H.run(f"GitHub · {q}", S.fetch_github_repos, q, since, token, hr.get("min_stars", 30))
        time.sleep(1 if token else 7)
    for cat in conf.get("wikicfp", []):
        raw += H.run(f"WikiCFP · {cat}", S.fetch_wikicfp, cat, since)
    raw += special_issues(cfg, state, H)
    raw += conference_changes(conf, state, H)
    return raw


def special_issues(cfg: dict, state: dict, H: Health) -> list[dict]:
    seen = state.setdefault("si_links", {})
    sc = get_scorer()
    out = []
    for page in cfg.get("special_issue_pages", []):
        links = H.run(f"Calls · {page['name']}", S.fetch_collection_links, page)
        first_visit = page["url"] not in state.setdefault("si_pages", [])
        for ln in links:
            if ln["url"] in seen:
                continue
            seen[ln["url"]] = iso(today())
            if first_visit:
                pass  # still evaluate existing open calls on the first run
            if not sc.score(ln["title"])["themes"]:
                continue  # title shares no term with any theme
            try:
                text = S.fetch_page_text(ln["url"])
            except Exception:  # noqa: BLE001
                text = ""
            if "open for submission" not in text.lower() and "deadline" not in text.lower():
                continue
            ln["abstract"] = text
            ln["published"] = iso(today())
            out.append(ln)
        if first_visit:
            state["si_pages"].append(page["url"])
    return out


def conference_changes(conf: dict, state: dict, H: Health) -> list[dict]:
    hashes = state.setdefault("conf_hash", {})
    out = []
    for c in conf["conferences"]:
        if c.get("fetch") is False:
            continue
        res = H.run(f"Conference · {c['name']}", S.fetch_conference_page, c)
        if not res:
            continue
        old = hashes.get(c["url"])
        hashes[c["url"]] = res["text_hash"]
        if old is None or old == res["text_hash"]:
            continue  # first visit only records the page; cards appear on later changes
        status = "Website updated"
        snippet = " ".join(res["snippets"][:5])
        out.append({
            "kind": "conference",
            "title": f"{c['name']} — {status.lower()}",
            "url": c["url"], "doi": "", "authors": [], "venue": c.get("area", ""),
            "published": iso(today()),
            "abstract": (f"{c.get('why', '')} " + (f"Deadline-related text on the page: {snippet}" if snippet else
                         "No deadline sentences found on the page.")).strip(),
            "source": "Conference watch", "conf_name": c["name"], "fit": c.get("fit", ""),
            "page_excerpt": res["excerpt"][:1500], "always": True,
        })
    return out


# ------------------------------------------------------------------ processing
def process(raw: list[dict], cfg: dict, authors: list[dict], state: dict) -> list[dict]:
    sc = get_scorer()
    seen = state.setdefault("seen", {})
    seen_titles = state.setdefault("seen_titles", {})
    watched_ids = {a["id"]: a["name"] for a in authors if a.get("id")}
    watched_names = {a["name"].lower(): a["name"] for a in authors}
    stars = state.setdefault("repo_stars", {})
    day = iso(today())
    kept: dict[str, dict] = {}

    for it in raw:
        if not it.get("title"):
            continue
        key = it.get("doi") or it["url"]
        iid = item_id(it["kind"] if it["kind"] in ("repo", "conference") else "", key, day if it["kind"] in ("repo", "conference") else "")
        nt = norm_title(it["title"])
        if it["kind"] in ("paper", "preprint", "special-issue", "cfp", "news", "tool"):
            if iid in seen or nt in seen_titles:
                continue
        text = f"{it['title']}. {it.get('abstract', '')}"
        if sc.excluded(text):
            continue
        s = sc.score(text)
        themes = sc.qualifying(s)
        watched = sorted({watched_ids[a] for a in it.get("author_ids", []) if a in watched_ids} |
                         {watched_names[a.lower()] for a in it.get("authors", []) if a.lower() in watched_names})
        k = it["kind"]
        focus, adj = sc.approach(text) if k in ("paper", "preprint") else ("", 0)
        if k in ("paper", "preprint"):
            if not themes or s["total"] + adj + 2 * len(watched) < sc.min_paper_score:
                continue
        elif k == "news":
            if it.get("filter", True) and not themes and s["industry"] < sc.min_score:
                continue
        elif k == "repo":
            prev = stars.get(it["title"])
            stars[it["title"]] = it["stars"]
            grew = it["stars"] - prev if prev is not None else None
            it["star_delta"] = grew
            # show a repo when first discovered, or when it gained >= 5% / 25 stars since yesterday
            if prev is not None and not (grew and (grew >= 25 or grew >= 0.05 * prev)):
                continue
            if not (themes or s["industry"] >= 1 or s["total"] >= 1):
                continue
        elif k in ("cfp", "special-issue"):
            if not themes:
                continue
        # tools and conference changes are always kept
        score = s["total"] + adj + 2 * len(watched) + (3 if k in ("tool", "conference") else 0)
        it.update({
            "id": iid, "cat": CAT_OF[k], "first_seen": day, "themes": themes or (["industry"] if s["industry"] else []),
            "score": score, "kw_score": score, "focus": focus, "matched": s["matched"], "watched": watched,
            "authors": it.get("authors", [])[:8] + (["et al."] if len(it.get("authors", [])) > 8 else []),
            "abstract": clean_text(it.get("abstract", ""), 1800),
        })
        it.pop("author_ids", None)
        it.pop("filter", None)
        if iid in kept:  # same work from two sources: keep the richer record
            if len(it["abstract"]) <= len(kept[iid]["abstract"]):
                continue
        kept[iid] = it

    # dedupe by normalised title across sources (arXiv vs journal vs OpenAlex)
    by_title: dict[str, dict] = {}
    for it in kept.values():
        nt = norm_title(it["title"])
        cur = by_title.get(nt)
        if cur is None or (cur["kind"] == "preprint" and it["kind"] == "paper") or len(it["abstract"]) > len(cur["abstract"]) + 200:
            by_title[nt] = it

    # daily caps per page
    caps = cfg.get("daily_caps", {})
    final = []
    for cat in ("papers", "industry", "conferences"):
        items = sorted((i for i in by_title.values() if i["cat"] == cat), key=lambda i: -i["score"])
        final += items[: caps.get(cat, 50)]

    for it in final:
        it["summary"] = summarize(it)
        seen[it["id"]] = day
        seen_titles[norm_title(it["title"])] = day
    # forget very old dedupe keys
    cutoff = iso(today() - dt.timedelta(days=cfg.get("dedupe_days", 400)))
    for d in (seen, seen_titles):
        for k in [k for k, v in d.items() if v < cutoff]:
            del d[k]
    return final


# ------------------------------------------------------------------ Claude queue / ingest
def write_queue(new_items: list[dict]) -> None:
    """Items for the Claude routine: today's best papers + all industry/conference items."""
    q = read_json(QUEUE, {"items": []})
    known = {x["id"] for x in q["items"]}
    pick = sorted([i for i in new_items if i["cat"] == "papers"], key=lambda i: -i["score"])[:15]
    pick += sorted([i for i in new_items if i["cat"] == "industry"], key=lambda i: -i["score"])[:10]
    pick += [i for i in new_items if i["cat"] == "conferences"]
    for i in pick:
        if i["id"] in known:
            continue
        q["items"].append({k: i.get(k) for k in ("id", "cat", "kind", "title", "url", "venue", "authors",
                                                   "published", "first_seen", "abstract", "themes", "matched",
                                                   "watched", "focus", "page_excerpt")})
    q["updated"] = iso(today())
    write_json(QUEUE, q)


def ingest() -> int:
    """Merge data/llm_out/*.json: {"summaries": {id: {what, why, how, impact}}, "new_items": [...]}"""
    files = sorted(p for p in LLM_OUT.glob("*.json"))
    if not files:
        return 0
    summaries, new_items = {}, []
    for f in files:
        d = read_json(f, {})
        summaries.update(d.get("summaries", {}))
        new_items += d.get("new_items", [])
    n = 0
    for path in all_archive_files():
        items = read_json(path, [])
        changed = False
        for it in items:
            s = summaries.get(it["id"])
            if s and all(k in s for k in ("what", "why", "how", "impact")):
                it["summary"] = {**{k: clean_text(s[k], 700) for k in ("what", "why", "how", "impact")}, "by": "claude"}
                r = s.get("relevance")
                if isinstance(r, int) and 1 <= r <= 5:
                    # Claude's 1-5 relevance rating re-ranks the keyword score
                    it.setdefault("kw_score", it.get("score", 0))
                    it["relevance"] = r
                    it["score"] = it["kw_score"] + 3 * (r - 3)
                changed = True
                n += 1
        if changed:
            write_json(path, items)
    # new items found by the weekly web search (special issues etc.)
    state = read_json(STATE, {})
    sc = get_scorer()
    add = []
    for it in new_items:
        if not it.get("title") or not it.get("url"):
            continue
        iid = item_id("", it["url"])
        if iid in state.get("seen", {}):
            continue
        kind = it.get("kind", "special-issue")
        s = sc.score(f"{it['title']}. {it.get('abstract', '')}")
        add.append({
            "id": iid, "cat": CAT_OF.get(kind, "conferences"), "kind": kind, "title": clean_text(it["title"]),
            "url": it["url"], "doi": "", "authors": [], "venue": clean_text(it.get("venue", "")),
            "published": it.get("published", iso(today())), "first_seen": iso(today()),
            "abstract": clean_text(it.get("abstract", ""), 1800), "source": "Claude web search",
            "themes": sc.qualifying(s) or [], "score": s["total"] + 3, "matched": s["matched"], "watched": [],
            "deadline": it.get("deadline", ""),
            "summary": ({**{k: clean_text(it["summary"][k], 700) for k in ("what", "why", "how", "impact")}, "by": "claude"}
                        if isinstance(it.get("summary"), dict) else None),
        })
        state.setdefault("seen", {})[iid] = iso(today())
    for a in add:
        if not a["summary"]:
            a["summary"] = summarize(a)
    if add:
        add_to_archive(add)
        write_json(STATE, state)
    # drop processed items from the queue, archive the output files
    q = read_json(QUEUE, {"items": []})
    q["items"] = [x for x in q["items"] if x["id"] not in summaries]
    write_json(QUEUE, q)
    done = LLM_OUT / "done"
    done.mkdir(parents=True, exist_ok=True)
    for f in files:
        shutil.move(str(f), done / f.name)
    print(f"ingested {n} summaries, {len(add)} new items")
    return n + len(add)


# ------------------------------------------------------------------ topic suggestions
STOP = set("""a an the of and or in on for to with by from at as is are was were be been this that these those we our
their its into via using based new study results show shows approach method methods model models paper work high low
large small two three can also than which while between under over such both more most first however here""".split())


def topic_suggestions(state: dict) -> None:
    """Weekly: frequent bigrams in this week's kept papers that are not keywords yet."""
    if today().weekday() != 0 and (DATA / "topic_suggestions.json").exists():
        return
    sc = get_scorer()
    since = iso(today() - dt.timedelta(days=7))
    cnt = Counter()
    for path in sorted((ARCHIVE / "papers").glob("*.json"))[-2:]:
        for it in read_json(path, []):
            if it["first_seen"] < since:
                continue
            words = [w for w in re.findall(r"[a-z][a-z0-9\-]+", f"{it['title']} {it['abstract']}".lower())]
            for a, b in zip(words, words[1:]):
                if a in STOP or b in STOP:
                    continue
                bg = f"{a} {b}"
                if bg not in sc.all_terms and not any(bg in t for t in sc.all_terms):
                    cnt[bg] += 1
    write_json(DATA / "topic_suggestions.json",
               {"week_of": iso(today()), "candidates": [{"term": t, "count": c} for t, c in cnt.most_common(40) if c >= 3]})


# ------------------------------------------------------------------ main
def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--build", action="store_true", help="only rebuild the site")
    ap.add_argument("--ingest", action="store_true", help="merge Claude output, then rebuild")
    args = ap.parse_args()

    from .build import build

    if args.build:
        build()
        return
    if args.ingest:
        ingest()
        build()
        return

    cfg = load_yaml("sources.yaml")
    conf = load_yaml("conferences.yaml")
    authors = load_yaml("authors.yaml")["authors"]
    state = read_json(STATE, {})
    H = Health()
    raw = fetch_all(cfg, conf, authors, state, H)
    new = process(raw, cfg, authors, state)
    add_to_archive(new)
    write_queue(new)
    try:
        topic_suggestions(state)
    except Exception:  # noqa: BLE001
        traceback.print_exc()
    state["last_run"] = dt.datetime.now(dt.timezone.utc).isoformat(timespec="minutes")
    write_json(STATE, state)
    write_json(DATA / "health.json", {"run": state["last_run"], "sources": H.rows,
                                      "new": Counter(i["cat"] for i in new)})
    print(f"raw {len(raw)} → new {len(new)} ({dict(Counter(i['cat'] for i in new))}); "
          f"failed sources: {sum(not r['ok'] for r in H.rows)}/{len(H.rows)}")
    build()


if __name__ == "__main__":
    main()
