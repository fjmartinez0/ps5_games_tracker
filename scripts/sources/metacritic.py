"""Metacritic: PS5 Metascore per game, and the year browse lists used for discovery.

Metacritic pages embed their data as a Nuxt payload (<script id="__NUXT_DATA__">): one flat JSON list
where objects refer to other entries by position. We decode just what we need. Each game page lists a
criticScoreSummary per platform; we always take the "PlayStation 5" one (a game's default score can
be another platform's: Skate Story is 85 on PC and 80 on PS5).
"""
import json
import re

from common import fetch, metacritic_slug
from sources.textutil import text_lines

BROWSE = "https://www.metacritic.com/browse/game/ps5/all/all-time/{sort}/?releaseYearMin={y}&releaseYearMax={y}&page={p}"
MONTHS = {m: i for i, m in enumerate(["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"], 1)}
WRAPPERS = ("Reactive", "ShallowReactive", "Ref", "ShallowRef", "EmptyRef", "EmptyShallowRef")


def game_url(title_or_slug: str) -> str:
    slug = title_or_slug if re.fullmatch(r"[a-z0-9-]+", title_or_slug) else metacritic_slug(title_or_slug)
    return f"https://www.metacritic.com/game/{slug}/critic-reviews/?platform=playstation-5"


# ---------------------------------------------------------------- Nuxt payload
def nuxt_payload(html: str):
    m = re.search(r'<script[^>]*id="__NUXT_DATA__"[^>]*>(.*?)</script>', html, re.S)
    if not m:
        return None
    try:
        data = json.loads(m.group(1))
    except json.JSONDecodeError:
        return None
    return data if isinstance(data, list) else None


def _v(a, i):
    """Value at position i, unwrapping Nuxt's reactive wrappers."""
    if not isinstance(i, int) or isinstance(i, bool) or not 0 <= i < len(a):
        return None
    v = a[i]
    if isinstance(v, list) and len(v) == 2 and v[0] in WRAPPERS:
        return _v(a, v[1])
    return v


def _score(a, ref):
    css = _v(a, ref)
    if not isinstance(css, dict):
        return None, None
    s, n = _v(a, css.get("score")), _v(a, css.get("reviewCount"))
    return (int(s) if isinstance(s, (int, float)) and not isinstance(s, bool) else None,
            int(n) if isinstance(n, (int, float)) and not isinstance(n, bool) else None)


def read_score(url: str) -> dict:
    """Return {score, reviews, release_date} for the PS5 version; score None if Metacritic has none yet."""
    page = fetch(url)
    out = {"url": url, "score": None, "reviews": None, "release_date": None, "strategy": None}
    a = nuxt_payload(page)
    if a:
        for d in a:
            if not isinstance(d, dict) or "criticScoreSummary" not in d:
                continue
            if "name" in d and _v(a, d["name"]) == "PlayStation 5":           # per-platform entry
                out["score"], out["reviews"] = _score(a, d["criticScoreSummary"])
                out["strategy"] = "nuxt"
                rd = _v(a, d.get("releaseDate"))
                if isinstance(rd, str) and re.match(r"\d{4}-\d{2}-\d{2}", rd):
                    out["release_date"] = rd[:10]
            elif _v(a, d.get("type")) == "game-title" and out["release_date"] is None:
                rd = _v(a, d.get("releaseDate"))
                if isinstance(rd, str) and re.match(r"\d{4}-\d{2}-\d{2}", rd):
                    out["release_date"] = rd[:10]
        if out["strategy"]:
            return out
    # Fallback: the visible score card ("Metascore 80 out of 100"), only when the page is PS5-only
    m = re.search(r'data-testid="score-card-overview".*?title="Metascore (\d+) out of 100"', page, re.S)
    if m and "PlayStation 5" in page and not re.search(r"\b(PC|Xbox Series X|Nintendo Switch)\b", page[:200000]):
        out.update(score=int(m.group(1)), strategy="score-card")
    return out


def browse(year: int, page: int = 1, sort: str = "metascore") -> list[dict]:
    """One page of the PS5 browse list: [{title, slug, release_date, score}] (score None if 'tbd')."""
    html = fetch(BROWSE.format(sort=sort, y=year, p=page), cache_hours=6)
    items = []
    a = nuxt_payload(html)
    if a:
        for d in a:
            if isinstance(d, dict) and _v(a, d.get("type")) == "game-title" and "slug" in d and "title" in d:
                score, _ = _score(a, d.get("criticScoreSummary"))
                rd = _v(a, d.get("releaseDate"))
                items.append({"title": _v(a, d["title"]), "slug": _v(a, d["slug"]),
                              "release_date": rd[:10] if isinstance(rd, str) else None, "score": score})
    if not items:                                                           # fallback: page text
        lines = text_lines(html)
        date_re = re.compile(r"^(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]* (\d{1,2}), (\d{4})$")
        for i, ln in enumerate(lines):
            dm = date_re.match(ln)
            if not dm:
                continue
            title = next((re.sub(r"^\d+\.\s*", "", lines[j]) for j in range(i - 1, max(-1, i - 4), -1)
                          if not date_re.match(lines[j]) and not re.fullmatch(r"(Metascore|tbd|\d{1,3}\.?|[A-Z]+)", lines[j])), None)
            score = next((int(lines[j]) for j in range(i + 1, min(len(lines), i + 6)) if re.fullmatch(r"\d{1,3}", lines[j])), None)
            if title:
                items.append({"title": title, "slug": metacritic_slug(title), "score": score,
                              "release_date": f"{dm.group(3)}-{MONTHS[dm.group(1)[:3]]:02d}-{int(dm.group(2)):02d}"})
    seen, out = set(), []
    for it in items:
        if it["slug"] and it["slug"] not in seen:
            seen.add(it["slug"])
            out.append(it)
    return out
