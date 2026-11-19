import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import flirt_crush as fc  # noqa: E402


class FlirtScoreTests(unittest.TestCase):
    def test_flirty_messages_score(self):
        for text in ["love you jaan", "miss u babe 🥺", "you're so cute 😘", "good night ❤️❤️",
                     "tum cute ho", "be mine 💕"]:
            self.assertGreater(fc.flirt_score(text), 0.5, text)

    def test_normal_messages_score_zero(self):
        for text in ["what's the date today", "this hotel is nice", "pretty good game",
                     "update the bot", "babel tower", "skiss", "gnome", ""]:
            self.assertLess(fc.flirt_score(text), 0.5, text)

    def test_capped(self):
        self.assertLessEqual(fc.flirt_score("i love you babe jaan 😘😘😘💕💖 kiss cuddle"), fc.MAX_SCORE_PER_MESSAGE)


def edge(score=0.0, flirt=0.0, count=0):
    return {"score": score, "flirt_score": flirt, "flirt_count": count}


GENDERS = {1: "male", 2: "female", 3: "female", 4: "male", 5: None}


class RankTests(unittest.TestCase):
    def rank(self, edges, target_gender="male"):
        return fc.rank_crush_candidates(1, target_gender, edges, GENDERS.get)

    def test_picks_who_they_flirt_with_most(self):
        edges = {
            "1": {"2": edge(30, 2.0, 3), "3": edge(5, 9.0, 12)},
            "3": {"1": edge(4, 3.0, 4)},
        }
        ranked, _ = self.rank(edges)
        self.assertEqual(ranked[0].user_id, 3)
        self.assertTrue(ranked[0].mutual)
        self.assertEqual(ranked[0].flirts_sent, 12)

    def test_same_gender_left_out_unknown_kept(self):
        edges = {"1": {"4": edge(10, 20.0, 30), "5": edge(10, 5.0, 6), "2": edge(1, 1.0, 1)}}
        ranked, stats = self.rank(edges)
        self.assertEqual([c.user_id for c in ranked], [5, 2])
        self.assertEqual(stats["same_gender"], 1)
        self.assertEqual(stats["unknown_gender"], 1)

    def test_unknown_target_gender_includes_everyone(self):
        edges = {"1": {"4": edge(10, 20.0, 30), "2": edge(1, 1.0, 1)}}
        ranked, _ = self.rank(edges, target_gender=None)
        self.assertEqual(ranked[0].user_id, 4)

    def test_chatting_without_flirting_is_not_a_crush(self):
        edges = {"1": {"2": edge(200, 0.0, 0)}}
        ranked, _ = self.rank(edges)
        self.assertEqual(ranked, [])

    def test_admirer_only_ranks_below_real_crush(self):
        edges = {"1": {"3": edge(2, 1.0, 1)}, "2": {"1": edge(5, 15.0, 20)}}
        ranked, _ = self.rank(edges)
        self.assertEqual(ranked[0].user_id, 3)

    def test_confidence(self):
        edges = {"1": {"3": edge(5, 9.0, 12), "2": edge(5, 1.0, 1)}}
        ranked, _ = self.rank(edges)
        self.assertGreater(fc.crush_confidence(ranked), 60)
        self.assertEqual(fc.crush_confidence([]), 0)


class GenderGuessTests(unittest.TestCase):
    def test_self_votes(self):
        self.assertEqual(fc.self_gender_votes("main ghar ja raha hu, kal milunga"), (2.0, 0.0))
        self.assertEqual(fc.self_gender_votes("main thak gayi hoon, so rahi hu"), (0.0, 2.0))
        self.assertEqual(fc.self_gender_votes("I'm a girl lol"), (0.0, 1.0))
        self.assertEqual(fc.self_gender_votes("wo ja raha hai, usne kaha tha"), (0.0, 0.0))

    def test_address_votes(self):
        self.assertEqual(fc.address_gender_votes("bro what"), (0.5, 0.0))
        self.assertEqual(fc.address_gender_votes("didi please"), (0.0, 0.5))
        self.assertEqual(fc.address_gender_votes("broccoli is great"), (0.0, 0.0))

    def test_resolve(self):
        self.assertEqual(fc.resolve_gender({"male": 4, "female": 0.5}), "male")
        self.assertEqual(fc.resolve_gender({"male": 0, "female": 3}), "female")
        self.assertIsNone(fc.resolve_gender({"male": 1, "female": 0}))
        self.assertIsNone(fc.resolve_gender({"male": 3, "female": 3}))
        self.assertIsNone(fc.resolve_gender(None))


if __name__ == "__main__":
    unittest.main()
