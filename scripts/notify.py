"""Phone notifications through ntfy.sh. Two topics: results (new games, price drops) and problems.
Nothing is sent on a normal night with no news.

  python3 scripts/notify.py --before .run/games_before.json    # after a run: new games + price alerts
  python3 scripts/notify.py --problem "Agent run failed"        # low-priority problem note
"""
import argparse
import json
import urllib.request

from common import SALES, WISHLIST, load_config, load_games, load_json, save_json, today

MAX_SINGLE = 3


def send(topic: str, title: str, body: str, *, priority: str = "default", tags: str = "", click: str | None = None):
    if not topic:
        print(f"[ntfy disabled] {title}: {body}")
        return
    headers = {"Title": title.encode("utf-8").decode("latin-1", "ignore"), "Priority": priority, "Tags": tags}
    if click:
        headers["Click"] = click
    req = urllib.request.Request(f"https://ntfy.sh/{topic}", data=body.encode("utf-8"), headers=headers, method="POST")
    try:
        urllib.request.urlopen(req, timeout=20).read()
    except Exception as e:  # never fail the run because a notification failed
        print("ntfy error:", e)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--before")
    ap.add_argument("--problem")
    args = ap.parse_args()
    cfg = load_config()
    url = cfg.get("DASHBOARD_URL")
    if args.problem:
        send(cfg.get("NTFY_PROBLEMS_TOPIC"), "PS5 tracker problem", args.problem, priority="low", tags="warning", click=url)
        return

    games = load_games()
    by_id = {g["id"]: g for g in games}
    before = {g["id"]: g["status"] for g in (load_json(args.before, []) if args.before else [])}
    added = [g for g in games if g["status"] == "listed" and before.get(g["id"]) != "listed"]
    msgs = []
    if added:
        if len(added) <= MAX_SINGLE:
            for g in added:
                s = (g.get("metacritic") or {}).get("score") or (g.get("alt_score") or {}).get("score")
                msgs.append(("New game on the list", f"{g['title']} - score {s}, {g.get('scale')}, {g.get('genre')}"))
        else:
            msgs.append((f"{len(added)} new games on the list", ", ".join(g["title"] for g in added[:8]) + ("…" if len(added) > 8 else "")))

    wish = set((load_json(WISHLIST, {}) or {}).get("game_ids", []))
    sales = load_json(SALES, {"open": [], "closed": []})
    from rules import alert_due
    due = {}
    for r in sales.get("open", []):
        if r.get("changed_on") == today() and alert_due(r, r["game_id"] in wish):
            k = (r["game_id"], r["format"])
            if k not in due or r["price"] < due[k]["price"]:      # several disc stores: keep the cheapest
                due[k] = r
    lines = []
    for (gid, fmt), r in sorted(due.items()):
        g = by_id.get(gid, {"title": gid})
        low = r.get("lowest_before")
        tag = " - lowest ever" if low is not None and r["price"] < low - 0.01 else ""
        cut = " (price cut)" if r.get("kind") == "price_cut" else ""
        end = f" until {r['end']}" if r.get("end") else ""
        lines.append(f"{g['title']} {fmt} at {r['store']}: ${r['baseline']:.2f} → ${r['price']:.2f} (−{r['pct']}%){tag}{cut}{end}")
    if lines:
        if len(lines) <= MAX_SINGLE:
            msgs += [("Wishlist price drop", ln) for ln in lines]
        else:
            msgs.append((f"{len(lines)} wishlist price drops", "\n".join(lines)))
    for title, body in msgs:
        send(cfg.get("NTFY_ALERTS_TOPIC"), title, body, tags="video_game", click=url)
    for r in sales.get("open", []):
        if (r["game_id"], r["format"]) in due:
            r["alerted"] = True
    save_json(SALES, sales)
    print(f"notify: {len(added)} new games, {len(lines)} price alerts, {len(msgs)} messages sent")
    print(json.dumps([m[0] for m in msgs]))


if __name__ == "__main__":
    main()
