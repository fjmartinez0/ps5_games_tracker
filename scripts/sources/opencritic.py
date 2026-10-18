"""OpenCritic: fallback score when Metacritic has no PS5 score. Reads OpenCritic's public site data.

No paid API. The site loads scores with JavaScript from api.opencritic.com; we read that same data
slowly (one request per game, cached) and stop for the night if it refuses.
"""
from urllib.parse import quote

from common import FetchError, fetch_json

API = "https://api.opencritic.com/api"
HDRS = {"Origin": "https://opencritic.com", "Referer": "https://opencritic.com/"}


def search(title: str) -> list[dict]:
    """OpenCritic changed its search endpoint at least once; try the known forms in order."""
    last = None
    for path in (f"/meta/search?criteria={quote(title)}", f"/game/search?criteria={quote(title)}"):
        try:
            data = fetch_json(API + path, headers=HDRS, cache_hours=72)
        except FetchError as e:
            last = e
            if e.blocked:
                raise
            continue
        rows = [{"id": d.get("id"), "name": d.get("name"), "dist": d.get("dist")} for d in data
                if isinstance(d, dict) and d.get("relation", "game") == "game"]
        if rows:
            return rows
    if last:
        raise last
    return []


def read_score(game_id: int) -> dict:
    d = fetch_json(f"{API}/game/{game_id}", headers=HDRS, cache_hours=20)
    score = d.get("topCriticScore")
    score = round(score) if isinstance(score, (int, float)) and score > 0 else None
    return {"score": score, "reviews": d.get("numTopCriticReviews"), "url": f"https://opencritic.com/game/{game_id}/{d.get('url', '')}",
            "platforms": [p.get("shortName") for p in d.get("Platforms", []) if isinstance(p, dict)]}
