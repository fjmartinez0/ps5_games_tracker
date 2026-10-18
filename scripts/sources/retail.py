"""EB Games and Walmart Canada product pages: current price of a new PS5 disc copy.

Polite access only: one request per game per check, random pauses (common.fetch), browser user agent,
on-disk cache. No fingerprint spoofing, proxy rotation or CAPTCHA solving. If a store answers with a
bot challenge, the store is marked blocked for 7 days and the weekly agent run collects its prices
from published flyers instead.
"""
import datetime as dt
import re

from common import META, FetchError, fetch, json_ld, load_json, money, save_json, today
from sources.textutil import all_json_blobs, walk

BLOCK_DAYS = 7


def store_blocked(store: str) -> bool:
    until = (load_json(META, {}).get("sources", {}).get(store, {}) or {}).get("blocked_until")
    return bool(until and until >= today())


def mark_blocked(store: str, reason: str) -> None:
    meta = load_json(META, {})
    until = (dt.date.fromisoformat(today()) + dt.timedelta(days=BLOCK_DAYS)).isoformat()
    meta.setdefault("sources", {})[store] = {"blocked_until": until, "reason": reason, "since": today()}
    save_json(META, meta)


def read(store: str, url: str) -> dict:
    """Return {store, price, regular, in_stock}. Raises FetchError (blocked=True on bot challenge)."""
    if store_blocked(store):
        raise FetchError(url, 0, f"{store} marked blocked", blocked=True)
    try:
        page = fetch(url, min_delay=6, max_delay=14)
    except FetchError as e:
        if e.blocked:
            mark_blocked(store, f"{e.status} {e.reason}")
        raise
    out = {"store": store, "url": url, "price": None, "regular": None, "in_stock": None, "strategy": None}
    # Strategy 1: Next.js data (Walmart) - priceInfo.currentPrice / wasPrice
    for blob in all_json_blobs(page):
        for d in walk(blob):
            pi = d.get("priceInfo") if isinstance(d.get("priceInfo"), dict) else None
            if pi:
                cur = pi.get("currentPrice") or {}
                was = pi.get("wasPrice") or {}
                out["price"] = money(cur.get("price") if isinstance(cur, dict) else cur)
                out["regular"] = money(was.get("price") if isinstance(was, dict) else was) or out["price"]
                out["strategy"] = "next-data"
                break
        if out["price"] is not None:
            break
    # Strategy 2: JSON-LD Product offers (EB Games and most retailers)
    if out["price"] is None:
        for d in json_ld(page):
            if not isinstance(d, dict):
                continue
            offers = d.get("offers")
            offers = offers[0] if isinstance(offers, list) and offers else offers
            if isinstance(offers, dict) and offers.get("price") is not None:
                out["price"] = out["regular"] = money(offers["price"])
                out["in_stock"] = "InStock" in str(offers.get("availability", ""))
                out["strategy"] = "json-ld"
                break
    # Strategy 3: visible "was" price
    if out["price"] is not None:
        m = re.search(r"(?:Was|Reg\.?|Regular price)\s*:?\s*\$\s?(\d[\d,]*\.\d{2})", page, re.I)
        if m and money(m.group(1)) > out["price"]:
            out["regular"] = money(m.group(1))
    return out
