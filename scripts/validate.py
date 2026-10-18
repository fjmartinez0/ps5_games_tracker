"""Integrity rules. Runs on the Mac before every push and again in GitHub Actions before publishing.
Exit code 1 = the data must not go live."""
import re
import sys

from common import (CATEGORIES, DATE_RE, EVENTS, ID_RE, MIN_SCORE, PHYSICAL, PRICES, SALES, SCALES, SCOPE_YEARS,
                    STATUSES, WISHLIST, headline_score, load_games, load_json, norm_title, read_jsonl)

URL = re.compile(r"^https?://")


def main() -> int:
    errors, warnings = [], []
    games = load_games()
    ids, keys = set(), {}
    for g in games:
        gid, t = g.get("id"), g.get("title")
        where = f"{gid} {t}"
        if not ID_RE.match(gid or ""):
            errors.append(f"{where}: bad id")
        if gid in ids:
            errors.append(f"{where}: duplicate id")
        ids.add(gid)
        if not t:
            errors.append(f"{where}: missing title")
        if g.get("status") not in STATUSES:
            errors.append(f"{where}: status {g.get('status')!r}")
        if g.get("category") not in CATEGORIES:
            errors.append(f"{where}: category {g.get('category')!r}")
        if g.get("status") != "excluded":
            k = norm_title(t or "")
            if k in keys:
                errors.append(f"{where}: duplicate of {keys[k]}")
            keys[k] = gid
        rd = g.get("release_date")
        if rd and not DATE_RE.match(rd):
            errors.append(f"{where}: release_date {rd!r}")
        if g.get("ps5_year") not in SCOPE_YEARS and g.get("status") != "excluded":
            errors.append(f"{where}: ps5_year {g.get('ps5_year')} out of scope")
        if rd and g.get("status") == "listed" and int(rd[:4]) != g.get("ps5_year"):
            errors.append(f"{where}: ps5_year {g.get('ps5_year')} doesn't match release date {rd}")
        if g.get("status") in ("listed", "pending_score"):
            if g.get("category") != "game":
                errors.append(f"{where}: category {g.get('category')} can't be listed")
            if g.get("scale") not in SCALES:
                errors.append(f"{where}: scale {g.get('scale')!r}")
            if g.get("physical") not in PHYSICAL:
                errors.append(f"{where}: physical {g.get('physical')!r}")
        if g.get("status") == "listed":
            s = headline_score(g)
            if (s is None or s < MIN_SCORE) and not g.get("inclusion_reason"):
                errors.append(f"{where}: listed with score {s} and no by-request reason")
        if g.get("status") == "excluded" and not g.get("excluded_reason"):
            errors.append(f"{where}: excluded without a reason")
        for path in (("ps_store", "url"), ("metacritic", "url"), ("disc", "deku_url")):
            v = (g.get(path[0]) or {}).get(path[1])
            if v and not URL.match(v):
                errors.append(f"{where}: {'.'.join(path)} is not a URL")
    wl = load_json(WISHLIST, {}) or {}
    for gid in wl.get("game_ids", []):
        if gid not in ids:
            errors.append(f"wishlist: unknown id {gid}")
    for i, r in enumerate(read_jsonl(PRICES), 1):
        if r.get("game_id") not in ids or r.get("format") not in ("digital", "disc") or not isinstance(r.get("price"), (int, float)) \
                or not DATE_RE.match(str(r.get("date", ""))) or not (0 <= r["price"] <= 200):
            errors.append(f"prices.jsonl line {i}: invalid row {r}")
    for r in (load_json(SALES, {}) or {}).get("open", []):
        if r.get("game_id") not in ids:
            errors.append(f"sales: unknown id {r.get('game_id')}")
    for e in load_json(EVENTS, []) or []:
        if not e.get("name") or not DATE_RE.match(str(e.get("start", ""))):
            errors.append(f"events: invalid {e}")
    listed = sum(1 for g in games if g.get("status") == "listed")
    if listed < 50:
        errors.append(f"only {listed} listed games - refusing to publish a near-empty catalog")
    unverified = sum(1 for g in games if g.get("status") == "listed" and not g.get("verified"))
    if unverified:
        warnings.append(f"{unverified} listed games not yet verified by the checker")
    for w in warnings:
        print("warning:", w)
    for e in errors[:50]:
        print("ERROR:", e)
    print(f"validate: {len(games)} games, {listed} listed, {len(errors)} errors, {len(warnings)} warnings")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
