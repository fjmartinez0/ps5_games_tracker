"""Fill missing links without the AI: guess each game's Deku Deals PS5 item from its title, confirm the
page really is that game on PS5, then take the PlayStation Store Canada link from it.
Whatever this can't find is left for the agent (scripts/discover.py lists it).

  python3 scripts/enrich.py [--limit 60]
"""
import argparse
import re

from common import CHECKS, FetchError, append_jsonl, load_games, log_check, metacritic_slug, norm_title, save_games
from sources import deku


def slug_candidates(title):
    full = metacritic_slug(title)
    base = metacritic_slug(re.split(r"\s[-–:]\s|:\s", title)[0])
    return list(dict.fromkeys([full, base]))


def same_game(title, page_title):
    if not page_title:
        return False
    want = set(norm_title(title).split()[:3])
    have = set(norm_title(page_title).split())
    return len(want & have) >= max(1, min(2, len(want)))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=60)
    args = ap.parse_args()
    games = load_games()
    todo = [g for g in games if g["status"] in ("listed", "pending_score")
            and (not (g.get("disc") or {}).get("deku_url") or not (g.get("ps_store") or {}).get("url"))
            and not g.get("enrich_tried")]
    todo.sort(key=lambda g: g.get("release_date") or "0", reverse=True)
    checks, filled = [], 0
    for g in todo[: args.limit]:
        g["enrich_tried"] = True                       # one automatic attempt; the agent handles misses
        for slug in slug_candidates(g["title"]):
            url = deku.item_url(slug)
            try:
                d = deku.read(url)
            except FetchError as e:
                checks.append(log_check("deku-enrich", g["id"], url, False, {"error": str(e)}))
                continue
            ok = d["is_ps5"] and same_game(g["title"], d.get("page_title"))
            checks.append(log_check("deku-enrich", g["id"], url, ok, {"ps_store": bool(d.get("ps_store_url"))}))
            if not ok:
                continue
            g.setdefault("disc", {"deku_url": None, "msrp": None, "stores": {}})
            if not g["disc"].get("deku_url"):
                g["disc"]["deku_url"] = url
            if d.get("ps_store_url") and not (g.get("ps_store") or {}).get("url"):
                g.setdefault("ps_store", {})["url"] = d["ps_store_url"]
            if any(o["format"] == "disc" for o in d["offers"]):
                g["physical"] = "Yes"
            filled += 1
            break
    append_jsonl(CHECKS, checks)
    save_games(games)
    print(f"enrich: tried {min(len(todo), args.limit)} games, filled {filled}, {max(0, len(todo) - args.limit)} left for later nights")


if __name__ == "__main__":
    main()
