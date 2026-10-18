"""Shared paths, rules, enums and helpers. Standard library only (Python 3.13 on macOS)."""
from __future__ import annotations

import datetime as dt
import gzip
import hashlib
import json
import os
import random
import re
import time
import unicodedata
import urllib.error
import urllib.request
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
PROPOSALS = ROOT / "proposals"
RUN = ROOT / ".run"
CACHE = RUN / "cache"
LOGS = ROOT / "logs"

GAMES = DATA / "games.json"
PRICES = DATA / "prices.jsonl"          # append-only: one line per observed price change
CHECKS = DATA / "checks.jsonl"          # append-only: one line per external check
SALES = DATA / "sales.json"             # open + recently closed sales (derived from prices)
WISHLIST = DATA / "wishlist.json"
EVENTS = DATA / "events.json"           # store-wide sale calendar (curated + agent-proposed)
SEED_OBS = DATA / "seed_observations.json"  # historical sale prices researched before tracking began
STATS = DATA / "stats.json"             # derived, for the Statistics tab
META = DATA / "meta.json"
NOTIFY_STATE = RUN / "notify_state.json"

TZ = ZoneInfo("America/Toronto")

# ---------------------------------------------------------------- rules
SCOPE_YEARS = {2025, 2026}
MIN_SCORE = 70
SCORE_LOCK_DAYS = 30          # score keeps updating until this many days after release, then locks
WAIT_DAYS = 30                # unscored releases leave "Waiting for Scores" after this many days
ALERT_PCT = 25                # wishlist alert threshold (percent off the baseline price)

STATUSES = {"listed", "pending_score", "expired", "excluded", "review"}
CATEGORIES = {"game", "dlc", "sports", "vr", "f2p", "dup", "review"}
EXCLUDED_CATEGORIES = {"dlc": "DLC or expansion that needs the base game",
                       "sports": "Sports game",
                       "vr": "PS VR2-only game",
                       "f2p": "Free-to-play game",
                       "dup": "Re-release, edition or episode of a game already tracked"}
SCALES = {"AAA", "AA", "Indie"}
PHYSICAL = {"Yes", "No", "Unverified"}
FORMATS = {"digital", "disc"}
DIGITAL_STORE = "PlayStation Store"
DISC_STORES = ["Best Buy", "Walmart", "EB Games", "Video Games Plus", "PNP Games"]
SOURCES = {"migration", "rebuild", "agent", "manual"}

ID_RE = re.compile(r"^PS5-\d{4}$")
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


# ---------------------------------------------------------------- time
def now() -> dt.datetime:
    return dt.datetime.now(TZ).replace(microsecond=0)


def today() -> str:
    return now().date().isoformat()


def iso_now() -> str:
    return now().isoformat()


def parse_date(s: str) -> dt.date:
    return dt.date.fromisoformat(s[:10])


def days_between(a: str, b: str) -> int:
    return (parse_date(b) - parse_date(a)).days


# ---------------------------------------------------------------- json io
def load_json(path: Path, default=None):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return default


def save_json(path: Path, obj) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=1, sort_keys=False)
        f.write("\n")
    os.replace(tmp, path)


def append_jsonl(path: Path, rows) -> None:
    rows = list(rows)
    if not rows:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False, sort_keys=True) + "\n")


def read_jsonl(path: Path) -> list[dict]:
    out = []
    try:
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    out.append(json.loads(line))
    except FileNotFoundError:
        pass
    return out


def load_games() -> list[dict]:
    return load_json(GAMES, [])


def save_games(games: list[dict]) -> None:
    games.sort(key=lambda g: g["id"])
    save_json(GAMES, games)


# ---------------------------------------------------------------- titles
def norm_title(t: str) -> str:
    """Normalised key for de-duplication: case, accents, punctuation, edition noise removed."""
    t = unicodedata.normalize("NFKD", t).encode("ascii", "ignore").decode()
    t = t.lower().replace("&", " and ")
    t = re.sub(r"\b(the|a|an)\b", " ", t)
    t = re.sub(r"\b(ps5|playstation 5|standard edition)\b", " ", t)
    t = re.sub(r"[^a-z0-9]+", " ", t)
    return re.sub(r"\s+", " ", t).strip()


def metacritic_slug(title: str) -> str:
    t = unicodedata.normalize("NFKD", title).encode("ascii", "ignore").decode().lower()
    t = t.replace("&", "").replace("'", "").replace("'", "")
    t = re.sub(r"[^a-z0-9]+", "-", t)
    return t.strip("-")


def next_id(games: list[dict]) -> str:
    n = max([int(g["id"][4:]) for g in games] + [0]) + 1
    return f"PS5-{n:04d}"


def headline_score(g: dict):
    """The single score shown on the dashboard: Metacritic PS5, else the alternative aggregate."""
    mc = (g.get("metacritic") or {}).get("score")
    if mc is not None:
        return mc
    return (g.get("alt_score") or {}).get("score")


