import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
from rules import alert_due, close_expired, disc_msrp, lifecycle, score_update, set_release_date, update_sale  # noqa: E402


def game(**kw):
    g = {"id": "PS5-0001", "title": "T", "status": "pending_score", "release_date": "2026-10-01",
         "metacritic": {"score": None, "verified": False}, "alt_score": None, "score_locked": False}
    g.update(kw)
    return g


class Lifecycle(unittest.TestCase):
    def test_promotes_at_70(self):
        g = game()
        score_update(g, 74, 12, "u", "2026-10-05")
        self.assertEqual(lifecycle(g, "2026-10-05"), "listed")
        self.assertEqual(g["listed_on"], "2026-10-05")

    def test_stays_waiting_below_70_then_expires(self):
        g = game()
        score_update(g, 65, 12, "u", "2026-10-05")
        self.assertIsNone(lifecycle(g, "2026-10-05"))
        self.assertEqual(lifecycle(g, "2026-10-31"), "expired")

    def test_future_release_keeps_waiting(self):
        g = game(release_date="2026-12-01")
        self.assertIsNone(lifecycle(g, "2026-11-20"))
        self.assertEqual(g["status"], "pending_score")

    def test_score_locks_after_30_days_and_stops_changing(self):
        g = game(status="listed")
        score_update(g, 80, 30, "u", "2026-10-10")
        self.assertEqual(lifecycle(g, "2026-11-01"), "score locked")
        self.assertEqual(score_update(g, 60, 40, "u", "2026-11-02"), [])
        self.assertEqual(g["metacritic"]["score"], 80)
        self.assertEqual(g["status"], "listed")            # once on, always on


class ReleaseDates(unittest.TestCase):
    def test_year_follows_date_and_out_of_scope_goes_to_review(self):
        g = game(status="listed", release_date=None, ps5_year=2025)
        self.assertIn("year 2025 -> 2026", set_release_date(g, "2026-03-31"))
        self.assertEqual((g["ps5_year"], g["status"]), (2026, "listed"))
        g = game(status="listed", release_date=None, ps5_year=2026)
        set_release_date(g, "2024-02-01")
        self.assertEqual(g["status"], "review")
        self.assertIsNone(set_release_date(g, "2025-01-01"))          # never overwrites a known date


class Sales(unittest.TestCase):
    def test_open_deepen_close(self):
        s = {"open": [], "closed": []}
        r = update_sale(s, "PS5-0001", "digital", "PlayStation Store", 59.99, 79.99, 79.99, "2026-11-20")
        self.assertEqual((r["change"], r["pct"]), ("opened", 25))
        self.assertIsNone(update_sale(s, "PS5-0001", "digital", "PlayStation Store", 59.99, 79.99, 79.99, "2026-11-21"))
        r = update_sale(s, "PS5-0001", "digital", "PlayStation Store", 39.99, 79.99, 79.99, "2026-11-22")
        self.assertEqual((r["change"], r["pct"], r["lowest_before"]), ("deeper", 50, 59.99))
        self.assertIsNone(update_sale(s, "PS5-0001", "digital", "PlayStation Store", 79.99, 79.99, 39.99, "2026-12-01"))
        self.assertEqual((len(s["open"]), len(s["closed"])), (0, 1))

    def test_alert_rules(self):
        row = {"pct": 20, "price": 63.99, "lowest_before": 70.0, "alerted": False}
        self.assertTrue(alert_due(row, True))                # new lowest price
        self.assertFalse(alert_due(row, False))              # not on the wishlist
        row = {"pct": 20, "price": 63.99, "lowest_before": 59.99, "alerted": False}
        self.assertFalse(alert_due(row, True))               # under 25% and not a new low
        self.assertTrue(alert_due({**row, "pct": 25}, True))
        self.assertFalse(alert_due({**row, "pct": 40, "alerted": True}, True))

    def test_disc_msrp_ignores_one_inflated_store(self):
        self.assertEqual(disc_msrp([89.99, 89.99, 99.99, 89.96]), 89.99)

    def test_flyer_sale_closes_after_end(self):
        s = {"open": [], "closed": []}
        update_sale(s, "PS5-0001", "disc", "Walmart", 49.99, 89.99, None, "2026-11-20", "2026-11-27")
        close_expired(s, "2026-11-28")
        self.assertEqual(len(s["closed"]), 1)


if __name__ == "__main__":
    unittest.main()
