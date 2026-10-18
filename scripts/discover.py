"""Deterministic discovery: read Metacritic's PS5 lists for the current year (sorted by score) and
list every 70+ game we don't track yet. Also lists tracked games that still miss links, so the AI
agent can fill them in. Writes .run/candidates.json for the agent.
"""
import json

from common import RUN, FetchError, load_games, metacritic_slug, norm_title, now, save_json
from sources import metacritic

ENRICH_PER_NIGHT = 15
MAX_PAGES = 8


def main():
    games = load_games()
    known_titles = {norm_title(g["title"]) for g in games}
    known_slugs = {(g.get("metacritic") or {}).get("url", "").split("/game/")[-1].split("/")[0] for g in games}
    years = {now().year} | ({now().year - 1} if now().month == 1 else set())
    new, errors = [], []
    for y in sorted(years):
        for p in range(1, MAX_PAGES + 1):
            try:
                items = metacritic.browse(y, p)
            except FetchError as e:
                errors.append(str(e))
                break
            if not items:
                break
            for it in items:
                if it["score"] is not None and it["score"] >= 70 and norm_title(it["title"]) not in known_titles \
                        and it["slug"] not in known_slugs and metacritic_slug(it["title"]) not in known_slugs:
                    new.append(it)
            if all(it["score"] is not None and it["score"] < 70 for it in items[-5:]):
                break
    enrich = [{"id": g["id"], "title": g["title"], "release_date": g.get("release_date"),
               "missing": [k for k, v in (("ps_store_url", (g.get("ps_store") or {}).get("url")),
                                          ("deku_url", (g.get("disc") or {}).get("deku_url")),
                                          ("release_date", g.get("release_date"))) if not v]}
              for g in games if g["status"] in ("listed", "pending_score")]
    enrich = [e for e in enrich if e["missing"]]
    enrich.sort(key=lambda e: (e["release_date"] or "9999"), reverse=True)
    out = {"generated_at": now().isoformat(), "scored_new": new, "enrich": enrich[:ENRICH_PER_NIGHT],
           "enrich_remaining": max(0, len(enrich) - ENRICH_PER_NIGHT), "errors": errors}
    save_json(RUN / "candidates.json", out)
    print(f"discover: {len(new)} new 70+ games on Metacritic, {len(out['enrich'])} games to enrich"
          f" ({out['enrich_remaining']} more queued), {len(errors)} errors")
    if errors:
        print(json.dumps(errors, indent=1))


if __name__ == "__main__":
    main()
