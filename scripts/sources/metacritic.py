"""Metacritic: PS5 Metascore per game, and the year browse lists used for discovery.

Important: a game's default page can show another platform's score (Skate Story: PC 85, PS5 80),
so always read the PS5 critic-reviews page.
"""
import re

from common import fetch, metacritic_slug
from sources.textutil import all_json_blobs, text_lines, walk

BROWSE = "https://www.metacritic.com/browse/game/ps5/all/all-time/{sort}/?releaseYearMin={y}&releaseYearMax={y}&page={p}"
MONTHS = {m: i for i, m in enumerate(["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"], 1)}
DATE_RE = re.compile(r"^(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]* (\d{1,2}), (\d{4})$")


def game_url(title_or_slug: str) -> str:
    slug = title_or_slug if re.fullmatch(r"[a-z0-9-]+", title_or_slug) else metacritic_slug(title_or_slug)
    return f"https://www.metacritic.com/game/{slug}/critic-reviews/?platform=playstation-5"


def read_score(url: str) -> dict:
    """Return {score, reviews, release_date} for the PS5 version; score None if Metacritic has none yet."""
    page = fetch(url)
    out = {"url": url, "score": None, "reviews": None, "release_date": None, "strategy": None}
    # Strategy 1: embedded JSON with a PS5 critic score summary
    for blob in all_json_blobs(page):
        for d in walk(blob):
            if "criticScoreSummary" in d and isinstance(d["criticScoreSummary"], dict):
                s = d["criticScoreSummary"]
                if s.get("score") is not None and "playstation-5" in str(s.get("url", "")) + url:
                    out.update(score=int(s["score"]), reviews=s.get("reviewCount"), strategy="json")
            if out["release_date"] is None and isinstance(d.get("releaseDate"), str) and re.match(r"\d{4}-\d{2}-\d{2}", d["releaseDate"]):
                out["release_date"] = d["releaseDate"][:10]
    if out["score"] is not None:
        return out
    # Strategy 2: page text - "Based on 29 Critic Reviews" next to the score
    lines = text_lines(page)
    for i, ln in enumerate(lines):
        m = re.search(r"Based on (\d+) Critic Reviews?", ln)
        if m:
            near = " ".join(lines[max(0, i - 4): i + 4])
            nums = [int(x) for x in re.findall(r"\b(\d{2,3})\b", near) if 0 < int(x) <= 100 and int(x) != int(m.group(1))]
            if nums:
                out.update(score=nums[0], reviews=int(m.group(1)), strategy="text")
                break
    return out


def browse(year: int, page: int = 1, sort: str = "metascore") -> list[dict]:
    """One page of the PS5 browse list: [{title, release_date, score, slug}] (score None if 'tbd')."""
    html = fetch(BROWSE.format(sort=sort, y=year, p=page), cache_hours=6)
    items = []
    # Strategy 1: product cards in embedded JSON
    for blob in all_json_blobs(html):
        for d in walk(blob):
            if d.get("type") == "game-title" and d.get("title") and d.get("slug"):
                score = (d.get("criticScoreSummary") or {}).get("score")
                items.append({"title": d["title"], "slug": d["slug"], "release_date": (d.get("releaseDate") or "")[:10] or None,
                              "score": int(score) if score is not None else None})
    if items:
        return _dedupe(items)
    # Strategy 2: card links + page text ("Title", "Dec 4, 2025", "Metascore", "84")
    slugs = dict()
    for m in re.finditer(r'href="/game/([a-z0-9-]+)/"[^>]*>(.*?)</a>', html, re.S):
        txt = re.sub(r"<[^>]+>", " ", m.group(2))
        txt = re.sub(r"^\s*\d+\.\s*", "", re.sub(r"\s+", " ", txt)).strip()
        if txt:
            slugs.setdefault(txt, m.group(1))
    lines = text_lines(html)
    for i, ln in enumerate(lines):
        dm = DATE_RE.match(ln)
        if not dm:
            continue
        title = next((re.sub(r"^\d+\.\s*", "", lines[j]) for j in range(i - 1, max(-1, i - 4), -1)
                      if not DATE_RE.match(lines[j]) and not re.fullmatch(r"(Metascore|tbd|\d{1,3}|[A-Z]+)", lines[j])), None)
        score = None
        for j in range(i + 1, min(len(lines), i + 6)):
            if re.fullmatch(r"\d{1,3}", lines[j]):
                score = int(lines[j])
                break
            if lines[j].lower() == "tbd":
                break
        if title:
            date = f"{dm.group(3)}-{MONTHS[dm.group(1)[:3]]:02d}-{int(dm.group(2)):02d}"
            items.append({"title": title, "slug": slugs.get(title) or metacritic_slug(title), "release_date": date, "score": score})
    return _dedupe(items)


def _dedupe(items):
    seen, out = set(), []
    for it in items:
        if it["slug"] in seen:
            continue
        seen.add(it["slug"])
        out.append(it)
    return out
