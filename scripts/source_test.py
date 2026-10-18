"""Run this FIRST on the Mac: checks every data source from your own connection and saves raw pages.

  python3 scripts/source_test.py

Prints PASS / FAIL per source and writes .run/source_test_report.md plus raw pages in .run/samples/.
If anything fails, zip .run/samples and the report and send them back so the parsers can be fixed.
Takes about 3 minutes (requests are spaced out on purpose).
"""
import os
import shutil
import traceback

os.environ["FETCH_NO_CACHE"] = "1"

from common import RUN, FetchError, cache_path, fetch, load_games  # noqa: E402
from sources import deku, metacritic, opencritic, ps_store, retail  # noqa: E402

SAMPLES = RUN / "samples"
results = []


def run(name, url, fn, expect):
    print(f"… {name}")
    try:
        out = fn()
        ok, detail = expect(out)
        status = "PASS" if ok else "FAIL"
    except FetchError as e:
        out, status, detail = None, "BLOCKED" if e.blocked else "FAIL", str(e)
    except Exception:
        out, status, detail = None, "ERROR", traceback.format_exc(limit=2)
    src = cache_path(url)
    if src.exists():
        SAMPLES.mkdir(parents=True, exist_ok=True)
        shutil.copy(src, SAMPLES / f"{name.replace(' ', '_').replace('/', '-')}.html")
    results.append((name, status, detail, url))
    print(f"  {status}: {detail}")


def main():
    if SAMPLES.exists():
        shutil.rmtree(SAMPLES)
    games = {g["title"]: g for g in load_games()}

    # PlayStation Store Canada
    ps_urls = [g["ps_store"]["url"] for g in games.values() if (g.get("ps_store") or {}).get("url")][:2]
    ps_urls.append("https://store.playstation.com/en-ca/concept/10019219")
    for i, u in enumerate(dict.fromkeys(ps_urls)):
        run(f"ps_store {i + 1}", u, lambda u=u: ps_store.read(u),
            lambda o: (o["regular"] is not None, f"regular={o['regular']} current={o['current']} release={o['release_date']} "
                                                 f"edition={o['edition']} via {o['strategy']}"))

    # Metacritic: PS5 score must differ from PC where they differ (Skate Story PS5 = 80)
    for name, slug, exp in (("metacritic skate-story", "skate-story", 80), ("metacritic octopath-0", "octopath-traveler-0", 84)):
        u = metacritic.game_url(slug)
        run(name, u, lambda u=u: metacritic.read_score(u),
            lambda o, exp=exp: (o["score"] == exp, f"score={o['score']} (expected {exp}) reviews={o['reviews']} via {o['strategy']}"))
    u = metacritic.BROWSE.format(sort="metascore", y=2026, p=1)
    run("metacritic browse 2026", u, lambda: metacritic.browse(2026, 1),
        lambda o: (len(o) >= 20 and any(x["title"] == "Hades II" for x in o),
                   f"{len(o)} rows; first: {o[:2]}"))

    # OpenCritic (free site data)
    run("opencritic search", f"{opencritic.API}/game/search?criteria=Clair%20Obscur", lambda: opencritic.search("Clair Obscur"),
        lambda o: (bool(o and o[0].get("id")), f"{o[:2]}"))

    # Deku Deals Canada (PS5 items; disc stores Best Buy / VGP / PNP)
    for slug in ("death-stranding-2", "ghost-of-yotei", "kingdom-come-deliverance-ii"):
        u = deku.item_url(slug)
        run(f"deku {slug}", u, lambda u=u: deku.read(u),
            lambda o: (o["is_ps5"] and bool(o["offers"]) and bool(o["history"]),
                       f"ps5={o['is_ps5']} offers={o['offers'][:4]} lowest={o['lowest']} history={sorted(o['history'])}"))

    # EB Games and Walmart: can we read a page at all?
    for store, u in (("EB Games", "https://www.ebgames.ca/SearchResult/QuickSearch?q=death+stranding+2"),
                     ("Walmart", "https://www.walmart.ca/en/search?q=death%20stranding%202%20ps5")):
        def probe(u=u, store=store):
            if retail.store_blocked(store):
                raise FetchError(u, 0, "marked blocked earlier", blocked=True)
            html = fetch(u, min_delay=6, max_delay=12, cache_hours=0)
            return {"bytes": len(html), "has_price": "$" in html, "has_ps5": "PS5" in html or "PlayStation 5" in html}
        run(f"{store.lower().replace(' ', '')} search", u, probe,
            lambda o: (o["has_price"] and o["has_ps5"], str(o)))

    lines = ["# Source test report", "", "| Source | Result | Detail |", "|---|---|---|"]
    for name, status, detail, url in results:
        lines.append(f"| {name} | {status} | {str(detail)[:300].replace('|', '/').replace(chr(10), ' ')} |")
    (RUN / "source_test_report.md").write_text("\n".join(lines) + "\n")
    expected_blocked = {"ebgames search", "walmart search"}             # known: these two block automated access
    passed = sum(1 for r in results if r[1] == "PASS" or (r[0] in expected_blocked and r[1] == "BLOCKED"))
    print(f"\n{passed}/{len(results)} passed (EB Games/Walmart blocked is expected; flyers cover them). Report: .run/source_test_report.md  Raw pages: .run/samples/")
    if passed < len(results):
        print("Send the report and a zip of .run/samples so the failing readers can be adjusted.")


if __name__ == "__main__":
    main()
