"""Deku Deals Canada: current PS5 prices per store (digital: PlayStation Store; disc: Best Buy,
Video Games Plus, PNP Games), the lowest price ever, and the full daily price history.

Each price row on the page carries a small JSON record (outAnalytics[...] = {...}) with the store,
platform (item_category "ps5"), format (item_variant "physical"/"digital"), price in cents and the
discount in hundredths of a percent. The price-history chart data is embedded as JSON
(<script id='price_history_data'>), one column per store/platform/format.
"""
import json
import re

from common import fetch, money

AFFILIATION = {"playstation_ca": "PlayStation Store", "bestbuy_ca": "Best Buy", "vgp_ca": "Video Games Plus",
               "pnp_games_ca": "PNP Games", "amazon_ca": "Amazon.ca", "walmart_ca": "Walmart", "ebgames_ca": "EB Games"}
HISTORY_STORES = {"PlayStation Store": "PlayStation Store", "Best Buy Canada": "Best Buy",
                  "Video Games Plus": "Video Games Plus", "PNP Games": "PNP Games", "Walmart": "Walmart", "EB Games": "EB Games"}
HEADER_RE = re.compile(r"^(?P<store>.+?) \((?:(?P<platform>[^,]+), )?(?P<fmt>digital|physical)\)$")


def item_url(slug: str) -> str:
    # platform=all: for games also on Switch 2, Deku shows only the Switch 2 version without it
    return f"https://www.dekudeals.com/items/{slug}?format=all&country=ca&platform=all"


def canonical(url: str) -> str:
    m = re.match(r"^https://www\.dekudeals\.com/items/([a-z0-9-]+)", url or "")
    return item_url(m.group(1)) if m else url


def read(url: str) -> dict:
    """Return {is_ps5, offers:[{store, format, price, was}], lowest:{digital, disc}, history:{(fmt, store): [(date, price)]},
    ps_store_url, page_title}. Prices in CAD; formats 'digital' / 'disc'."""
    page = fetch(url)
    out = {"url": url, "offers": [], "lowest": {"digital": None, "disc": None}, "history": {}, "is_ps5": False,
           "ps_store_url": None, "page_title": None}
    t = re.search(r"<title>(.*?)</title>", page, re.S)
    out["page_title"] = re.sub(r"\s+", " ", t.group(1)).replace("| Deku Deals", "").strip() if t else None

    # 1. current offers
    seen = set()
    for m in re.finditer(r"outAnalytics\['([^']+)'\]\s*=\s*(\{.*?\})\s*;?\s*\n", page):
        try:
            rec = json.loads(m.group(2))
            it = rec["items"][0]
        except (json.JSONDecodeError, KeyError, IndexError):
            continue
        if it.get("item_category") != "ps5":
            continue
        out["is_ps5"] = True
        aff, cents = it.get("affiliation", ""), it.get("price") or rec.get("value") or 0
        store = AFFILIATION.get(aff, aff)
        if aff == "playstation_ca" and not out["ps_store_url"]:
            pid = m.group(1).split(":", 1)[-1]
            if re.fullmatch(r"[A-Z]{2}\d{4}-[A-Z0-9_]+-[A-Z0-9]+", pid):
                out["ps_store_url"] = f"https://store.playstation.com/en-ca/product/{pid}"
        if not cents:
            continue                                                   # store lists the game but has no price now
        fmt = "disc" if it.get("item_variant") == "physical" else "digital"
        price = round(cents / 100, 2)
        was = None             # Deku's discount is against its own reference price; regular prices come from history
        key = (store, fmt)
        if key in seen:                                                # keep the cheapest listing per store/format
            prev = next(o for o in out["offers"] if (o["store"], o["format"]) == key)
            if price < prev["price"]:
                prev.update(price=price, was=was)
            continue
        seen.add(key)
        out["offers"].append({"store": store, "format": fmt, "price": price, "was": was})

    # 2. daily price history (PS5 columns only)
    hm = re.search(r"<script id='price_history_data'[^>]*>(.*?)</script>", page, re.S)
    if hm:
        try:
            h = json.loads(hm.group(1))
            headers, rows = h.get("headers", []), h.get("data", [])
            width = max((len(r) for r in rows), default=0) - 1        # series count (date column excluded)
            offset = width - len(headers)                             # leading series without a header
            for hi, name in enumerate(headers):
                hd = HEADER_RE.match(name)
                platform = hd["platform"] if hd else None
                single_platform = not any(HEADER_RE.match(x) and HEADER_RE.match(x)["platform"] for x in headers)
                if not hd or hd["store"] not in HISTORY_STORES or not (platform == "PS5" or (platform is None and single_platform and out["is_ps5"])):
                    continue
                fmt = "disc" if hd["fmt"] == "physical" else "digital"
                col = 1 + offset + hi
                pts = [(r[0], round(float(r[col]), 2)) for r in rows if col < len(r) and isinstance(r[col], (int, float))]
                if pts:
                    out["history"].setdefault((fmt, HISTORY_STORES[hd["store"]]), []).extend(pts)
        except (json.JSONDecodeError, TypeError, ValueError):
            pass
    for (fmt, store), pts in out["history"].items():
        if store == "Amazon.ca":
            continue
        low = min(p for _, p in pts)
        out["lowest"][fmt] = low if out["lowest"][fmt] is None else min(out["lowest"][fmt], low)

    # 3. fallback lowest prices from the "All time low" table when there's no history
    if not out["history"]:
        i = page.find("All time low")
        if i >= 0:
            seg = page[i: page.find("price-history-chart", i) if page.find("price-history-chart", i) > 0 else i + 3000]
            toks = [x.strip() for x in re.sub(r"<[^>]+>", "\n", seg).split("\n") if x.strip()]
            cols = [x.lower() for x in toks if x in ("Physical", "Digital")]
            platform, cells = None, {}
            single = not any(x in ("PS5", "Steam", "Xbox X|S", "Switch", "Switch 2") for x in toks)
            for x in toks:
                if x in ("PS5", "Steam", "Xbox X|S", "Switch", "Switch 2"):
                    platform = x
                    cells.setdefault(x, [])
                elif (platform or single) and (x.startswith("$") or "&nbsp;" in x):
                    cells.setdefault(platform or "PS5", []).append(money(x) if x.startswith("$") else None)
            for fmt_name, price in zip(cols, cells.get("PS5", [])):
                if price is not None:
                    out["lowest"]["disc" if fmt_name == "physical" else "digital"] = price
    return out


def history_changes(history: dict) -> list[tuple]:
    """Collapse daily series into change points: [(date, format, store, price)]."""
    out = []
    for (fmt, store), pts in history.items():
        last = None
        for date, price in sorted(pts):
            if last is None or abs(price - last) > 0.009:
                out.append((date, fmt, store, price))
                last = price
    return out
