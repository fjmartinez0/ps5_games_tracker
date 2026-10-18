"""One-time: write data/events.json and data/seed_observations.json from sale prices researched
on 2026-10-17 (before the tracker existed). Every row carries its source URL.

Run once from the repo root:  python3 tools/seed_history.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
from common import EVENTS, SEED_OBS, save_json  # noqa: E402

MS = "https://mobilesyrup.com"
SRC = {
    "DOP25": f"{MS}/2025/05/27/playstation-days-of-play-2025-sale-ps5-consoles-accessories-games/",
    "SUM25": f"{MS}/2025/07/16/playstation-summer-sale-2025/",
    "BF25": f"{MS}/2025/11/21/playstation-canada-black-friday-2025-deals/",
    "HOL25": "https://www.tomsguide.com/gaming/playstation/first-playstation-sale-of-2026-has-ps5-games-from-usd4-heres-15-deals-id-buy-now",
    "DOP26": f"{MS}/2026/05/26/playstation-big-annual-days-of-play-sale-2026/",
    "EB_BF25": f"{MS}/2025/11/20/eb-games-canada-black-friday-2025-deals/",
    "EB_BOX25": f"{MS}/2025/12/22/eb-games-launches-boxing-week-deals-secret-in-store-sales/",
    "WM_BF25": f"{MS}/2025/11/24/walmart-canada-black-friday-2025-week-3-deals/",
    "DEKU": "https://www.dekudeals.com/?country=ca",
}

EVENT_LIST = [
    {"id": "DOP25", "name": "Days of Play 2025", "start": "2025-05-28", "end": "2025-06-11", "special": True, "formats": ["digital"], "source": SRC["DOP25"]},
    {"id": "SUM25", "name": "Summer Sale 2025", "start": "2025-07-16", "end": None, "special": False, "formats": ["digital"], "source": SRC["SUM25"]},
    {"id": "BF25", "name": "Black Friday 2025", "start": "2025-11-21", "end": "2025-12-05", "special": True, "formats": ["digital", "disc"], "source": SRC["BF25"]},
    {"id": "HOL25", "name": "Holiday Sale 2025", "start": "2025-12-17", "end": "2026-01-21", "special": True, "formats": ["digital"], "source": SRC["HOL25"], "note": "US % off"},
    {"id": "BOX25", "name": "Boxing Week 2025", "start": "2025-12-21", "end": "2025-12-31", "special": True, "formats": ["disc"], "source": SRC["EB_BOX25"], "note": "EB Games"},
    {"id": "DOP26", "name": "Days of Play 2026", "start": "2026-05-27", "end": "2026-06-10", "special": True, "formats": ["digital"], "source": SRC["DOP26"]},
    {"id": "OCT26", "name": "October Sale 2026", "start": "2026-10-08", "end": "2026-10-22", "special": False, "formats": ["digital"], "source": SRC["DEKU"], "note": "observed Oct 17"},
    # expected (not yet confirmed) - the agent replaces these with confirmed dates when they are announced
    {"id": "BF26", "name": "Black Friday 2026", "start": "2026-11-20", "end": "2026-12-04", "special": True, "formats": ["digital", "disc"], "expected": True, "source": None, "note": "expected, based on 2025"},
    {"id": "BOX26", "name": "Boxing Week 2026", "start": "2026-12-21", "end": "2026-12-31", "special": True, "formats": ["disc"], "expected": True, "source": None, "note": "expected, based on 2025"},
    {"id": "HOL26", "name": "Holiday Sale 2026", "start": "2026-12-16", "end": "2027-01-20", "special": True, "formats": ["digital"], "expected": True, "source": None, "note": "expected, based on 2025"},
]

# (title, format, store, event, regular, sale_price | None, pct_if_no_price, extra)
OBS = [
    ("Kingdom Come: Deliverance II", "digital", "PlayStation Store", "DOP25", 93.49, 74.79),
    ("Kingdom Come: Deliverance II", "digital", "PlayStation Store", "SUM25", 93.49, 70.11),
    ("Kingdom Come: Deliverance II", "digital", "PlayStation Store", "BF25", 93.49, 56.09),
    ("Kingdom Come: Deliverance II", "digital", "PlayStation Store", "OCT26", 93.49, 32.72),
    ("Split Fiction", "digital", "PlayStation Store", "BF25", 66.99, 53.59),
    ("Assassin's Creed Shadows", "digital", "PlayStation Store", "SUM25", 89.99, 67.49),
    ("Assassin's Creed Shadows", "digital", "PlayStation Store", "BF25", 89.99, 53.99),
    ("Indiana Jones and the Great Circle", "digital", "PlayStation Store", "DOP25", 93.49, 74.79),
    ("Indiana Jones and the Great Circle", "digital", "PlayStation Store", "SUM25", 93.49, 74.79),
    ("Clair Obscur: Expedition 33", "digital", "PlayStation Store", "SUM25", 66.99, 60.29),
    ("Clair Obscur: Expedition 33", "digital", "PlayStation Store", "BF25", 66.99, 53.59),
    ("Clair Obscur: Expedition 33", "digital", "PlayStation Store", "HOL25", None, None, 20),
    ("Clair Obscur: Expedition 33", "digital", "PlayStation Store", "OCT26", 66.99, 50.24),
    ("Forza Horizon 5", "digital", "PlayStation Store", "DOP25", 79.99, 63.99),
    ("Forza Horizon 5", "digital", "PlayStation Store", "SUM25", 79.99, 59.99),
    ("Forza Horizon 5", "digital", "PlayStation Store", "BF25", 79.99, 51.99),
    ("Forza Horizon 5", "digital", "PlayStation Store", "HOL25", None, None, 41),
    ("Death Stranding 2: On The Beach", "digital", "PlayStation Store", "BF25", 89.99, 63.89),
    ("Gears of War: Reloaded", "digital", "PlayStation Store", "BF25", 49.99, 32.49),
    ("Gears of War: Reloaded", "digital", "PlayStation Store", "HOL25", None, None, 51),
    ("Metal Gear Solid Delta: Snake Eater", "digital", "PlayStation Store", "BF25", 93.49, 65.44),
    ("Metal Gear Solid Delta: Snake Eater", "digital", "PlayStation Store", "OCT26", 93.49, 46.89),
    ("Hollow Knight: Silksong", "digital", "PlayStation Store", "HOL25", None, None, 21),
    ("Borderlands 4", "digital", "PlayStation Store", "BF25", 89.99, 71.99),
    ("Dying Light: The Beast", "digital", "PlayStation Store", "BF25", 79.99, 63.99),
    ("Silent Hill f", "digital", "PlayStation Store", "BF25", 93.49, 65.44),
    ("Battlefield 6", "digital", "PlayStation Store", "BF25", 89.99, 76.49),
    ("Battlefield 6", "digital", "PlayStation Store", "HOL25", None, None, 30),
    ("Battlefield 6", "digital", "PlayStation Store", "OCT26", 89.99, 35.99),
    ("Dispatch", "digital", "PlayStation Store", "HOL25", None, None, 10),
    ("The Outer Worlds 2", "digital", "PlayStation Store", "BF25", 89.99, 71.99),
    ("ARC Raiders", "digital", "PlayStation Store", "HOL25", None, None, 21),
    ("Ninja Gaiden 2 Black", "digital", "PlayStation Store", "SUM25", 66.99, 43.54),
    # disc
    ("Assassin's Creed Shadows", "disc", "EB Games", "BF25", 89.99, 49.99),
    ("Assassin's Creed Shadows", "disc", "EB Games", "BOX25", 89.99, 44.99, None, "2025-12-23"),
    ("Battlefield 6", "disc", "EB Games", "BF25", 89.99, 79.99),
    ("Borderlands 4", "disc", "EB Games", "BF25", 89.99, 69.99),
    ("Borderlands 4", "disc", "Walmart", "BF25", 89.96, 69.96, None, "2025-11-26"),
    ("Borderlands 4", "disc", "EB Games", "BOX25", 89.99, 69.99),
    ("Death Stranding 2: On The Beach", "disc", "EB Games", "BF25", 89.99, 64.99),
    ("Kingdom Come: Deliverance II", "disc", "EB Games", "BF25", 79.99, 59.99),
    ("Metal Gear Solid Delta: Snake Eater", "disc", "EB Games", "BF25", 89.99, 69.99),
    ("Metal Gear Solid Delta: Snake Eater", "disc", "EB Games", "BOX25", 89.99, 49.99),
    ("Silent Hill f", "disc", "EB Games", "BF25", 89.99, 69.99),
    ("Silent Hill f", "disc", "EB Games", "BOX25", 89.99, 69.99),
    ("Elden Ring Nightreign", "disc", "EB Games", "BF25", 59.99, 44.99),
    ("Mafia: The Old Country", "disc", "EB Games", "BF25", 69.99, 54.99),
    ("Sonic Racing: CrossWorlds", "disc", "EB Games", "BF25", 89.99, 64.99),
]
# lowest prices ever, Deku Deals Canada, read 2026-10-17 (dates not shown on the site)
LOWEST = {
    "Kingdom Come: Deliverance II": (32.72, 44.99), "Clair Obscur: Expedition 33": (50.24, 49.99),
    "Ghost of Yotei": (63.89, 64.96), "Silent Hill f": (46.74, 54.98),
    "Metal Gear Solid Delta: Snake Eater": (37.39, 39.99), "Battlefield 6": (35.99, 42.32),
    "DOOM: The Dark Ages": (29.69, 49.99), "Forza Horizon 5": (31.99, None),
    "Death Stranding 2: On The Beach": (51.29, 49.96),
}


def main():
    ev = {e["id"]: e for e in EVENT_LIST}
    obs = []
    for row in OBS:
        title, fmt, store, eid, regular, price = row[:6]
        pct = row[6] if len(row) > 6 and row[6] is not None else None
        date = row[7] if len(row) > 7 else ev[eid]["start"]
        if price is not None:
            pct = round((1 - price / regular) * 100)
        src = SRC[{"EB Games": "EB_" + eid, "Walmart": "WM_" + eid}.get(store, eid)] if store != "PlayStation Store" else SRC[eid if eid != "OCT26" else "DEKU"]
        obs.append({"title": title, "format": fmt, "store": store, "event": eid, "date": date,
                    "regular": regular, "price": price, "pct": pct, "us_pct": price is None, "source": src})
    lows = [{"title": t, "format": f, "price": p, "source": SRC["DEKU"], "seen_on": "2026-10-17"}
            for t, (d, x) in LOWEST.items() for f, p in (("digital", d), ("disc", x)) if p is not None]
    save_json(EVENTS, EVENT_LIST)
    save_json(SEED_OBS, {"note": "Sale prices researched on 2026-10-17 from published sale lists, before nightly tracking began. "
                                 "Disc regular prices use the most common launch price, not a store's own 'regular' label.",
                         "observations": obs, "lowest_known": lows})
    print(len(EVENT_LIST), "events,", len(obs), "observations,", len(lows), "lowest prices")


if __name__ == "__main__":
    main()
