"""Resolve watched authors to OpenAlex author IDs.

    python -m radar.authors            # resolve entries without an id, rewrite config/authors.yaml

Each entry: {name, hint, id}. `hint` is an institution substring used to pick
the right person among namesakes. Review the result by hand: the chosen
institution and works count are written as a comment-like `matched` field.
"""
from __future__ import annotations

import yaml

from .common import CONFIG, http_get


def _insts(a: dict) -> list[str]:
    names = [i.get("display_name", "") for i in a.get("last_known_institutions") or []]
    names += [x["institution"].get("display_name", "") for x in a.get("affiliations") or []]
    return names


def resolve_by_works(name: str, hint: str, topic: str) -> dict | None:
    """Most frequent author id among works on `topic` whose raw author name matches."""
    from collections import Counter
    params = {"filter": f"raw_author_name.search:{name},title_and_abstract.search:{topic}", "per-page": 100}
    works = http_get("https://api.openalex.org/works", params).json()["results"]
    last = name.split()[-1].lower()
    hint_l = [h.strip().lower() for h in hint.split("|") if h.strip()]
    cnt, label = Counter(), {}
    for w in works:
        for a in w["authorships"]:
            raw = (a.get("raw_author_name") or "").lower()
            if last not in raw:
                continue
            insts = " ; ".join(i.get("display_name", "") for i in a.get("institutions", [])).lower()
            if hint_l and not any(h in insts for h in hint_l):
                continue
            if not (a.get("author") or {}).get("id"):
                continue
            aid = a["author"]["id"].rsplit("/", 1)[-1]
            cnt[aid] += 1
            label[aid] = a["author"]["display_name"]
    if not cnt:
        return None
    aid, n = cnt.most_common(1)[0]
    return {"id": aid, "matched": f"{label[aid]} · {n} matching {topic!r} works with {hint!r}"}


def resolve(name: str, hint: str) -> dict | None:
    res = http_get("https://api.openalex.org/authors", {"search": name, "per-page": 25}).json()["results"]
    hint_l = [h.strip().lower() for h in hint.split("|") if h.strip()]
    best = None
    for a in res:
        insts = " ; ".join(_insts(a)).lower()
        if hint_l and not any(h in insts for h in hint_l):
            continue
        if best is None or a["works_count"] > best["works_count"]:
            best = a
    if not best:
        return None
    return {"id": best["id"].rsplit("/", 1)[-1],
            "matched": f"{best['display_name']} · {', '.join(_insts(best)[:2])} · {best['works_count']} works"}


def main() -> None:
    path = CONFIG / "authors.yaml"
    doc = yaml.safe_load(path.read_text(encoding="utf-8"))
    for a in doc["authors"]:
        if a.get("id"):
            continue
        r = resolve_by_works(a["name"], a.get("hint", ""), a.get("topic", "thermal")) or resolve(a["name"], a.get("hint", ""))
        if r:
            a.update(r)
        else:
            a["matched"] = "NOT FOUND — check name/hint"
        print(f"{a['name']:<22} -> {a.get('id', '-'):<12} {a['matched']}")
    header = path.read_text(encoding="utf-8").split("authors:")[0]
    path.write_text(header + yaml.safe_dump(doc, allow_unicode=True, sort_keys=False, width=200), encoding="utf-8")


if __name__ == "__main__":
    main()
