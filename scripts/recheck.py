"""Checker: confirm scores against Metacritic (OpenCritic as fallback) and move games through their
lifecycle. Deterministic; logs every external check to data/checks.jsonl.

  python3 scripts/recheck.py               # nightly: waiting games, unlocked scores, verification backlog
  python3 scripts/recheck.py --new-only    # only games added by today's proposals
"""
import argparse
import sys

from common import (CHECKS, FetchError, append_jsonl, load_games, log_check, save_games, today)
from rules import lifecycle, score_update, set_release_date
from sources import metacritic, opencritic

BACKLOG_PER_NIGHT = 40


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--new-only", action="store_true")
    ap.add_argument("--backlog", type=int, default=BACKLOG_PER_NIGHT)
    args = ap.parse_args()
    on, games, checks, changes = today(), load_games(), [], []
    oc_ok = True

    def check(g):
        nonlocal oc_ok
        was_verified = bool(g.get("verified"))
        url = (g.get("metacritic") or {}).get("url") or metacritic.game_url(g["title"])
        try:
            r = metacritic.read_score(url)
            checks.append(log_check("metacritic", g["id"], url, True, {"score": r["score"], "strategy": r["strategy"]}))
        except FetchError as e:
            checks.append(log_check("metacritic", g["id"], url, False, {"error": str(e)}))
            return
        for c in score_update(g, r["score"], r["reviews"], url, on):
            changes.append(f"{g['title']}: {c}")
        c = set_release_date(g, r.get("release_date"))
        if c:
            changes.append(f"{g['title']}: {c}")
        if r["score"] is None and oc_ok and not (g.get("metacritic") or {}).get("score"):
            try:                                          # fallback: OpenCritic, only when Metacritic has nothing
                hits = opencritic.search(g["title"])
                if hits and hits[0].get("id") and (hits[0].get("dist") or 0) < 0.2:
                    o = opencritic.read_score(hits[0]["id"])
                    checks.append(log_check("opencritic", g["id"], o["url"], True, {"score": o["score"]}))
                    if o["score"] is not None:
                        g["alt_score"] = {"score": o["score"], "source": "OpenCritic", "url": o["url"], "checked_at": on, "verified": True}
                        g["verified"] = True
            except FetchError as e:
                checks.append(log_check("opencritic", g["id"], "api.opencritic.com", False, {"error": str(e)}))
                oc_ok = False                             # stop asking OpenCritic for the rest of the night
        if g["status"] == "listed" and not g.get("inclusion_reason") and g.get("verified"):
            s = (g.get("metacritic") or {}).get("score") or (g.get("alt_score") or {}).get("score")
            if s is not None and s < 70 and (not g.get("score_locked") or not was_verified):
                g["status"], g["review_note"] = "review", f"confirmed score is {s}, below 70 - keep by request or drop"
                changes.append(f"{g['title']}: moved to review (score {s})")

    if args.new_only:
        todo = [g for g in games if g.get("first_seen") == on and g["status"] in ("pending_score", "listed")]
    else:
        todo = [g for g in games if g["status"] == "pending_score" or (g["status"] == "listed" and not g.get("score_locked"))]
        backlog = [g for g in games if g["status"] == "listed" and not g.get("verified") and g not in todo]
        todo += backlog[: args.backlog]
    for g in todo:
        check(g)
    for g in games:
        c = lifecycle(g, on)
        if c:
            changes.append(f"{g['title']}: {c}")
    append_jsonl(CHECKS, checks)
    save_games(games)
    ok = sum(1 for c in checks if c["ok"])
    print(f"recheck: {len(todo)} games, {ok}/{len(checks)} checks ok, {len(changes)} changes")
    for c in changes:
        print("  -", c)
    if checks and ok == 0:
        sys.exit(2)                                       # every check failed: tell the runner


if __name__ == "__main__":
    main()
