"""Nightly prices: digital (PlayStation Store Canada) and disc (Best Buy, VGP, PNP via Deku Deals;
EB Games and Walmart from their own pages). Records only changes to data/prices.jsonl and keeps
data/sales.json up to date for the dashboard and alerts.

Cadence: digital every night for every tracked game; disc every night for wishlist games and for a
rotating third of the rest (each game's disc prices are checked at least every 3 days).
"""
import argparse
import zlib

from common import (CHECKS, DISC_STORES, DIGITAL_STORE, PRICES, SALES, SEED_OBS, WISHLIST, FetchError, append_jsonl,
                    load_games, load_json, log_check, read_jsonl, save_games, save_json, today)
from rules import close_expired, disc_msrp, prune_closed, set_release_date, update_sale
from sources import deku, ps_store, retail


def lowest_index():
    """{(game_id or title, format): lowest price ever seen} from tracked prices + researched history."""
    low = {}
    for r in read_jsonl(PRICES):
        k = (r["game_id"], r["format"])
        low[k] = min(low.get(k, 1e9), r["price"])
    for r in (load_json(SEED_OBS, {}) or {}).get("lowest_known", []):
        k = (r["title"], r["format"])
        low[k] = min(low.get(k, 1e9), r["price"])
    return low


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--all-disc", action="store_true", help="check disc prices for every game tonight")
    ap.add_argument("--only", help="comma-separated game IDs")
    args = ap.parse_args()
    on, games = today(), load_games()
    wish = set((load_json(WISHLIST, {}) or {}).get("game_ids", []))
    sales = load_json(SALES, {"open": [], "closed": []})
    low = lowest_index()
    obs, checks, notes = [], [], []
    day_slot = int(on.replace("-", "")) % 3

    def lowest_before(g, fmt):
        vals = [low.get((g["id"], fmt)), low.get((g["title"], fmt))]
        vals = [v for v in vals if v is not None and v < 1e9]
        return min(vals) if vals else None

    def record(g, fmt, store, regular, price, extra=None):
        last = g.setdefault("_last", {}).get(f"{fmt}|{store}")
        if last is None or abs(last - price) > 0.009:
            obs.append({"date": on, "game_id": g["id"], "format": fmt, "store": store, "regular": regular, "price": price, **(extra or {})})
        low[(g["id"], fmt)] = min(low.get((g["id"], fmt), 1e9), price)

    # last known prices per (game, format, store) so we only append changes
    last = {}
    for r in sorted(read_jsonl(PRICES), key=lambda r: r["date"]):      # latest by date, not file order
        last[(r["game_id"], f"{r['format']}|{r['store']}")] = r["price"]
    tracked = [g for g in games if g["status"] in ("listed", "pending_score")]
    if args.only:
        ids = set(args.only.split(","))
        tracked = [g for g in tracked if g["id"] in ids]
    for g in tracked:
        g["_last"] = {k: v for (gid, k), v in last.items() if gid == g["id"]}

    for g in tracked:
        # ---------------- digital
        url = (g.get("ps_store") or {}).get("url")
        if url:
            try:
                r = ps_store.read(url)
                checks.append(log_check("ps_store", g["id"], url, r["regular"] is not None, {"strategy": r["strategy"]}))
                if r["regular"] is not None:
                    lb = lowest_before(g, "digital")
                    # baseline = regular price; after a permanent price cut, the old regular for that one night
                    prev_regular = g["ps_store"].get("regular") if g["ps_store"].get("checked_at") else None
                    baseline = prev_regular if prev_regular and r["regular"] < prev_regular - 0.01 else r["regular"]
                    g["ps_store"].update(regular=r["regular"], current=r["current"], checked_at=on, sale_end=r["sale_end"])
                    c = set_release_date(g, r["release_date"])
                    if c:
                        notes.append(f"{g['title']}: {c}")
                    if not ps_store.is_standard_edition(r.get("edition")):
                        notes.append(f"{g['title']}: PS Store link is a '{r['edition']}', not the standard edition")
                    record(g, "digital", DIGITAL_STORE, r["regular"], r["current"], {"sale_end": r["sale_end"]})
                    update_sale(sales, g["id"], "digital", DIGITAL_STORE, r["current"], baseline, lb, on, r["sale_end"], r["regular"])
            except FetchError as e:
                checks.append(log_check("ps_store", g["id"], url, False, {"error": str(e)}))

        # ---------------- disc
        if not (args.all_disc or g["id"] in wish or zlib.crc32(g["id"].encode()) % 3 == day_slot):
            continue
        disc = g.setdefault("disc", {"deku_url": None, "msrp": None, "stores": {}})
        seen = []
        if disc.get("deku_url"):
            try:
                d = deku.read(disc["deku_url"])
                checks.append(log_check("deku", g["id"], disc["deku_url"], d["is_ps5"], {"offers": len(d["offers"])}))
                if not d["is_ps5"]:
                    notes.append(f"{g['title']}: Deku Deals link shows no PS5 prices (wrong platform item?)")
                if d.get("ps_store_url") and not (g.get("ps_store") or {}).get("url"):
                    g.setdefault("ps_store", {})["url"] = d["ps_store_url"]
                hist = {k: v for k, v in d["history"].items() if k[1] in DISC_STORES or k[1] == DIGITAL_STORE}
                if hist and not disc.get("history_imported"):          # one-time back-fill of the full daily history
                    rows = [(dt_, f, st, pr) for dt_, f, st, pr in deku.history_changes(hist) if dt_ < on]
                    obs.extend({"date": dt_, "game_id": g["id"], "format": f, "store": st, "price": pr,
                                "regular": None, "source": "deku-history"} for dt_, f, st, pr in rows)
                    for dt_, f, st, pr in rows:
                        g["_last"][f"{f}|{st}"] = pr
                        low[(g["id"], f)] = min(low.get((g["id"], f), 1e9), pr)
                    disc["history_imported"] = on
                firsts = [sorted(v)[0][1] for (f, st), v in hist.items() if f == "disc"]
                if firsts and disc.get("msrp_source") != "history":     # launch price = first price each store showed
                    disc["msrp"], disc["msrp_source"] = disc_msrp(firsts), "history"
                for o in d["offers"]:
                    if o["format"] == "disc" and o["store"] in DISC_STORES:
                        seen.append((o["store"], o["price"], disc.get("msrp") or o["price"], None))
                for fmt in ("digital", "disc"):
                    if d["lowest"][fmt] is not None:
                        low[(g["id"], fmt)] = min(low.get((g["id"], fmt), 1e9), d["lowest"][fmt])
            except FetchError as e:
                checks.append(log_check("deku", g["id"], disc["deku_url"], False, {"error": str(e)}))
        for store in ("EB Games", "Walmart"):
            surl = (disc.get("stores", {}).get(store) or {}).get("url")
            if not surl or retail.store_blocked(store):
                continue
            try:
                r = retail.read(store, surl)
                checks.append(log_check(store, g["id"], surl, r["price"] is not None, {"strategy": r["strategy"]}))
                if r["price"] is not None:
                    seen.append((store, r["price"], r["regular"] or r["price"], None))
            except FetchError as e:
                checks.append(log_check(store, g["id"], surl, False, {"error": str(e), "blocked": e.blocked}))
                if e.blocked:
                    notes.append(f"{store} is blocking requests; using weekly flyers instead for 7 days")
        if seen:
            g["physical"] = "Yes"
            if not disc.get("msrp"):
                disc["msrp"] = disc_msrp([reg for _, _, reg, _ in seen])
            lb = lowest_before(g, "disc")
            for store, price, reg, _ in seen:
                disc.setdefault("stores", {}).setdefault(store, {})
                disc["stores"][store].update(price=price, checked_at=on)
                record(g, "disc", store, reg, price)
                update_sale(sales, g["id"], "disc", store, price, disc["msrp"] or reg, lb, on)

    for g in tracked:
        g.pop("_last", None)
    close_expired(sales, on)
    prune_closed(sales, on)
    append_jsonl(PRICES, obs)
    append_jsonl(CHECKS, checks)
    save_json(SALES, sales)
    save_games(games)
    ok = sum(1 for c in checks if c["ok"])
    print(f"prices: {len(tracked)} games, {ok}/{len(checks)} checks ok, {len(obs)} price changes, {len(sales['open'])} open sales")
    for n in sorted(set(notes)):
        print("  !", n)


if __name__ == "__main__":
    main()
