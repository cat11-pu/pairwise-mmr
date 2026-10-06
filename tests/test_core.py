"""Behaviour tests for the ranked-ladder rating kernel.

Run them from the project root:

    python3 -m unittest discover -s tests -v
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from mmr.core import (
    Ladder,
    clamp_rating,
    expected_score,
    streak_multiplier,
)


class ExpectedScoreTest(unittest.TestCase):
    def test_the_odds_follow_the_rating_gap(self):
        self.assertAlmostEqual(expected_score(1500.0, 1500.0), 0.5, places=9)
        self.assertAlmostEqual(expected_score(1600.0, 1400.0), 0.7597469, places=6)
        self.assertAlmostEqual(expected_score(1400.0, 1600.0), 0.2402531, places=6)
        self.assertAlmostEqual(
            expected_score(1830.0, 1210.0) + expected_score(1210.0, 1830.0),
            1.0,
            places=9,
        )

        ladder = Ladder()
        ladder.register("fav", 1600.0)
        ladder.register("dog", 1400.0)
        opener = ladder.record_match("fav", "dog", day=1, margin=1)
        self.assertAlmostEqual(opener.expected_winner, 0.7597469, places=6)
        self.assertAlmostEqual(opener.weight, 64.0, places=6)
        self.assertAlmostEqual(ladder.rating_of("fav"), 1615.7606, places=3)
        reply = ladder.record_match("dog", "fav", day=2, margin=1)
        self.assertAlmostEqual(reply.weight, 64.0, places=6)
        self.assertGreater(ladder.rating_of("dog"), 1384.2394)
        self.assertLess(ladder.rating_of("fav"), 1615.7606)


class MatchBalanceTest(unittest.TestCase):
    def test_a_settled_match_moves_both_sides_by_the_same_amount(self):
        ladder = Ladder()
        for name in ("alpha", "beta", "gamma", "delta", "epsilon", "zeta"):
            ladder.register(name, 1500.0, matches=25, last_day=0)

        even = ladder.record_match("alpha", "beta", day=1, margin=10)
        self.assertAlmostEqual(even.weight, 24.0, places=6)
        self.assertAlmostEqual(even.expected_winner, 0.5, places=9)
        self.assertAlmostEqual(even.pair_delta(), 0.0, places=9)
        self.assertAlmostEqual(even.winner_delta(), 15.0, places=6)
        self.assertAlmostEqual(even.loser_delta(), -15.0, places=6)
        self.assertAlmostEqual(ladder.rating_of("alpha"), 1515.0, places=6)
        self.assertAlmostEqual(ladder.rating_of("beta"), 1485.0, places=6)

        wide = ladder.record_match("gamma", "delta", day=1, margin=20)
        self.assertAlmostEqual(wide.pair_delta(), 0.0, places=9)
        self.assertAlmostEqual(wide.winner_delta(), 18.0, places=6)

        huge = ladder.record_match("epsilon", "zeta", day=1, margin=500)
        self.assertAlmostEqual(huge.pair_delta(), 0.0, places=9)
        self.assertAlmostEqual(huge.winner_delta(), 18.0, places=6)


class PlacementTest(unittest.TestCase):
    def test_the_placement_weight_holds_over_the_whole_placement_run(self):
        ladder = Ladder()
        ladder.register("rookie", 1500.0)
        ladder.register("mate", 1500.0)
        for day in range(1, 5):
            outcome = ladder.record_match("rookie", "mate", day=day, margin=1)
            self.assertAlmostEqual(outcome.weight, 64.0, places=6)
        self.assertEqual(ladder.matches_of("rookie"), 4)
        self.assertEqual(ladder.streak_of("rookie"), 4)
        self.assertEqual(ladder.streak_of("mate"), -4)

        for day in range(5, 11):
            outcome = ladder.record_match("rookie", "mate", day=day, margin=1)
            self.assertAlmostEqual(outcome.weight, 64.0, places=6)
        self.assertEqual(ladder.matches_of("rookie"), 10)
        self.assertEqual(ladder.matches_of("mate"), 10)

        settled = ladder.record_match("rookie", "mate", day=11, margin=1)
        self.assertAlmostEqual(settled.weight, 24.0, places=6)


class StreakTest(unittest.TestCase):
    def test_streaks_bend_the_weight_in_both_directions(self):
        ladder = Ladder()
        ladder.register("hot", 1500.0, matches=40, streak=4, last_day=0)
        ladder.register("calm", 1500.0, matches=40, streak=0, last_day=0)
        ladder.register("cold", 1500.0, matches=40, streak=-4, last_day=0)
        ladder.register("plain", 1500.0, matches=40, streak=0, last_day=0)
        ladder.register("surging", 1500.0, matches=40, streak=9, last_day=0)
        ladder.register("sinking", 1500.0, matches=40, streak=-9, last_day=0)

        heat = ladder.record_match("hot", "calm", day=1, margin=20)
        self.assertAlmostEqual(heat.weight, 27.6, places=6)
        self.assertAlmostEqual(heat.winner_delta(), 20.7, places=6)

        slump = ladder.record_match("plain", "cold", day=1, margin=20)
        self.assertAlmostEqual(slump.weight, 20.4, places=6)
        self.assertAlmostEqual(slump.winner_delta(), 15.3, places=6)

        levelled = ladder.record_match("surging", "sinking", day=1, margin=20)
        self.assertAlmostEqual(levelled.weight, 24.0, places=6)

        self.assertAlmostEqual(streak_multiplier(0), 1.0, places=9)
        self.assertAlmostEqual(streak_multiplier(1), 1.0, places=9)
        self.assertAlmostEqual(streak_multiplier(-1), 1.0, places=9)
        self.assertAlmostEqual(streak_multiplier(4), 1.3, places=9)
        self.assertAlmostEqual(streak_multiplier(-4), 0.7, places=9)
        self.assertAlmostEqual(streak_multiplier(9), 1.4, places=9)
        self.assertAlmostEqual(streak_multiplier(-9), 0.6, places=9)


class RatingBandTest(unittest.TestCase):
    def test_ratings_stay_inside_the_published_band(self):
        self.assertAlmostEqual(clamp_rating(3300.0), 3200.0, places=6)
        self.assertAlmostEqual(clamp_rating(60.0), 100.0, places=6)
        self.assertAlmostEqual(clamp_rating(1500.0), 1500.0, places=6)

        ladder = Ladder()
        ladder.register("peak", 3190.0, matches=30, last_day=0)
        ladder.register("near", 3190.0, matches=30, last_day=0)
        outcome = ladder.record_match("peak", "near", day=1, margin=1)
        self.assertAlmostEqual(outcome.weight, 24.0, places=6)
        self.assertAlmostEqual(ladder.rating_of("peak"), 3200.0, places=6)
        self.assertAlmostEqual(outcome.winner_delta(), 10.0, places=6)
        self.assertGreater(ladder.rating_of("near"), 3000.0)


class PlacementFloorTest(unittest.TestCase):
    def test_a_rookie_cannot_be_dropped_through_the_protection_line(self):
        ladder = Ladder()
        ladder.register("rookie", 1210.0)
        ladder.register("rival", 1250.0)
        first = ladder.record_match("rival", "rookie", day=1, margin=20)
        self.assertGreater(first.winner_delta(), 30.0)
        self.assertLess(first.loser_delta(), 0.0)
        self.assertAlmostEqual(ladder.rating_of("rookie"), 1200.0, places=6)
        ladder.record_match("rival", "rookie", day=2, margin=20)
        self.assertAlmostEqual(ladder.rating_of("rookie"), 1200.0, places=6)
        ladder.record_match("rival", "rookie", day=3, margin=20)
        self.assertAlmostEqual(ladder.rating_of("rookie"), 1200.0, places=6)

        ladder.register("veteran", 1205.0, matches=30, last_day=0)
        ladder.register("challenger", 1000.0, matches=30, last_day=0)
        placed = ladder.record_match("challenger", "veteran", day=4, margin=20)
        self.assertLess(placed.loser_delta(), 0.0)
        self.assertLess(ladder.rating_of("veteran"), 1200.0)


class DecayTest(unittest.TestCase):
    def test_a_long_absence_is_settled_with_a_capped_amount(self):
        ladder = Ladder()
        ladder.register("lapsed", 1500.0, matches=30, last_day=0)
        ladder.register("gone", 1500.0, matches=30, last_day=0)

        short = ladder.apply_decay("lapsed", day=13)
        self.assertEqual(short.days_idle, 13)
        self.assertAlmostEqual(short.amount, 0.0, places=6)
        self.assertAlmostEqual(ladder.rating_of("lapsed"), 1500.0, places=6)

        long_away = ladder.apply_decay("gone", day=200)
        self.assertEqual(long_away.days_idle, 200)
        self.assertAlmostEqual(long_away.amount, 250.0, places=6)
        self.assertAlmostEqual(ladder.rating_of("gone"), 1250.0, places=6)
        after = ladder.apply_decay("gone", day=300)
        self.assertAlmostEqual(after.amount, 0.0, places=6)
        self.assertAlmostEqual(ladder.rating_of("gone"), 1250.0, places=6)

    def test_decay_is_settled_once_for_each_stretch(self):
        ladder = Ladder()
        ladder.register("idle", 1500.0, matches=30, last_day=0)

        first = ladder.apply_decay("idle", day=34)
        self.assertAlmostEqual(first.amount, 100.0, places=6)
        self.assertAlmostEqual(ladder.rating_of("idle"), 1400.0, places=6)

        repeat = ladder.apply_decay("idle", day=34)
        self.assertAlmostEqual(repeat.amount, 0.0, places=6)
        self.assertAlmostEqual(ladder.rating_of("idle"), 1400.0, places=6)

        carried = ladder.apply_decay("idle", day=49)
        self.assertAlmostEqual(carried.amount, 75.0, places=6)
        self.assertAlmostEqual(ladder.rating_of("idle"), 1325.0, places=6)

        capped = ladder.apply_decay("idle", day=120)
        self.assertAlmostEqual(capped.amount, 75.0, places=6)
        self.assertAlmostEqual(ladder.rating_of("idle"), 1250.0, places=6)


class IdleClockTest(unittest.TestCase):
    def test_playing_a_match_starts_a_new_absence(self):
        ladder = Ladder()
        ladder.register("cycled", 1420.0, matches=30, last_day=0)
        ladder.register("rival", 1340.0, matches=30, last_day=0)

        away = ladder.apply_decay("cycled", day=30)
        self.assertAlmostEqual(away.amount, 80.0, places=6)
        self.assertAlmostEqual(ladder.rating_of("cycled"), 1340.0, places=6)

        played = ladder.record_match("cycled", "rival", day=40, margin=1)
        self.assertAlmostEqual(played.weight, 24.0, places=6)
        self.assertAlmostEqual(played.winner_delta(), 12.3, places=6)
        self.assertEqual(ladder.last_played_day_of("cycled"), 40)

        back = ladder.apply_decay("cycled", day=50)
        self.assertEqual(back.days_idle, 10)
        self.assertAlmostEqual(back.amount, 0.0, places=6)
        self.assertAlmostEqual(ladder.rating_of("cycled"), 1352.3, places=6)


class DecayFloorTest(unittest.TestCase):
    def test_decay_never_lifts_a_rating_and_never_passes_the_floor(self):
        ladder = Ladder()
        ladder.register("sunken", 130.0, matches=30, last_day=0)
        before = ladder.rating_of("sunken")

        settled = ladder.apply_decay("sunken", day=90)
        self.assertGreaterEqual(settled.amount, 0.0)
        self.assertAlmostEqual(settled.amount, 30.0, places=6)
        self.assertAlmostEqual(ladder.rating_of("sunken"), 100.0, places=6)
        self.assertLess(ladder.rating_of("sunken"), before)

        again = ladder.apply_decay("sunken", day=90)
        self.assertAlmostEqual(again.amount, 0.0, places=6)
        self.assertAlmostEqual(ladder.rating_of("sunken"), 100.0, places=6)


if __name__ == "__main__":
    unittest.main()
