"""PlayStation Store Canada: digital price (non-member) and PS5 release date."""
import datetime as dt
import re

from common import fetch, json_ld, money
from sources.textutil import all_json_blobs, walk

BASE = "https://store.playstation.com/en-ca/"


def read(url: str) -> dict:
    """Return {title, regular, current, on_sale, sale_end, release_date, edition, plus_only_discount}."""
    page = fetch(url)
    out = {"url": url, "title": None, "regular": None, "current": None, "on_sale": False, "sale_end": None,
           "release_date": None, "edition": None, "plus_only_discount": False, "strategy": None}

    # Strategy 1: the Apollo cache embedded in <script type="application/json"> blocks
    for blob in all_json_blobs(page):
        for d in walk(blob):
            p = d.get("price") if isinstance(d.get("price"), dict) else None
            if p and "basePrice" in p and out["regular"] is None:
                base, disc = money(p.get("basePrice")), money(p.get("discountedPrice"))
                tied = bool(p.get("isTiedToSubscription")) or "PS_PLUS" in str(p.get("serviceBranding", ""))
                out["regular"] = base
                if disc is not None and base is not None and disc < base and not tied:
                    out["current"], out["on_sale"] = disc, True
                    out["sale_end"] = _ms_to_date(p.get("endTime"))
                else:
                    out["current"] = base
                    out["plus_only_discount"] = bool(tied and disc is not None and base and disc < base)
                out["title"] = out["title"] or d.get("name")
                out["edition"] = (d.get("edition") or {}).get("name") if isinstance(d.get("edition"), dict) else None
                out["strategy"] = "apollo"
            if out["release_date"] is None and isinstance(d.get("releaseDate"), str):
                out["release_date"] = d["releaseDate"][:10]
    # Strategy 2: JSON-LD offers
    if out["regular"] is None:
        for d in json_ld(page):
            offers = d.get("offers") if isinstance(d, dict) else None
            if isinstance(offers, list):
                offers = offers[0] if offers else None
            if isinstance(offers, dict) and offers.get("price") is not None:
                out["regular"] = out["current"] = money(offers["price"])
                out["title"] = out["title"] or d.get("name")
                out["strategy"] = "json-ld"
                break
    # Strategy 3: release date shown as text ("Release: 9/8/2026" - month/day ambiguous, ISO preferred)
    if out["release_date"] is None:
        m = re.search(r'"releaseDate"\s*:\s*"(\d{4}-\d{2}-\d{2})', page)
        if m:
            out["release_date"] = m.group(1)
    return out


def _ms_to_date(ms):
    try:
        return dt.datetime.fromtimestamp(int(ms) / 1000, dt.timezone.utc).date().isoformat()
    except (TypeError, ValueError):
        return None


def is_standard_edition(edition: str | None) -> bool:
    return not edition or not re.search(r"deluxe|ultimate|gold|premium|collector|complete|royal|digital deluxe", edition, re.I)
