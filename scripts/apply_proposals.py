"""Merger: accept or reject each item of the agent's proposal against the rules. The agent's output is
untrusted input - every rule that matters is enforced here, not in the prompt.

New games never enter the catalog directly: they start as `pending_score` (or `excluded`) and the
checker promotes them only after reading a 70+ score from Metacritic/OpenCritic itself.
"""
import argparse
import re
import sys

from prices import lowest_index
from rules import update_sale

from common import (CATEGORIES, EVENTS, EXCLUDED_CATEGORIES, PRICES, PROPOSALS, SALES, SCALES, SCOPE_YEARS, append_jsonl,
                    load_games, load_json, metacritic_slug, next_id, norm_title, save_games, save_json, today)

URL_RULES = {
    "ps_store_url": r"^https://store\.playstation\.com/en-ca/(product|concept)/[A-Za-z0-9_\-]+",
    "metacritic_url": r"^https://www\.metacritic\.com/game/[a-z0-9-]+/",
    "deku_url": r"^https://www\.dekudeals\.com/items/[a-z0-9-]+",
    "eb_url": r"^https://www\.ebgames\.ca/",
    "walmart_url": r"^https://www\.walmart\.ca/en/ip/",
}
DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def clean_url(field, v):
    if not v:
        return None
    if field == "deku_url" and "country=ca" not in v:
        v = v.split("?")[0] + "?format=all&country=ca"
    return v if re.match(URL_RULES[field], v) else False


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", default=today())
    args = ap.parse_args()
    path = PROPOSALS / f"{args.date}.json"
    prop = load_json(path)
    if prop is None:
        print(f"apply: no proposal at {path}")
        sys.exit(3)
    games = load_games()
    by_id = {g["id"]: g for g in games}
    by_key = {norm_title(g["title"]): g for g in games}
    accepted, rejected = [], []

    def reject(item, why):
        rejected.append(f"{item.get('title') or item.get('id') or item.get('name')}: {why}")

    for it in prop.get("new_games", []):
        title = (it.get("title") or "").strip()
        if not title:
            reject(it, "no title")
            continue
        if norm_title(title) in by_key:
            g = by_key[norm_title(title)]
            it = {**it, "id": g["id"]}
            prop.setdefault("updates", []).append(it)            # treat as an update of the tracked game
            continue
        cat = it.get("category")
        if cat not in CATEGORIES - {"review"}:
            reject(it, f"category '{cat}' not allowed")
            continue
        rd = it.get("release_date")
        if rd and (not DATE.match(rd) or int(rd[:4]) not in SCOPE_YEARS):
            reject(it, f"release date {rd} outside 2025-2026")
            continue
        if rd and rd > today():
            reject(it, f"not released yet ({rd})")
            continue
        if not it.get("evidence"):
            reject(it, "no evidence URLs")
            continue
        links = {f: clean_url(f, it.get(f)) for f in URL_RULES}
        bad = [f for f, v in links.items() if v is False]
        if bad:
            reject(it, f"malformed link(s): {', '.join(bad)}")
            continue
        scale = it.get("scale") if it.get("scale") in SCALES else None
        if cat == "game" and not scale:
            reject(it, f"scale '{it.get('scale')}' not in AAA/AA/Indie")
            continue
        g = {
            "id": next_id(games), "title": title,
            "status": "pending_score" if cat == "game" else "excluded", "category": cat,
            "excluded_reason": EXCLUDED_CATEGORIES.get(cat), "review_note": None, "inclusion_reason": None,
            "release_date": rd, "ps5_year": int(rd[:4]) if rd else int(today()[:4]),
            "scale": scale, "genre": (it.get("genre") or "")[:40] or None,
            "metacritic": {"score": None, "url": links["metacritic_url"] or
                           f"https://www.metacritic.com/game/{metacritic_slug(title)}/critic-reviews/?platform=playstation-5",
                           "checked_at": None, "verified": False},
            "alt_score": None, "score_locked": False, "score_locked_at": None, "physical": "Unverified",
            "ps_store": {"url": links["ps_store_url"], "regular": None, "current": None, "checked_at": None},
            "disc": {"deku_url": links["deku_url"], "msrp": None, "stores": {
                **({"EB Games": {"url": links["eb_url"]}} if links["eb_url"] else {}),
                **({"Walmart": {"url": links["walmart_url"]}} if links["walmart_url"] else {})}},
            "first_seen": today(), "listed_on": None, "source": "agent", "verified": False,
            "evidence": it["evidence"][:5],
        }
        games.append(g)
        by_key[norm_title(title)] = g
        by_id[g["id"]] = g
        accepted.append(f"new {g['status']}: {title} ({cat})")

    for it in prop.get("updates", []):
        g = by_id.get(it.get("id"))
        if not g:
            reject(it, "unknown id")
            continue
        if not it.get("evidence"):
            reject(it, "no evidence URLs")
            continue
        changed = []
        for f in ("ps_store_url", "deku_url", "eb_url", "walmart_url", "metacritic_url"):
            v = clean_url(f, it.get(f))
            if v is False:
                reject(it, f"malformed {f}")
            elif v:
                if f == "ps_store_url" and not (g.get("ps_store") or {}).get("url"):
                    g.setdefault("ps_store", {})["url"] = v; changed.append(f)
                elif f == "deku_url" and not g.get("disc", {}).get("deku_url"):
                    g.setdefault("disc", {"stores": {}})["deku_url"] = v; changed.append(f)
                elif f in ("eb_url", "walmart_url"):
                    store = "EB Games" if f == "eb_url" else "Walmart"
                    st = g.setdefault("disc", {"stores": {}}).setdefault("stores", {}).setdefault(store, {})
                    if not st.get("url"):
                        st["url"] = v; changed.append(f)
                elif f == "metacritic_url" and not (g.get("metacritic") or {}).get("verified"):
                    g.setdefault("metacritic", {})["url"] = v; changed.append(f)
        rd = it.get("release_date")
        if rd and DATE.match(rd) and not g.get("release_date"):
            g["release_date"] = rd; changed.append("release_date")
        if changed:
            accepted.append(f"update {g['id']} {g['title']}: {', '.join(changed)}")

    flyer_rows = []
    for it in prop.get("flyer_prices", []):
        g = by_id.get(it.get("id"))
        price, reg = it.get("price"), it.get("regular")
        if not g or it.get("store") not in ("Walmart", "EB Games") or not isinstance(price, (int, float)) \
                or not it.get("evidence") or not DATE.match(str(it.get("valid_from", ""))):
            reject(it, "flyer price incomplete (id, store, price, valid_from, evidence)")
            continue
        if not (5 <= price <= 150) or (isinstance(reg, (int, float)) and price > reg):
            reject(it, f"implausible price {price}")
            continue
        flyer_rows.append({"date": it["valid_from"], "game_id": g["id"], "format": "disc", "store": it["store"],
                           "regular": reg, "price": round(float(price), 2), "source": "flyer",
                           "valid_to": it.get("valid_to"), "evidence": it["evidence"][:2]})
        accepted.append(f"flyer {it['store']} {g['title']}: ${price}")
    append_jsonl(PRICES, flyer_rows)
    if flyer_rows:                                               # flyer deals open sales like live prices do
        sales, low = load_json(SALES, {"open": [], "closed": []}), lowest_index()
        for r in flyer_rows:
            if (r.get("valid_to") or r["date"]) < today():
                continue
            g = by_id[r["game_id"]]
            base = (g.get("disc") or {}).get("msrp") or r["regular"] or r["price"]
            update_sale(sales, g["id"], "disc", r["store"], r["price"], base, low.get((g["id"], "disc")), today(), r.get("valid_to"))
        save_json(SALES, sales)

    events = load_json(EVENTS, [])
    for it in prop.get("events", []):
        if not it.get("name") or not DATE.match(str(it.get("start", ""))) or not it.get("evidence"):
            reject(it, "event needs name, start date and evidence")
            continue
        eid = re.sub(r"[^A-Z0-9]", "", it["name"].upper())[:12]
        row = {"id": eid, "name": it["name"], "start": it["start"], "end": it.get("end"), "special": bool(it.get("special")),
               "formats": [f for f in it.get("formats", ["digital"]) if f in ("digital", "disc")] or ["digital"],
               "source": it["evidence"][0], "expected": False}
        same = [e for e in events if e["name"] == row["name"] or (e.get("expected") and e["name"].split(" 20")[0] == row["name"].split(" 20")[0]
                                                                   and e["start"][:4] == row["start"][:4])]
        for e in same:
            events.remove(e)
        events.append(row)
        accepted.append(f"event {row['name']} {row['start']}")
    save_json(EVENTS, sorted(events, key=lambda e: e["start"]))
    save_games(games)

    print(f"apply: {len(accepted)} accepted, {len(rejected)} rejected")
    for a in accepted:
        print("  +", a)
    for r in rejected:
        print("  -", r)


if __name__ == "__main__":
    main()
