"""Add or remove wishlist games.

  python3 scripts/wishlist.py add "Clair Obscur"     # by title (partial match) or by ID (PS5-0001)
  python3 scripts/wishlist.py remove PS5-0001
  python3 scripts/wishlist.py list
  python3 scripts/wishlist.py --issue-title "wishlist: add PS5-0001"   # used by the GitHub workflow
"""
import argparse
import re
import sys

from common import WISHLIST, iso_now, load_games, load_json, save_json


def find(games, q):
    if re.fullmatch(r"PS5-\d{4}", q):
        return [g for g in games if g["id"] == q]
    ql = q.lower()
    exact = [g for g in games if g["title"].lower() == ql]
    return exact or [g for g in games if ql in g["title"].lower() and g["status"] in ("listed", "pending_score")]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("action", nargs="?", choices=["add", "remove", "list"])
    ap.add_argument("query", nargs="?")
    ap.add_argument("--issue-title")
    a = ap.parse_args()
    if a.issue_title:
        m = re.match(r"^\s*wishlist:\s*(add|remove)\s+(PS5-\d{4})\s*$", a.issue_title, re.I)
        if not m:
            print(f"not a wishlist request: {a.issue_title!r}")
            return 2
        a.action, a.query = m.group(1).lower(), m.group(2)
    games = load_games()
    wl = load_json(WISHLIST, {"game_ids": []})
    ids = list(wl.get("game_ids", []))
    if a.action == "list" or not a.action:
        for g in games:
            if g["id"] in ids:
                print(g["id"], g["title"])
        return 0
    hits = find(games, a.query or "")
    if len(hits) != 1:
        print(f"{len(hits)} matches for {a.query!r}: " + "; ".join(f"{g['id']} {g['title']}" for g in hits[:8]))
        return 1
    g = hits[0]
    if g["status"] not in ("listed", "pending_score"):
        print(f"{g['title']} isn't tracked (status {g['status']}); only tracked games can be wishlisted")
        return 1
    if a.action == "add" and g["id"] not in ids:
        ids.append(g["id"])
    elif a.action == "remove" and g["id"] in ids:
        ids.remove(g["id"])
    save_json(WISHLIST, {"game_ids": sorted(ids), "updated_at": iso_now()})
    print(f"{a.action}: {g['id']} {g['title']} ({len(ids)} on wishlist)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
