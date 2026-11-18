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
    s = latex_to_unicode(_WS.sub(" ", s).strip())
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


# ------------------------------------------------------------------ LaTeX in titles → Unicode
_GREEK = {"alpha": "α", "beta": "β", "gamma": "γ", "delta": "δ", "epsilon": "ε", "varepsilon": "ε", "zeta": "ζ",
          "eta": "η", "theta": "θ", "kappa": "κ", "lambda": "λ", "mu": "μ", "nu": "ν", "xi": "ξ", "pi": "π",
          "rho": "ρ", "sigma": "σ", "tau": "τ", "phi": "φ", "varphi": "φ", "chi": "χ", "psi": "ψ", "omega": "ω",
          "Gamma": "Γ", "Delta": "Δ", "Theta": "Θ", "Lambda": "Λ", "Sigma": "Σ", "Phi": "Φ", "Psi": "Ψ", "Omega": "Ω",
          "times": "×", "pm": "±", "approx": "≈", "sim": "∼", "leq": "≤", "geq": "≥", "le": "≤", "ge": "≥",
          "to": "→", "rightarrow": "→", "infty": "∞", "cdot": "·", "circ": "°", "degree": "°", "AA": "Å", "hbar": "ħ",
          "partial": "∂", "nabla": "∇", "langle": "⟨", "rangle": "⟩", "%": "%"}
_SUB = str.maketrans("0123456789+-=()aehijklmnoprstuvxβγρφχ", "₀₁₂₃₄₅₆₇₈₉₊₋₌₍₎ₐₑₕᵢⱼₖₗₘₙₒₚᵣₛₜᵤᵥₓᵦᵧᵨᵩᵪ")
_SUP = str.maketrans("0123456789+-=()niδ", "⁰¹²³⁴⁵⁶⁷⁸⁹⁺⁻⁼⁽⁾ⁿⁱᵟ")


def _script(body: str, table: dict, mark: str) -> str:
    conv = body.translate(table)
    # characters without a Unicode sub/superscript form keep a plain marker
    return conv if all(c != o or c in " ," for c, o in zip(conv, body)) or conv != body else f"{mark}{body}"


def latex_to_unicode(s: str) -> str:
    if not s or ("$" not in s and "\\" not in s and "_{" not in s):
        return s

    def math(m: re.Match) -> str:
        t = m.group(1)
        t = re.sub(r"\\(?:mathrm|text|mathbf|mathit|rm|bf|mathcal|operatorname)\s*\{([^{}]*)\}", r"\1", t)
        t = re.sub(r"\\([A-Za-z]+|%)", lambda g: _GREEK.get(g.group(1), g.group(1)), t)
        t = re.sub(r"_\{([^{}]*)\}", lambda g: _script(g.group(1), _SUB, "_"), t)
        t = re.sub(r"_(\w)", lambda g: _script(g.group(1), _SUB, "_"), t)
        t = re.sub(r"\^\{([^{}]*)\}", lambda g: _script(g.group(1), _SUP, "^"), t)
        t = re.sub(r"\^(\w|[+\-])", lambda g: _script(g.group(1), _SUP, "^"), t)
        return t.replace("{", "").replace("}", "").replace("\\,", " ").replace("~", " ")

    s = re.sub(r"\$\$?([^$]+)\$\$?", math, s)
    s = re.sub(r"\\\((.+?)\\\)", math, s)
    s = re.sub(r"\\([A-Za-z]+)", lambda g: _GREEK.get(g.group(1), g.group(0)), s)
    s = re.sub(r"(?<=\d)~(?=[A-Za-z])", " ", s)
    return s.replace("\\%", "%").replace("\\&", "&").replace("\\_", "_")
