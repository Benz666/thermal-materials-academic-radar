"""Fetchers. Each returns a list of raw items:
{kind, title, url, doi, authors, venue, published, abstract, source}
kind: preprint | paper | tool | news | conference | cfp
"""
from __future__ import annotations

import datetime as dt
import re
import time
import urllib.parse

import feedparser

from .common import clean_text, http_get, iso


def _date(struct) -> str:
    if not struct:
        return ""
    return dt.date(*struct[:3]).isoformat()


# ------------------------------------------------------------------ arXiv
ARXIV_API = "http://export.arxiv.org/api/query"


def _arxiv(query: str, n: int) -> list[dict]:
    params = {"search_query": query, "sortBy": "submittedDate", "sortOrder": "descending",
              "start": 0, "max_results": n}
    feed = feedparser.parse(http_get(ARXIV_API, params, timeout=90).content)
    out = []
    for e in feed.entries:
        aid = e.id.rsplit("/abs/", 1)[-1]
        out.append({
            "kind": "preprint",
            "title": clean_text(e.title),
            "url": f"https://arxiv.org/abs/{re.sub(r'v\\d+$', '', aid)}",
            "doi": e.get("arxiv_doi", ""),
            "authors": [a.name for a in e.get("authors", [])],
            "venue": "arXiv · " + e.get("arxiv_primary_category", {}).get("term", ""),
            "published": _date(e.get("published_parsed")),
            "abstract": clean_text(e.get("summary")),
            "source": "arXiv",
        })
    return out


def fetch_arxiv(cfg: dict, since: dt.date) -> list[dict]:
    cats = " OR ".join(f"cat:{c}" for c in cfg["categories"])
    items = _arxiv(cats, cfg.get("max_results", 300))
    for q in cfg.get("queries", []):
        time.sleep(3)  # arXiv API etiquette
        items += _arxiv(q, cfg.get("query_max_results", 100))
    return [i for i in items if i["published"] >= iso(since)]


# ------------------------------------------------------------------ Crossref
def fetch_crossref(journal: dict, since: dt.date) -> list[dict]:
    url = f"https://api.crossref.org/journals/{journal['issn']}/works"
    params = {"filter": f"from-created-date:{iso(since)},type:journal-article",
              "rows": 300, "sort": "created", "order": "desc",
              "select": "DOI,title,abstract,author,container-title,created,URL"}
    msg = http_get(url, params).json()["message"]
    out = []
    for w in msg.get("items", []):
        title = clean_text(" ".join(w.get("title") or []))
        if not title:
            continue
        authors = [f"{a.get('given', '')} {a.get('family', '')}".strip() for a in w.get("author", [])]
        out.append({
            "kind": "paper",
            "title": title,
            "url": f"https://doi.org/{w['DOI']}",
            "doi": w["DOI"].lower(),
            "authors": authors,
            "venue": journal["name"],
            "published": w.get("created", {}).get("date-time", "")[:10],
            "abstract": clean_text(w.get("abstract")),
            "source": "Crossref",
        })
    return out


# ------------------------------------------------------------------ OpenAlex
def _openalex_abstract(inv: dict | None) -> str:
    if not inv:
        return ""
    pos = sorted((p, w) for w, ps in inv.items() for p in ps)
    return " ".join(w for _, w in pos)


def fetch_openalex(search: str, since: dt.date, n: int) -> list[dict]:
    params = {"search": search, "per-page": min(n, 200), "sort": "publication_date:desc",
              "filter": f"from_publication_date:{iso(since)},type:article"}
    res = http_get("https://api.openalex.org/works", params).json()["results"]
    out = []
    for w in res:
        doi = (w.get("doi") or "").replace("https://doi.org/", "").lower()
        src = ((w.get("primary_location") or {}).get("source") or {})
        is_pre = src.get("type") == "repository"
        out.append({
            "kind": "preprint" if is_pre else "paper",
            "title": clean_text(w.get("title")),
            "url": w.get("doi") or (w.get("primary_location") or {}).get("landing_page_url") or w["id"],
            "doi": doi,
            "authors": [a["author"]["display_name"] for a in w.get("authorships", [])],
            "venue": src.get("display_name") or "OpenAlex",
            "published": w.get("publication_date", ""),
            "abstract": clean_text(_openalex_abstract(w.get("abstract_inverted_index"))),
            "source": "OpenAlex",
        })
    return [o for o in out if o["title"]]


# ------------------------------------------------------------------ RSS / Atom
def fetch_feed(url: str, name: str, kind: str, since: dt.date) -> list[dict]:
    feed = feedparser.parse(http_get(url).content)
    if feed.bozo and not feed.entries:
        raise ValueError(f"unparseable feed ({feed.bozo_exception})")
    out = []
    for e in feed.entries[:60]:
        pub = _date(e.get("published_parsed") or e.get("updated_parsed"))
        if pub and pub < iso(since):
            continue
        body = e.get("summary") or ""
        if e.get("content"):
            body = e.content[0].get("value", body)
        out.append({
            "kind": kind,
            "title": clean_text(e.get("title")),
            "url": e.get("link", url),
            "doi": "",
            "authors": [],
            "venue": name,
            "published": pub or iso(since),
            "abstract": clean_text(body, 3000),
            "source": name,
        })
    return out


