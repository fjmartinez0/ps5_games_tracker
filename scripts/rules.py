"""Pure decision rules (no I/O) so they can be unit-tested. The AI never decides any of these."""
from __future__ import annotations

import re

from common import ALERT_PCT, MIN_SCORE, SCOPE_YEARS, SCORE_LOCK_DAYS, WAIT_DAYS, days_between


# ---------------------------------------------------------------- catalog lifecycle
def score_update(g: dict, score: int | None, reviews: int | None, url: str, on: str) -> list[str]:
    """Apply a freshly read Metacritic PS5 score. Returns a list of human-readable changes."""
    changes = []
    if score is None:
        return changes
    mc = g.get("metacritic") or {}
    if g.get("score_locked") and mc.get("verified"):
        return changes                                   # locked scores never change
    if mc.get("score") != score:
        changes.append(f"score {mc.get('score')} -> {score}")
    g["metacritic"] = {**mc, "score": score, "reviews": reviews, "url": url, "checked_at": on, "verified": True}
    g["verified"] = True
    return changes


def lifecycle(g: dict, on: str) -> str | None:
    """Move a game between statuses based on its score and age. Returns the change, if any."""
    score = (g.get("metacritic") or {}).get("score")
    if score is None:
        score = (g.get("alt_score") or {}).get("score") if (g.get("alt_score") or {}).get("verified") else None
    rel = g.get("release_date")
    age = days_between(rel, on) if rel else None
    if g["status"] == "pending_score":
        if rel and rel > on:
            return None                                  # not released yet: keep waiting
        if score is not None and score >= MIN_SCORE:
            g["status"], g["listed_on"] = "listed", on
            return "listed"
        start = rel or g.get("first_seen") or on
        if days_between(start, on) >= WAIT_DAYS:
            g["status"] = "expired"
            return "expired"
    if g["status"] == "listed" and not g.get("score_locked") and age is not None and age >= SCORE_LOCK_DAYS:
        g["score_locked"], g["score_locked_at"] = True, on
        return "score locked"
    return None


def set_release_date(g: dict, date: str | None) -> str | None:
    """Fill a missing release date and keep ps5_year in step with it. A date outside 2025-2026 sends a
    listed or waiting game to review instead of breaking validation. Returns the change, if any."""
    if not date or g.get("release_date") or not re.match(r"^\d{4}-\d{2}-\d{2}$", date):
        return None
    g["release_date"], year = date, int(date[:4])
    change = f"release date {date}"
    if year != g.get("ps5_year"):
        change += f" (year {g.get('ps5_year')} -> {year})"
        g["ps5_year"] = year
    if year not in SCOPE_YEARS and g.get("status") in ("listed", "pending_score"):
        g["status"], g["review_note"] = "review", f"PS5 release date {date} is outside 2025-2026"
        change += " - moved to review"
    return change


def in_scope_year(release_date: str | None) -> bool:
    return release_date is None or int(release_date[:4]) in SCOPE_YEARS


# ---------------------------------------------------------------- prices and sales
def pct_off(price: float, baseline: float) -> int:
    return round((1 - price / baseline) * 100) if baseline else 0


def disc_msrp(regular_prices: list[float]) -> float | None:
    """Most common launch price across stores (ties -> the lower one), so one store's inflated
    'regular' label can't make a discount look bigger."""
    vals = [round(p, 2) for p in regular_prices if p]
    if not vals:
        return None
    return sorted(set(vals), key=lambda v: (-vals.count(v), v))[0]


def update_sale(sales: dict, game_id: str, fmt: str, store: str, price: float, baseline: float,
                lowest_before: float | None, on: str, sale_end: str | None = None, regular_now: float | None = None) -> dict | None:
    """Open, deepen or close a sale for one (game, format, store). Mutates `sales`.
    Returns the sale row when something alert-worthy may have happened today (opened or deeper)."""
    key = (game_id, fmt, store)
    open_rows = sales.setdefault("open", [])
    row = next((r for r in open_rows if (r["game_id"], r["format"], r["store"]) == key), None)
    price_cut = regular_now is not None and baseline and regular_now < baseline - 0.01 and abs(price - regular_now) < 0.01
    on_sale = price < baseline - 0.01
    if not on_sale:
        if row:
            row["ended"] = on
            open_rows.remove(row)
            sales.setdefault("closed", []).append(row)
        return None
    if row is None:
        row = {"game_id": game_id, "format": fmt, "store": store, "baseline": baseline, "price": price,
               "pct": pct_off(price, baseline), "start": on, "end": sale_end, "lowest_before": lowest_before,
               "kind": "price_cut" if price_cut else "sale", "changed_on": on, "change": "opened", "alerted": False}
        open_rows.append(row)
        return row
    if price < row["price"] - 0.01:
        row.update(price=price, pct=pct_off(price, baseline), changed_on=on, change="deeper", end=sale_end or row.get("end"),
                   lowest_before=min(x for x in (row.get("lowest_before"), row["price"]) if x is not None), alerted=False)
        return row
    row["end"] = sale_end or row.get("end")
    return None


def alert_due(row: dict, wished: bool) -> bool:
    if not wished or row.get("alerted"):
        return False
    lowest = row.get("lowest_before")
    return row["pct"] >= ALERT_PCT or (lowest is not None and row["price"] < lowest - 0.01)


def prune_closed(sales: dict, on: str, keep_days: int = 60) -> None:
    sales["closed"] = [r for r in sales.get("closed", []) if days_between(r.get("ended", on), on) <= keep_days]


def close_expired(sales: dict, on: str) -> None:
    """Close sales whose stated end date has passed (flyer deals, PS Store sales with an end time)."""
    for r in list(sales.get("open", [])):
        if r.get("end") and r["end"] < on:
            r["ended"] = r["end"]
            sales["open"].remove(r)
            sales.setdefault("closed", []).append(r)
