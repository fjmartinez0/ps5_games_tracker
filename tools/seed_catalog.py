"""One-time: build data/games.json from the Metacritic seed list + the old spreadsheet rows.

Rebuild rule agreed with the owner: Metacritic's 70+ PS5 lists are the backbone; every game from the
old sheet is kept unless there is a strong reason (DLC, sports, VR-only, free-to-play, below 70 on
Metacritic). Old-sheet games that Metacritic doesn't list stay on the catalog, marked unverified,
until the checker confirms a score. Writes a report to tools/rebuild_report.md.

Run once, from the repo root:  python3 tools/seed_catalog.py
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
from common import (DATA, EXCLUDED_CATEGORIES, GAMES, metacritic_slug, norm_title, save_json)  # noqa: E402

SEED = Path(__file__).with_name("metacritic_seed_2026-10-17.txt")
REPORT = Path(__file__).with_name("rebuild_report.md")
AS_OF = "2026-10-17"
MC_BROWSE = "https://www.metacritic.com/browse/game/ps5/all/all-time/metascore/?releaseYearMin={y}&releaseYearMax={y}"

# old-sheet titles whose Metacritic row uses a different spelling
ALIASES = {
    "death stranding 2 on beach": "death stranding 2 on beach",
    "final fantasy tactics ivalice chronicles": "final fantasy tactics ivalice chronicles",
    "yakuza 0 director s cut": "yakuza 0 director s cut",
    "patapon 1 2 replay": "patapon 1 2 replay",
}
# old-sheet rows the rules exclude, with the reason shown in the report
LEGACY_EXCLUDE = {
    "Rain World: The Watcher": ("dlc", None),
    "Lies of P: Overture": ("dlc", None),
    "Diablo IV: Lord of Hatred": ("dlc", None),
    "WWE 2K25": ("sports", None), "MLB The Show 25": ("sports", None),
    "EA Sports UFC 6": ("sports", None), "EA Sports College Football 27": ("sports", None),
}


def main():
    legacy = json.loads((DATA / "legacy_sheet.json").read_text())
    legacy_by_key = {norm_title(r["Game"]): r for r in legacy}

    seed = []
    for line in SEED.read_text().splitlines():
        if not line.strip() or line.startswith("#"):
            continue
        date, score, title, cat, scale, genre = [x.strip() for x in line.split("|")]
        seed.append({"date": date, "score": int(score), "title": title, "cat": cat, "scale": scale, "genre": genre})

    games, used_legacy, report = [], set(), {"excluded": [], "review": [], "legacy_only": [], "legacy_dropped": [],
                                             "legacy_changed": []}

    def add(g):
        g["id"] = f"PS5-{len(games) + 1:04d}"
        games.append(g)
        return g

    for s in seed:
        key = norm_title(s["title"])
        leg = legacy_by_key.get(key) or legacy_by_key.get(ALIASES.get(key, ""))
        if leg:
            used_legacy.add(norm_title(leg["Game"]))
        year = int(s["date"][:4])
        status = "listed" if s["cat"] == "game" else "review" if s["cat"] == "review" else "excluded"
        g = {
            "title": s["title"], "status": status,
            "category": s["cat"] if s["cat"] != "review" else "game",
            "excluded_reason": EXCLUDED_CATEGORIES.get(s["cat"]),
            "review_note": s["genre"].split("(", 1)[1].rstrip(")") if s["cat"] == "review" and "(" in s["genre"] else None,
            "inclusion_reason": None,
            "release_date": s["date"], "ps5_year": year,
            "scale": s["scale"], "genre": s["genre"].split(" (")[0],
            "metacritic": {"score": s["score"], "url": f"https://www.metacritic.com/game/{metacritic_slug(s['title'])}/critic-reviews/?platform=playstation-5",
                           "source_url": MC_BROWSE.format(y=year), "checked_at": AS_OF, "verified": False},
            "alt_score": None,
            "score_locked": True, "score_locked_at": AS_OF if _days(s["date"], AS_OF) >= 30 else None,
            "physical": (leg or {}).get("Physical?") if (leg or {}).get("Physical?") in ("Yes", "No") else "Unverified",
            "ps_store": {"url": _ps_url(leg), "regular": None, "current": None, "checked_at": None},
            "disc": {"deku_url": None, "msrp": None, "stores": {}},
            "first_seen": s["date"], "listed_on": AS_OF if status == "listed" else None,
            "source": "rebuild", "verified": False,
        }
        if g["score_locked_at"] is None:
            g["score_locked"] = False
        if leg and leg.get("Metacritic PS5") not in (None, s["score"]):
            report["legacy_changed"].append(f"{s['title']}: sheet said {leg['Metacritic PS5']}, Metacritic shows {s['score']}")
        if leg and int(leg["PS5 Year"]) != year:
            report["legacy_changed"].append(f"{s['title']}: sheet said {leg['PS5 Year']}, PS5 release is {s['date']}")
        add(g)
        if status == "excluded":
            report["excluded"].append(f"{s['title']} ({s['score']}): {g['excluded_reason']}")
        elif status == "review":
            report["review"].append(f"{s['title']} ({s['score']}): {g['review_note']}")

    # old-sheet rows Metacritic's 70+ lists don't contain
    below_70 = {"shadow labyrinth": 68, "clive barker s hellraiser revival": 69}
    for r in legacy:
        key = norm_title(r["Game"])
        if key in used_legacy:
            continue
        if r["Game"] in LEGACY_EXCLUDE:
            cat = LEGACY_EXCLUDE[r["Game"]][0]
            report["legacy_dropped"].append(f"{r['Game']}: {EXCLUDED_CATEGORIES[cat]}")
            continue
        if key in below_70:
            report["legacy_dropped"].append(f"{r['Game']}: Metacritic PS5 score is {below_70[key]}, below 70")
            continue
        mc, alt = r.get("Metacritic PS5"), r.get("Alt Critic Score")
        has_score = (alt if alt is not None else mc) is not None
        add({
            "title": r["Game"], "status": "listed" if has_score else "pending_score", "category": "game", "excluded_reason": None, "review_note": None,
            "inclusion_reason": None, "release_date": None, "ps5_year": int(r["PS5 Year"]),
            "scale": (r["Scale"] or "AA").split("/")[0].strip(), "genre": r["Genre"],
            "metacritic": None,
            "alt_score": {"score": alt if alt is not None else mc, "source": "old spreadsheet (unverified)",
                          "url": r.get("Score Source"), "checked_at": None, "verified": False} if (alt or mc) else None,
            "score_locked": False, "score_locked_at": None,
            "physical": r["Physical?"] if r["Physical?"] in ("Yes", "No") else "Unverified",
            "ps_store": {"url": _ps_url(r), "regular": r.get("Price CAD"), "current": None, "checked_at": None},
            "disc": {"deku_url": None, "msrp": None, "stores": {}},
            "first_seen": None if has_score else AS_OF, "listed_on": AS_OF if has_score else None,
            "source": "migration", "verified": False,
        })
        report["legacy_only"].append(f"{r['Game']} ({r['PS5 Year']}, sheet score {alt if alt is not None else mc})")

    save_json(GAMES, games)
    listed = [g for g in games if g["status"] == "listed"]
    lines = [f"# Catalog rebuild report ({AS_OF})", "",
             f"- Games tracked: {len(games)}  (listed {len(listed)}, review {len(report['review'])}, excluded {len(report['excluded'])})",
             f"- Old sheet rows: {len(legacy)}; kept {len(legacy) - len(report['legacy_dropped'])}, dropped {len(report['legacy_dropped'])}", ""]
    sections = [("Old-sheet games dropped (strong reason)", "legacy_dropped"),
                ("Old-sheet games Metacritic doesn't list - kept, marked unverified until a score is confirmed", "legacy_only"),
                ("Old-sheet values corrected by Metacritic", "legacy_changed"),
                ("Needs your decision (shown in the report, not on the catalog)", "review"),
                ("Excluded by the rules", "excluded")]
    for head, k in sections:
        lines += [f"## {head} ({len(report[k])})", ""] + [f"- {x}" for x in report[k]] + [""]
    REPORT.write_text("\n".join(lines))
    print("\n".join(lines[:4]))


def _days(a, b):
    import datetime as dt
    return (dt.date.fromisoformat(b) - dt.date.fromisoformat(a)).days


def _ps_url(leg):
    u = (leg or {}).get("Price / Availability Source") or ""
    return u if "store.playstation.com/en-ca/" in u and ("/concept/" in u or "/product/" in u) else None


if __name__ == "__main__":
    main()
