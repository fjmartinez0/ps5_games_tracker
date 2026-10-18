"""Build data/stats.json for the Statistics tab and the "Next Expected Price Drop" column.

Inputs: researched sale history (data/seed_observations.json), tracked price changes (data/prices.jsonl),
open/closed sales (data/sales.json), the sale calendar (data/events.json).
Digital discounts are measured against the PlayStation Store launch price; disc discounts against the
most common launch price across the five disc stores (msrp).
"""
import datetime as dt
import statistics

from common import (EVENTS, PRICES, SALES, SEED_OBS, STATS, load_games, load_json, norm_title, parse_date, read_jsonl,
                    save_json, today)

BUCKETS = [("0–3 Months", 0, 3), ("3–6 Months", 3, 6), ("6–12 Months", 6, 12), ("12+ Months", 12, 999)]
FORMATS = ("digital", "disc")


def months(a: str, b: str) -> float:
    return (parse_date(b) - parse_date(a)).days / 30.44


def med(xs):
    return round(statistics.median(xs), 1) if xs else None


def event_for(date: str, fmt: str, events: list[dict]):
    d = parse_date(date)
    for e in events:
        if e.get("expected") or fmt not in e.get("formats", ["digital"]):
            continue
        start = parse_date(e["start"])
        end = parse_date(e["end"]) if e.get("end") else start + dt.timedelta(days=14)
        if start <= d <= end:
            return e["id"]
    return None


def main():
    on = today()
    games = [g for g in load_games() if g["status"] == "listed"]
    by_key = {norm_title(g["title"]): g for g in games}
    by_id = {g["id"]: g for g in games}
    events = load_json(EVENTS, [])
    seed = load_json(SEED_OBS, {}) or {}
    sales = load_json(SALES, {"open": [], "closed": []})

    obs = {g["id"]: {"digital": [], "disc": []} for g in games}
    lowest = {g["id"]: {"digital": None, "disc": None} for g in games}
    launch = {g["id"]: {"digital": None, "disc": (g.get("disc") or {}).get("msrp")} for g in games}

    def add_low(gid, fmt, price):
        cur = lowest[gid][fmt]
        lowest[gid][fmt] = price if cur is None else min(cur, price)

    # researched history
    for o in seed.get("observations", []):
        g = by_key.get(norm_title(o["title"]))
        if not g or o["pct"] is None or not g.get("release_date"):
            continue
        obs[g["id"]][o["format"]].append({"date": o["date"], "pct": o["pct"], "event": o["event"], "store": o["store"],
                                          "price": o["price"], "us_pct": o.get("us_pct", False), "source": o["source"]})
        if o["price"] is not None:
            add_low(g["id"], o["format"], o["price"])
        if o.get("regular") and launch[g["id"]][o["format"]] is None:
            launch[g["id"]][o["format"]] = o["regular"]
    for r in seed.get("lowest_known", []):
        g = by_key.get(norm_title(r["title"]))
        if g:
            add_low(g["id"], r["format"], r["price"])

    # tracked prices (one row per change); launch digital = first regular price seen
    rows = sorted(read_jsonl(PRICES), key=lambda r: r["date"])
    for r in rows:
        if r["game_id"] not in by_id:
            continue
        gid, fmt = r["game_id"], r["format"]
        add_low(gid, fmt, r["price"])
        if fmt == "digital" and launch[gid]["digital"] is None:   # earliest PlayStation Store price = launch price
            launch[gid]["digital"] = r.get("regular") or r["price"]
    for r in rows:
        gid, fmt = r["game_id"], r["format"]
        g = by_id.get(gid)
        base = launch.get(gid, {}).get(fmt) or r.get("regular")
        if not g or not g.get("release_date") or not base or r["price"] >= base - 0.01:
            continue
        ev = event_for(r["date"], fmt, events)
        existing = [x for x in obs[gid][fmt] if x["event"] and x["event"] == ev]
        pct = round((1 - r["price"] / base) * 100)
        if existing:                                          # one observation per game per event: keep deepest
            if pct > existing[0]["pct"]:
                existing[0].update(pct=pct, price=r["price"], store=r["store"], date=r["date"])
            continue
        obs[gid][fmt].append({"date": r["date"], "pct": pct, "event": ev, "store": r["store"], "price": r["price"],
                              "us_pct": False, "source": r.get("source", "tracked")})

    # per game
    per_game, summary = {}, {}
    for g in games:
        gid, rel = g["id"], g.get("release_date")
        entry = {"buckets": {}, "first": {}, "lowest": lowest[gid], "launch": launch[gid]}
        for fmt in FORMATS:
            xs = obs[gid][fmt]
            for x in xs:
                x["age"] = round(months(rel, x["date"]), 1) if rel else None
            xs = [x for x in xs if x["age"] is not None and x["age"] >= 0]
            first = min(xs, key=lambda x: x["age"]) if xs else None
            entry["first"][fmt] = first and {k: first[k] for k in ("age", "pct", "event", "store", "us_pct")}
            entry["buckets"][fmt] = [max([x["pct"] for x in xs if lo <= x["age"] < hi], default=None) for _, lo, hi in BUCKETS]
            entry[f"obs_{fmt}"] = xs
        entry["next_expected"] = next_expected(g, entry, sales, events, obs, on)
        per_game[gid] = entry

    for fmt in FORMATS:
        firsts = [e["first"][fmt] for e in per_game.values() if e["first"][fmt]]
        all_obs = [(gid, x) for gid, e in per_game.items() for x in e[f"obs_{fmt}"]]
        deep = max(all_obs, key=lambda t: t[1]["pct"], default=None)
        summary[fmt] = {
            "games": len(firsts),
            "first_age_median": med([f["age"] for f in firsts]),
            "first_pct_median": med([f["pct"] for f in firsts]),
            "within_3_months": sum(1 for f in firsts if f["age"] < 3),
            "deepest": deep and {"game_id": deep[0], "title": by_id[deep[0]]["title"], "pct": deep[1]["pct"],
                                 "store": deep[1]["store"], "date": deep[1]["date"]},
            "buckets": [{"label": b[0], "median": med([e["buckets"][fmt][i] for e in per_game.values() if e["buckets"][fmt][i] is not None]),
                         "games": sum(1 for e in per_game.values() if e["buckets"][fmt][i] is not None)} for i, b in enumerate(BUCKETS)],
        }

    ev_rows = []
    for e in sorted(events, key=lambda e: e["start"]):
        row = {k: e.get(k) for k in ("id", "name", "start", "end", "special", "expected", "note", "source", "formats")}
        for fmt in FORMATS:
            pcts = [x["pct"] for en in per_game.values() for x in en[f"obs_{fmt}"] if x["event"] == e["id"]]
            row[fmt] = {"games": len(pcts), "median": med(pcts)}
        ev_rows.append(row)
    calendar = [{"month": m, "events": [], "special": False} for m in range(1, 13)]
    for e in events:
        if e.get("expected"):
            continue
        months_hit = {parse_date(e["start"]).month} | ({parse_date(e["end"]).month} if e.get("end") else set())
        for m in months_hit:
            calendar[m - 1]["events"].append(e["name"].rsplit(" 20", 1)[0] + ("" if m == parse_date(e["start"]).month else " (ends)"))
            calendar[m - 1]["special"] |= bool(e.get("special"))
    for c in calendar:
        c["events"] = sorted(set(c["events"]))

    for e in per_game.values():
        for fmt in FORMATS:
            e[f"obs_{fmt}"] = [{k: x[k] for k in ("date", "age", "pct", "event", "store", "us_pct")} for x in e[f"obs_{fmt}"]]
    save_json(STATS, {"generated_at": on, "buckets": [b[0] for b in BUCKETS], "summary": summary,
                      "events": ev_rows, "calendar": calendar, "games": per_game})
    print(f"stats: {summary['digital']['games']} games with digital sale data, {summary['disc']['games']} with disc")


