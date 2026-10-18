"""Deku Deals Canada: current PS5 disc prices at Best Buy, Video Games Plus and PNP Games, plus the
lowest price ever per format. Amazon.ca also appears there but is not one of our disc stores.

Multi-platform games: Deku's default item can be the Switch 2 or Xbox version. Item URLs for PS5 must
be the PS5 item (the agent records it; source_test checks the platform).
"""
import re

from common import fetch, money
from sources.textutil import all_json_blobs, text_lines, walk

STORE_NAMES = {"Best Buy Canada": "Best Buy", "Best Buy": "Best Buy", "Video Games Plus": "Video Games Plus",
               "PNP Games": "PNP Games", "PlayStation Store": "PlayStation Store", "Amazon.ca": "Amazon.ca",
               "Walmart": "Walmart", "Walmart.ca": "Walmart", "EB Games": "EB Games"}


def item_url(slug: str) -> str:
    return f"https://www.dekudeals.com/items/{slug}?format=all&country=ca"


def read(url: str) -> dict:
    """Return {platforms_priced, offers:[{store, format, price, was}], lowest:{digital, disc}, history:[...]}."""
    page = fetch(url)
    lines = text_lines(page)
    out = {"url": url, "offers": [], "lowest": {"digital": None, "disc": None}, "history": [], "is_ps5": False}
    for i, ln in enumerate(lines):
        store = STORE_NAMES.get(ln)
        if not store:
            continue
        end = next((j for j in range(i + 1, min(len(lines), i + 7)) if lines[j] in STORE_NAMES), min(len(lines), i + 7))
        window = " ".join(lines[i: end])
        fm = re.search(r"\b(PS5|PlayStation 5)\s+(Physical|Digital)\b", window)
        if not fm:
            continue
        out["is_ps5"] = True
        prices = re.findall(r"\$\s?\d[\d,]*\.\d{2}", window)
        if not prices:
            continue
        cur = money(prices[0])
        was = money(prices[1]) if len(prices) > 1 and money(prices[1]) and money(prices[1]) > cur else None
        out["offers"].append({"store": store, "format": "disc" if fm.group(2) == "Physical" else "digital", "price": cur, "was": was})
    # "All time low" lines: "PS5 Physical $49.96 (-44%)" / "PS5 Digital $51.29 (-43%)"
    text = "\n".join(lines)
    for fmt, key in (("Physical", "disc"), ("Digital", "digital")):
        m = re.search(r"(?:PS5|PlayStation 5)\s+%s[^\n$]{0,40}?\$\s?(\d[\d,]*\.\d{2})\s*\(-\d+%%\)" % fmt, text)
        if m and "low" in text[max(0, m.start() - 300): m.start()].lower():
            out["lowest"][key] = money(m.group(1))
    # Price-history chart data, when the page embeds it (series of [timestamp, price])
    for blob in all_json_blobs(page):
        for d in walk(blob):
            for k, v in d.items():
                if isinstance(v, list) and len(v) > 2 and all(isinstance(p, list) and len(p) == 2 for p in v[:3]) and "price" in k.lower():
                    out["history"].append({"series": k, "points": v})
    # PlayStation Store Canada link for the PS5 version (used to fill in missing links)
    m = re.search(r'https://store\.playstation\.com/en-ca/(?:product|concept)/[A-Za-z0-9_\-]+', page)
    out["ps_store_url"] = m.group(0) if m else None
    t = re.search(r"<title>(.*?)</title>", page, re.S)
    out["page_title"] = re.sub(r"\s+", " ", t.group(1)).strip() if t else None
    seen, uniq = set(), []
    for o in out["offers"]:
        if (o["store"], o["format"]) not in seen:
            seen.add((o["store"], o["format"]))
            uniq.append(o)
    out["offers"] = uniq
    return out
