"""Shared helpers: paths, HTTP session, text cleanup, dates."""
from __future__ import annotations

import datetime as dt
import hashlib
import html
import json
import os
import re
import time
from pathlib import Path

import requests
import yaml

ROOT = Path(__file__).resolve().parent.parent
CONFIG = ROOT / "config"
DATA = ROOT / "data"
PUBLIC = ROOT / "public"

USER_AGENT = "research-radar/1.0 (+https://github.com/Benz666/research-radar)"

_session = requests.Session()
_session.headers["User-Agent"] = USER_AGENT


def http_get(url: str, params: dict | None = None, timeout: int = 40) -> requests.Response:
    if "api.openalex.org" in url and os.environ.get("OPENALEX_API_KEY"):
        params = {**(params or {}), "api_key": os.environ["OPENALEX_API_KEY"]}
    for attempt in range(4):
        r = _session.get(url, params=params, timeout=timeout)
        if r.status_code in (429, 503) and attempt < 3:
            wait = int(r.headers.get("Retry-After", "0") or 0) or 5 * (attempt + 1)
            if wait > 60:  # quota exhausted for a long time: give up, the source is reported as failed
                break
            time.sleep(wait)
            continue
        r.raise_for_status()
        return r
    r.raise_for_status()
    return r


def load_yaml(name: str) -> dict:
    return yaml.safe_load((CONFIG / name).read_text(encoding="utf-8"))


def read_json(path: Path, default):
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return default


def write_json(path: Path, obj) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=1, sort_keys=True) + "\n", encoding="utf-8")


_TAG = re.compile(r"<[^>]+>")
_WS = re.compile(r"\s+")


def clean_text(s: str | None, limit: int | None = None) -> str:
    if not s:
        return ""
    s = html.unescape(html.unescape(_TAG.sub(" ", s)))
    s = _WS.sub(" ", s).strip()
    if limit and len(s) > limit:
        s = s[: limit - 1].rsplit(" ", 1)[0] + "…"
    return s


def norm_title(t: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", t.lower())[:120]


def item_id(*parts: str) -> str:
    return hashlib.sha1("|".join(p or "" for p in parts).encode()).hexdigest()[:16]


def today() -> dt.date:
    return dt.datetime.now(dt.timezone.utc).date()


def iso(d: dt.date | dt.datetime | None) -> str:
    return d.isoformat()[:10] if d else ""