def next_expected(g, entry, sales, events, obs, on):
    open_rows = [r for r in sales.get("open", []) if r["game_id"] == g["id"]]
    if open_rows:
        best = {}
        for r in open_rows:
            if r["format"] not in best or r["pct"] > best[r["format"]]["pct"]:
                best[r["format"]] = {"pct": r["pct"], "price": r["price"], "store": r["store"], "end": r.get("end")}
        return {"on_sale": best}
    upcoming = [e for e in sorted(events, key=lambda e: e["start"]) if e["start"] > on]
    if not upcoming:
        return None
    e = upcoming[0]
    base = e["name"].rsplit(" 20", 1)[0]
    prior = [p for p in events if not p.get("expected") and p["name"].rsplit(" 20", 1)[0] == base and p["start"] < e["start"]]
    prior = prior[-1] if prior else None
    est, basis = {}, {}
    for fmt in e.get("formats", ["digital"]):
        own = [x["pct"] for x in obs[g["id"]][fmt] if prior and x["event"] == prior["id"]]
        if own:
            est[fmt], basis[fmt] = max(own), "own"
        elif prior:
            typical = [x["pct"] for xs in obs.values() for x in xs[fmt] if x["event"] == prior["id"]]
            est[fmt], basis[fmt] = (round(statistics.median(typical)) if typical else None), "typical"
    return {"event": e["name"], "start": e["start"], "expected": bool(e.get("expected")), "pct": est, "basis": basis}


if __name__ == "__main__":
    main()