# ---------------------------------------------------------------- config
def load_config() -> dict:
    cfg = {}
    for path in (ROOT / "config.env",):
        if path.exists():
            for line in path.read_text().splitlines():
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    cfg[k.strip()] = v.strip().strip('"').strip("'")
    cfg.update({k: v for k, v in os.environ.items() if k.startswith(("NTFY_", "DASHBOARD_", "GITHUB_", "CLAUDE_", "FETCH_", "WALMART_"))})
    return cfg


# ---------------------------------------------------------------- polite fetching
USER_AGENT = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
              "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36")
_last_hit: dict[str, float] = {}


class FetchError(Exception):
    def __init__(self, url, status, reason, blocked=False):
        super().__init__(f"{status} {reason} {url}")
        self.url, self.status, self.reason, self.blocked = url, status, reason, blocked


BLOCK_MARKERS = ("px-captcha", "Robot or human", "Access Denied", "cf-chl-", "Attention Required!",
                 "Please verify you are a human", "/_Incapsula_Resource", "perimeterx")


def fetch(url: str, *, min_delay: float = 3.0, max_delay: float = 7.0, cache_hours: float = 20,
          accept: str = "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
          headers: dict | None = None, timeout: int = 30) -> str:
    """GET a page politely: per-host random pause, one attempt, on-disk cache, block detection.

    Pauses are random between min_delay and max_delay seconds per host, so requests are slow and
    spread out. No fingerprint spoofing, proxy rotation or CAPTCHA solving: a blocked page raises
    FetchError(blocked=True) and the caller falls back to another source.
    """
    CACHE.mkdir(parents=True, exist_ok=True)
    key = hashlib.sha1(url.encode()).hexdigest()
    cpath = CACHE / f"{key}.html"
    if cache_hours and os.environ.get("FETCH_NO_CACHE") != "1" and cpath.exists() and time.time() - cpath.stat().st_mtime < cache_hours * 3600:
        return cpath.read_text(encoding="utf-8", errors="replace")

    host = urllib.request.urlparse(url).netloc
    wait = random.uniform(min_delay, max_delay) - (time.time() - _last_hit.get(host, 0))
    if wait > 0 and os.environ.get("FETCH_NO_SLEEP") != "1":
        time.sleep(wait)
    req = urllib.request.Request(url, headers={
        "User-Agent": USER_AGENT, "Accept": accept, "Accept-Language": "en-CA,en;q=0.9",
        "Accept-Encoding": "gzip", **(headers or {})})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read()
            if resp.headers.get("Content-Encoding") == "gzip":
                raw = gzip.decompress(raw)
            body = raw.decode(resp.headers.get_content_charset() or "utf-8", errors="replace")
    except urllib.error.HTTPError as e:
        _last_hit[host] = time.time()
        body = ""
        try:
            body = e.read().decode("utf-8", errors="replace")
        except Exception:
            pass
        blocked = e.code in (401, 403, 412, 429, 503) or any(m in body for m in BLOCK_MARKERS)
        raise FetchError(url, e.code, e.reason, blocked) from None
    except (urllib.error.URLError, TimeoutError) as e:
        _last_hit[host] = time.time()
        raise FetchError(url, 0, str(e)) from None
    _last_hit[host] = time.time()
    if any(m in body[:20000] for m in BLOCK_MARKERS):
        raise FetchError(url, 200, "bot challenge page", blocked=True)
    cpath.write_text(body, encoding="utf-8")
    return body


def cache_path(url: str) -> Path:
    return CACHE / f"{hashlib.sha1(url.encode()).hexdigest()}.html"


def fetch_json(url: str, **kw):
    return json.loads(fetch(url, accept="application/json", **kw))


# ---------------------------------------------------------------- html helpers
def json_ld(html: str) -> list:
    out = []
    for m in re.finditer(r'<script[^>]+type="application/ld\+json"[^>]*>(.*?)</script>', html, re.S | re.I):
        try:
            data = json.loads(m.group(1).strip())
        except json.JSONDecodeError:
            continue
        out.extend(data if isinstance(data, list) else [data])
    return out


def script_json(html: str, script_id: str):
    m = re.search(r'<script[^>]+id="%s"[^>]*>(.*?)</script>' % re.escape(script_id), html, re.S)
    if not m:
        return None
    try:
        return json.loads(m.group(1))
    except json.JSONDecodeError:
        return None


def money(s) -> float | None:
    """'$1,089.99' / 'CA$ 89,99' / 89.99 -> 89.99"""
    if s is None:
        return None
    if isinstance(s, (int, float)):
        return round(float(s), 2)
    m = re.search(r"(\d[\d,\s]*)(?:[.,](\d{2}))?\b", str(s).replace(" ", " "))
    if not m:
        return None
    whole = re.sub(r"[,\s]", "", m.group(1))
    return round(float(f"{whole}.{m.group(2) or '00'}"), 2)


def log_check(source: str, game_id: str | None, url: str, ok: bool, detail: dict | None = None) -> dict:
    return {"at": iso_now(), "source": source, "game_id": game_id, "url": url, "ok": ok, **(detail or {})}
