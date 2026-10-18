"""Parsers against real pages saved by scripts/source_test.py on the Mac (2026-10-18)."""
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

LIVE = Path(__file__).resolve().parent / "fixtures" / "live"
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import common  # noqa: E402
from sources import deku, metacritic, ps_store  # noqa: E402


class LivePages(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp())
        cls.orig = common.CACHE
        common.CACHE = cls.tmp
        os.environ["FETCH_NO_SLEEP"] = "1"

    @classmethod
    def tearDownClass(cls):
        common.CACHE = cls.orig
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def put(self, url, name):
        shutil.copy(LIVE / name, common.cache_path(url))

    def test_metacritic_ps5_score_not_pc(self):
        for slug, f, score, n, date in (("skate-story", "metacritic_skate-story.html", 80, 29, "2025-12-08"),
                                        ("octopath-traveler-0", "metacritic_octopath-0.html", 84, 41, "2025-12-04")):
            u = metacritic.game_url(slug)
            self.put(u, f)
            r = metacritic.read_score(u)
            self.assertEqual((r["score"], r["reviews"], r["release_date"]), (score, n, date))

    def test_metacritic_browse(self):
        u = metacritic.BROWSE.format(sort="metascore", y=2026, p=1)
        self.put(u, "metacritic_browse_2026.html")
        rows = metacritic.browse(2026, 1)
        self.assertEqual(len(rows), 24)
        self.assertEqual(rows[0], {"title": "Hades II", "slug": "hades-ii", "release_date": "2026-04-14", "score": 94})
        self.assertTrue(all(r["score"] >= 85 for r in rows))

    def test_deku_multi_platform_history(self):
        u = deku.item_url("kingdom-come-deliverance-ii")
        self.put(u, "deku_kingdom-come-deliverance-ii.html")
        d = deku.read(u)
        self.assertTrue(d["is_ps5"])
        self.assertEqual({(o["store"], o["format"]) for o in d["offers"]},
                         {("PlayStation Store", "digital"), ("Amazon.ca", "disc"), ("Best Buy", "disc"), ("Video Games Plus", "disc")})
        self.assertEqual(set(d["history"]), {("digital", "PlayStation Store"), ("disc", "Best Buy"), ("disc", "Video Games Plus")})
        self.assertEqual(d["lowest"]["digital"], 32.72)
        self.assertEqual(sorted(d["history"][("digital", "PlayStation Store")])[0], ("2024-08-20", 93.49))
        self.assertTrue(d["ps_store_url"].endswith("UP2047-PPSA21705_00-KCD2MAINGAMEDSUS"))

    def test_deku_single_platform_history(self):
        u = deku.item_url("ghost-of-yotei")
        self.put(u, "deku_ghost-of-yotei.html")
        d = deku.read(u)
        self.assertEqual([(o["store"], o["price"]) for o in d["offers"]], [("PNP Games", 69.99)])
        self.assertIn(("disc", "Best Buy"), d["history"])
        self.assertIn(("digital", "PlayStation Store"), d["history"])
        self.assertEqual(d["page_title"], "Ghost of Yōtei")

    def test_ps_store(self):
        u = "https://store.playstation.com/en-ca/concept/10019219"
        self.put(u, "ps_store_3.html")
        r = ps_store.read(u)
        self.assertEqual((r["regular"], r["release_date"]), (47.99, "2026-09-08"))


if __name__ == "__main__":
    unittest.main()
