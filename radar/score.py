"""Keyword scoring against config/topics.yaml."""
from __future__ import annotations

import re
from functools import lru_cache

from .common import load_yaml


def _pattern(term: str) -> re.Pattern:
    prefix = term.endswith("*")
    t = term.rstrip("*")
    body = re.escape(t).replace(r"\ ", r"[\s\-]+").replace(r"\-", r"[\s\-]?")
    tail = r"\w*" if prefix else ""
    flags = 0 if (any(c.isupper() for c in t) and len(t) <= 6 and " " not in t) else re.I
    return re.compile(rf"(?<![\w]){body}{tail}(?![\w])", flags)


class Scorer:
    def __init__(self) -> None:
        cfg = load_yaml("topics.yaml")
        self.min_score = cfg["min_score"]
        self.min_paper_score = cfg.get("min_paper_score", cfg["min_score"])
        self.exclude = [_pattern(t) for t in cfg.get("exclude", [])]
        self.themes = []
        for th in cfg["themes"] + [cfg["industry"]]:
            self.themes.append({
                "id": th["id"], "name": th["name"], "color": th.get("color", "#2B6EFF"),
                "core": [(t, _pattern(t)) for t in th.get("core", [])],
                "related": [(t, _pattern(t)) for t in th.get("related", [])],
                "context": [_pattern(t) for t in th.get("context", [])],
            })
        self.projects = [{"name": p["name"], "keys": [(k, _pattern(k)) for k in p["keys"]]}
                         for p in cfg.get("projects", [])]
        self.all_terms = {t.rstrip("*").lower() for th in self.themes for t, _ in th["core"] + th["related"]}

    def excluded(self, text: str) -> bool:
        return any(p.search(text) for p in self.exclude)

    def score(self, text: str) -> dict:
        """-> {'themes': {id: score}, 'matched': [terms], 'total': int}"""
        out, matched = {}, []
        for th in self.themes:
            if th["context"] and not any(p.search(text) for p in th["context"]):
                continue
            s = 0
            for t, p in th["core"]:
                if p.search(text):
                    s += 3
                    matched.append(t.rstrip("*"))
            for t, p in th["related"]:
                if p.search(text):
                    s += 1
                    matched.append(t.rstrip("*"))
            if s:
                out[th["id"]] = s
        seen, uniq = set(), []
        for m in matched:
            if m.lower() not in seen:
                seen.add(m.lower())
                uniq.append(m)
        research = {k: v for k, v in out.items() if k != "industry"}
        return {"themes": out, "matched": uniq[:12],
                "total": sum(research.values()), "industry": out.get("industry", 0)}

    def qualifying(self, sc: dict, include_industry: bool = False) -> list[str]:
        ids = [k for k, v in sc["themes"].items() if v >= self.min_score and (include_industry or k != "industry")]
        return sorted(ids, key=lambda k: -sc["themes"][k])

    def projects_for(self, text: str, n: int = 2) -> list[tuple[str, list[str]]]:
        hits = []
        for p in self.projects:
            keys = [k.rstrip("*") for k, pat in p["keys"] if pat.search(text)]
            if keys:
                hits.append((len(keys), p["name"], keys))
        hits.sort(key=lambda h: -h[0])
        return [(name, keys) for _, name, keys in hits[:n]]


@lru_cache(maxsize=1)
def get_scorer() -> Scorer:
    return Scorer()