def fetch_release(tool: dict, since: dt.date) -> list[dict]:
    items = fetch_feed(f"https://github.com/{tool['repo']}/releases.atom", tool["name"], "tool", since)
    for i in items:
        i["title"] = f"{tool['name']} {i['title']}".strip() if tool["name"].split()[0].lower() not in i["title"].lower() else i["title"]
        i["source"] = "GitHub releases"
    return items


def fetch_wikicfp(category: str, since: dt.date) -> list[dict]:
    url = "http://www.wikicfp.com/cfp/rss?cat=" + urllib.parse.quote(category)
    items = fetch_feed(url, f"WikiCFP · {category}", "cfp", since - dt.timedelta(days=10))
    for i in items:
        i["source"] = "WikiCFP"
    return items


# ------------------------------------------------------------------ conference pages
_DEADLINE = re.compile(r"(deadline|abstract|submission|call for|due|registration opens|notification)", re.I)
_DATEISH = re.compile(r"(20\d\d|Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)", re.I)


def fetch_conference_page(conf: dict) -> dict:
    """Returns {'text_hash', 'snippets'} for change detection."""
    import hashlib

    r = http_get(conf["url"])
    text = clean_text(re.sub(r"(?is)<(script|style|nav|footer)[^>]*>.*?</\1>", " ", r.text))
    sentences = re.split(r"(?<=[.!?])\s+|\s{2,}|\s[|•·]\s", text)
    snippets = []
    for s in sentences:
        s = s.strip()
        if 15 < len(s) < 260 and _DEADLINE.search(s) and _DATEISH.search(s) and s not in snippets:
            snippets.append(s)
    return {"text_hash": hashlib.sha1(text.encode()).hexdigest(), "snippets": snippets[:8],
            "excerpt": clean_text(text, 2500)}


# ------------------------------------------------------------------ watched authors
def fetch_openalex_authors(authors: list[dict], since: dt.date) -> list[dict]:
    """New works by watched OpenAlex author IDs (batched 25 per request)."""
    ids = [a["id"] for a in authors if a.get("id")]
    out = []
    for k in range(0, len(ids), 25):
        flt = f"authorships.author.id:{'|'.join(ids[k:k + 25])},from_publication_date:{iso(since)}"
        res = http_get("https://api.openalex.org/works", {"filter": flt, "per-page": 200,
                                                          "sort": "publication_date:desc"}).json()["results"]
        for w in res:
            src = ((w.get("primary_location") or {}).get("source") or {})
            out.append({
                "kind": "preprint" if src.get("type") == "repository" else "paper",
                "title": clean_text(w.get("title")),
                "url": w.get("doi") or (w.get("primary_location") or {}).get("landing_page_url") or w["id"],
                "doi": (w.get("doi") or "").replace("https://doi.org/", "").lower(),
                "authors": [a["author"]["display_name"] for a in w.get("authorships", [])],
                "author_ids": [(a["author"].get("id") or "").rsplit("/", 1)[-1] for a in w.get("authorships", [])],
                "venue": src.get("display_name") or "OpenAlex",
                "published": w.get("publication_date", ""),
                "abstract": clean_text(_openalex_abstract(w.get("abstract_inverted_index"))),
                "source": "Watched authors",
            })
    return [o for o in out if o["title"]]


# ------------------------------------------------------------------ GitHub hot repos
def fetch_github_repos(query: str, since: dt.date, token: str | None, min_stars: int) -> list[dict]:
    """Repos matching `query`, pushed recently, sorted by stars."""
    import requests

    headers = {"Accept": "application/vnd.github+json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    q = f"{query} pushed:>={iso(since)} stars:>={min_stars}"
    r = requests.get("https://api.github.com/search/repositories", headers=headers, timeout=40,
                     params={"q": q, "sort": "stars", "order": "desc", "per_page": 30})
    r.raise_for_status()
    out = []
    for repo in r.json().get("items", []):
        out.append({
            "kind": "repo",
            "title": repo["full_name"],
            "url": repo["html_url"],
            "doi": "",
            "authors": [repo["owner"]["login"]],
            "venue": "GitHub" + (f" · {repo['language']}" if repo.get("language") else ""),
            "published": repo["pushed_at"][:10],
            "abstract": clean_text(repo.get("description") or "") +
                        (" Topics: " + ", ".join(repo.get("topics", [])) + "." if repo.get("topics") else ""),
            "source": "GitHub search",
            "stars": repo["stargazers_count"],
            "created": repo["created_at"][:10],
        })
    return out


# ------------------------------------------------------------------ special-issue pages
def fetch_collection_links(page: dict) -> list[dict]:
    """Links on a journal 'collections / calls for papers' page."""
    r = http_get(page["url"])
    base = re.match(r"https?://[^/]+", page["url"]).group(0)
    out, seen = [], set()
    for href, text in re.findall(r'<a[^>]+href="([^"#]+)"[^>]*>(.*?)</a>', r.text, re.S):
        title = clean_text(text)
        if len(title) < 12 or len(title) > 200:
            continue
        if page.get("link_contains") and page["link_contains"] not in href:
            continue
        url = href if href.startswith("http") else base + href
        if url in seen:
            continue
        seen.add(url)
        out.append({"kind": "special-issue", "title": title, "url": url, "doi": "", "authors": [],
                    "venue": page["name"], "published": "", "abstract": "", "source": "Journal calls"})
    return out


def fetch_page_text(url: str, limit: int = 3000) -> str:
    r = http_get(url)
    text = clean_text(re.sub(r"(?is)<(script|style|nav|footer|header)[^>]*>.*?</\1>", " ", r.text))
    return text[:limit]
