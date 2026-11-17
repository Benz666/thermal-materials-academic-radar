"""Rule-based What / Why / How / Impact summary (no LLM).

Sentences of the abstract are sorted into roles by cue words. Claude later
replaces these with written summaries for the day's top items.
"""
from __future__ import annotations

import re

from .score import get_scorer

_SPLIT = re.compile(r"(?<=[.!?])\s+(?=[A-Z0-9(])")
WHY = re.compile(r"\b(however|challenge|challenging|remain[s]? (?:unclear|elusive|poorly|limited|difficult)|limited|lack|unclear|"
                 r"bottleneck|critical|crucial|essential|important|demand|despite|hinder|key to|yet|open question|"
                 r"is still|are still|not well understood|prohibitive|expensive)\b", re.I)
HOW = re.compile(r"\b(we (?:develop|propose|present|introduce|use|employ|combine|perform|construct|build|train|apply|"
                 r"leverage|implement|design|fabricate|measure|derive|formulate|couple|adopt|establish|conduct|benchmark)|"
                 r"using|based on|by means of|via|framework|approach|method|methodology|workflow|model(?:ed|ing)? with)\b", re.I)
WHAT = re.compile(r"\b(we (?:show|find|found|demonstrate|reveal|report|achieve|observe|identify|predict|obtain|uncover)|"
                  r"results? (?:show|indicate|reveal|demonstrate)|reveal|demonstrat|achiev|enabl|reduc|improv|"
                  r"increas|outperform|\d+(?:\.\d+)?\s?(?:%|times|fold|×))", re.I)


def _sentences(text: str) -> list[str]:
    return [s.strip() for s in _SPLIT.split(text or "") if len(s.strip()) > 25]


def _trim(s: str, n: int = 320) -> str:
    return s if len(s) <= n else s[: n - 1].rsplit(" ", 1)[0] + "…"


def summarize(item: dict) -> dict:
    sents = _sentences(item.get("abstract", ""))
    kind = item["kind"]
    if not sents:
        what = item["title"]
        why = how = ""
    elif kind in ("news", "tool", "repo", "conference", "cfp", "special-issue"):
        what = _trim(" ".join(sents[:2]), 360)
        why = _trim(next((s for s in sents[2:] if WHY.search(s)), ""))
        how = _trim(next((s for s in sents[2:] if HOW.search(s)), ""))
    else:
        used: set[int] = set()

        def pick(rx, prefer_last=False):
            idx = [i for i, s in enumerate(sents) if rx.search(s) and i not in used]
            if not idx:
                return ""
            i = idx[-1] if prefer_last else idx[0]
            used.add(i)
            return _trim(sents[i])

        why = pick(WHY) or (_trim(sents[0]) if len(sents) > 2 else "")
        if why:
            used.add(next((i for i, s in enumerate(sents) if _trim(s) == why), 0))
        how = pick(HOW)
        what = pick(WHAT, prefer_last=True) or _trim(sents[-1])
    return {"what": what, "why": why, "how": how, "impact": impact(item), "by": "rules"}


def impact(item: dict) -> str:
    text = f"{item['title']} {item.get('abstract', '')}"
    sc = get_scorer()
    projects = sc.projects_for(text)
    themes = {t["id"]: t["name"] for t in sc.themes}
    if projects:
        parts = [f"{name} (matched: {', '.join(keys[:4])})" for name, keys in projects]
        return "Possibly relevant to " + "; ".join(parts) + "."
    names = [themes[t] for t in item.get("themes", []) if t in themes]
    if names:
        return "Background reading for " + ", ".join(names[:2]) + "."
    return "General awareness."
