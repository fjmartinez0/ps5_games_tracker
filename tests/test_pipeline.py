"""End-to-end on a temporary copy of the repo: sample pages are placed in the fetch cache, so the real
scripts run without network access. Covers parsers, merger rules, prices -> sales -> alerts, stats,
wishlist and validation."""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
FIX = Path(__file__).resolve().parent / "fixtures"


class Pipeline(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp())
        shutil.copytree(REPO, cls.tmp / "repo", ignore=shutil.ignore_patterns(".run", "logs", ".git", "__pycache__", "config.env"))
        cls.root = cls.tmp / "repo"
        sys.path.insert(0, str(cls.root / "scripts"))
        import common
        cls.common = common
        cls.real_cache = common.CACHE
        common.CACHE = cls.root / ".run" / "cache"          # never touch the real tracker's page cache
        cls.today = common.today()
        cls.env = {**{k: v for k, v in os.environ.items() if not k.startswith("NTFY_")}, "FETCH_NO_SLEEP": "1"}  # never send real alerts

    @classmethod
    def tearDownClass(cls):
        cls.common.CACHE = cls.real_cache
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def run_script(self, *args, ok=True):
        p = subprocess.run([sys.executable, *args], cwd=self.root, env=self.env, capture_output=True, text=True)
        if ok and p.returncode != 0:
            self.fail(f"{args} failed:\n{p.stdout}\n{p.stderr}")
        return p

    def cache(self, url, fixture):
        """Put a sample page where fetch() looks first - the temp repo's cache only."""
        d = self.root / ".run" / "cache"
        d.mkdir(parents=True, exist_ok=True)
        shutil.copy(FIX / fixture, d / (__import__("hashlib").sha1(url.encode()).hexdigest() + ".html"))

    def games(self):
        return json.loads((self.root / "data/games.json").read_text())

    def test_1_parsers(self):
        os.chdir(self.root)
        from sources import deku, metacritic, ps_store
        u = "https://store.playstation.com/en-ca/product/TEST-SALE"
        self.cache(u, "ps_store_sale.html")
        r = ps_store.read(u)
        self.assertEqual((r["regular"], r["current"], r["on_sale"], r["release_date"]), (39.99, 27.99, True, "2026-04-14"))
        u2 = "https://store.playstation.com/en-ca/product/TEST-PLUS"
        self.cache(u2, "ps_store_plus_only.html")
        r = ps_store.read(u2)
        self.assertEqual((r["current"], r["on_sale"], r["plus_only_discount"]), (39.99, False, True))
        u3 = deku.item_url("hades-ii")
        self.cache(u3, "deku_item.html")
        d = deku.read(u3)
        self.assertTrue(d["is_ps5"])
        self.assertIn({"store": "Best Buy", "format": "disc", "price": 29.99, "was": None}, d["offers"])
        self.assertNotIn("Video Games Plus", {o["store"] for o in d["offers"]})            # price 0 = not available
        self.assertEqual(d["lowest"], {"digital": 35.99, "disc": 44.99})                   # from history, PS5 only
        self.assertEqual(d["ps_store_url"], "https://store.playstation.com/en-ca/product/UP0000-PPSA00000_00-HADES2GAME000000")
        self.assertEqual(sorted(d["history"]), [("digital", "PlayStation Store"), ("disc", "Best Buy"), ("disc", "PNP Games")])
        self.cache(metacritic.BROWSE.format(sort="metascore", y=2026, p=1), "metacritic_browse.html")
        items = metacritic.browse(2026, 1)
        self.assertEqual([(i["title"], i["score"], i["release_date"]) for i in items][:2],
                         [("Hades II", 94, "2026-04-14"), ("Brand New Game", 81, "2026-10-16")])

    def test_2_merger_rules(self):
        prop = {"date": self.today, "searches": ["a", "b", "c"], "new_games": [
            {"title": "Brand New Game", "category": "game", "scale": "Indie", "genre": "Roguelite", "release_date": self.today,
             "ps_store_url": "https://store.playstation.com/en-ca/concept/12345", "metacritic_url": None,
             "deku_url": "https://www.dekudeals.com/items/brand-new-game", "evidence": ["https://example.com/a"]},
            {"title": "Some DLC", "category": "dlc", "scale": "AA", "release_date": self.today, "evidence": ["https://x"]},
            {"title": "Fake Store Link", "category": "game", "scale": "AA", "release_date": self.today,
             "ps_store_url": "https://store.playstation.com/en-us/concept/1", "evidence": ["https://x"]},
            {"title": "From 2024", "category": "game", "scale": "AA", "release_date": "2024-05-01", "evidence": ["https://x"]},
            {"title": "No Evidence", "category": "game", "scale": "AA", "release_date": self.today},
            {"title": "Hades II", "category": "game", "scale": "Indie", "evidence": ["https://x"],
             "ps_store_url": "https://store.playstation.com/en-ca/product/TEST-SALE"}],
            "flyer_prices": [{"id": "PS5-0001", "store": "Walmart", "price": 49.99, "regular": 89.99, "valid_from": self.today,
                              "valid_to": "2099-01-01", "evidence": ["https://flyer"]},
                             {"id": "PS5-0001", "store": "Costco", "price": 1, "valid_from": self.today, "evidence": ["x"]}],
            "events": [{"name": "Black Friday 2026", "start": "2026-11-20", "end": "2026-12-03", "formats": ["digital", "disc"],
                        "special": True, "evidence": ["https://blog.playstation.com/x"]}]}
        (self.root / "proposals").mkdir(exist_ok=True)
        (self.root / f"proposals/{self.today}.json").write_text(json.dumps(prop))
        out = self.run_script("scripts/apply_proposals.py").stdout
        g = {x["title"]: x for x in self.games()}
        self.assertEqual(g["Brand New Game"]["status"], "pending_score")          # never listed directly
        self.assertEqual(g["Some DLC"]["status"], "excluded")
        for t in ("Fake Store Link", "From 2024", "No Evidence"):
            self.assertNotIn(t, g)
        self.assertEqual(g["Hades II"]["ps_store"]["url"], "https://store.playstation.com/en-ca/product/TEST-SALE")
        self.assertIn("flyer price incomplete", out)
        ev = json.loads((self.root / "data/events.json").read_text())
        bf = [e for e in ev if e["name"] == "Black Friday 2026"]
        self.assertEqual((len(bf), bf[0]["expected"], bf[0]["end"]), (1, False, "2026-12-03"))  # replaced the expected one

    def test_3_prices_sales_alerts_stats(self):
        games = self.games()
        hades = next(g for g in games if g["title"] == "Hades II")
        hades["disc"]["deku_url"] = "https://www.dekudeals.com/items/hades-ii?format=all&country=ca&platform=all"
        (self.root / "data/games.json").write_text(json.dumps(games))
        self.run_script("scripts/wishlist.py", "add", hades["id"])
        self.run_script("scripts/prices.py", "--only", hades["id"], "--all-disc")
        sales = json.loads((self.root / "data/sales.json").read_text())
        mine = [s for s in sales["open"] if s["game_id"] == hades["id"]]
        self.assertEqual(sorted((s["format"], s["store"], s["pct"]) for s in mine),
                         [("digital", "PlayStation Store", 30), ("disc", "Best Buy", 40)])
        self.assertNotIn("Amazon.ca", {s["store"] for s in mine})                 # not one of the 5 disc stores
        g = next(x for x in self.games() if x["id"] == hades["id"])
        self.assertEqual((g["physical"], g["disc"]["msrp"], g["disc"]["msrp_source"]), ("Yes", 49.99, "history"))
        hist = [json.loads(x) for x in (self.root / "data/prices.jsonl").read_text().splitlines() if '"deku-history"' in x]
        self.assertEqual(len(hist), 7)                                   # change points only, PS5 stores only
        out = self.run_script("scripts/notify.py").stdout                       # no topics configured: prints
        self.assertIn("2 price alerts", out)                             # digital 30% off; disc 40% off + new low
        self.assertIn("Hades II disc at Best Buy", out)
        out = self.run_script("scripts/notify.py").stdout
        self.assertIn("0 price alerts", out)                                     # once per sale
        self.run_script("scripts/build_stats.py")
        stats = json.loads((self.root / "data/stats.json").read_text())
        self.assertIn("on_sale", stats["games"][hades["id"]]["next_expected"])

    def test_3b_recheck_game_without_metacritic_entry(self):
        games = self.games()
        legacy = next(g for g in games if g.get("metacritic") is None and g["status"] == "listed")
        url = __import__("sources.metacritic", fromlist=["x"]).game_url(legacy["title"])
        self.cache(url, "live/metacritic_browse_2026.html")         # a page with no PS5 score on it
        legacy["first_seen"] = self.today                            # so --new-only picks it up
        legacy["release_date"] = None                                # start without a date
        (self.root / "data/games.json").write_text(json.dumps(games))
        out = self.run_script("scripts/recheck.py", "--new-only").stdout       # used to crash here
        self.assertIn("recheck:", out)
        g = next(x for x in self.games() if x["id"] == legacy["id"])
        self.assertIsNone(g["release_date"])        # never borrow another game's date from the page

    def test_5_real_cache_untouched(self):
        real = REPO / ".run" / "cache"
        fake = [p for p in real.glob("*.html") if "PPSA00000" in p.read_text(errors="ignore") or "Brand New Game" in p.read_text(errors="ignore")] if real.exists() else []
        self.assertEqual(fake, [], "test sample pages found in the real cache")

    def test_4_wishlist_issue_and_validate(self):
        p = self.run_script("scripts/wishlist.py", "--issue-title", "wishlist: remove PS5-0001")
        self.assertIn("remove", p.stdout)
        p = self.run_script("scripts/wishlist.py", "--issue-title", "please add everything", ok=False)
        self.assertEqual(p.returncode, 2)
        self.run_script("scripts/validate.py")
        games = self.games()
        games[0]["status"] = "listed"
        games[0]["metacritic"] = {"score": 50, "verified": True}
        games[0]["alt_score"] = None
        (self.root / "data/games.json").write_text(json.dumps(games))
        p = self.run_script("scripts/validate.py", ok=False)
        self.assertEqual(p.returncode, 1)
        self.assertIn("listed with score 50", p.stdout)


if __name__ == "__main__":
    unittest.main()
