import unittest

import numpy as np

from crs import adaptive


def simulated_answer(pool, occupation, question, rng):
    """A student whose interests match one occupation, answering with some noise."""
    d = pool.data
    if question.kind == "item":
        mean = (d.riasec[occupation, pool.item_type[question.index]] - 1) / 6
    elif question.kind == "area":
        mean = (d.area_scores[occupation, question.index] - 1) / 6
    else:
        mean = 0.85 if pool.has_dwa[occupation, question.index] else 0.25
    return int(np.clip(round((mean + rng.normal(0, 0.15)) * 4), 0, 4))


class AdaptiveTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.pool = adaptive.default_pool()

    def run_session(self, title, flip=()):
        occupation, rng = self.pool.data.index_of(title), np.random.default_rng(0)
        session = adaptive.Session(self.pool)
        while (q := session.next_question()) is not None:
            a = simulated_answer(self.pool, occupation, q, rng)
            session.answer(q, 4 - a if len(session.history) in flip else a)
        return occupation, session

    def test_finds_the_occupation_and_stops(self):
        for title in ("Data Scientists", "Registered Nurses", "Electricians", "Graphic Designers"):
            occupation, session = self.run_session(title)
            self.assertIn(occupation, [i for i, _ in session.ranking(5)], title)
            self.assertFalse(any(q.repeat for q, _ in session.history))
            self.assertGreaterEqual(len(session.history), adaptive.MIN_QUESTIONS)
            self.assertLessEqual(len(session.history), adaptive.MAX_QUESTIONS)

    def test_no_question_is_repeated(self):
        _, session = self.run_session("Physicists")
        asked = [(q.kind, q.index) for q, _ in session.history]
        self.assertEqual(len(asked), len(set(asked)))

    def test_survives_two_reversed_answers(self):
        occupation, session = self.run_session("Data Scientists", flip=(2, 9))
        self.assertIn(occupation, [i for i, _ in session.ranking(10)])

    def test_first_question_is_the_same_for_everyone(self):
        self.assertEqual(adaptive.Session(self.pool).next_question(), adaptive.Session(self.pool).next_question())

    def test_rejects_bad_answers(self):
        session = adaptive.Session(self.pool)
        q = session.next_question()
        with self.assertRaises(ValueError):
            session.answer(q, 7)
        session.answer(q, 3)
        with self.assertRaises(ValueError):
            session.answer(q, 3)

    def constant_session(self, value):
        session = adaptive.Session(self.pool)
        while (q := session.next_question()) is not None:
            session.answer(q, value)
        return session

    def test_outcome_clear_for_a_focused_student(self):
        _, session = self.run_session("Registered Nurses")
        self.assertEqual(session.outcome, "jelas")

    def test_outcome_diverse_when_everything_is_liked(self):
        session = self.constant_session(3)
        self.assertEqual(session.outcome, "beragam")
        self.assertTrue(session.liked_areas())

    def test_outcome_unclear_when_nothing_is_liked(self):
        session = self.constant_session(2)
        self.assertEqual(len(session.history), adaptive.MAX_QUESTIONS)
        self.assertTrue(session.reached_limit)
        self.assertEqual(session.outcome, "belum_jelas")

    def test_repeats_do_not_change_the_result(self):
        _, session = self.run_session("Registered Nurses")
        self.assertEqual(len(session.repeats), adaptive.CONSISTENCY_QUESTIONS)
        asked = {(q.kind, q.index) for q, _ in session.history}
        self.assertTrue(all((q.kind, q.index) in asked for q, _, _ in session.repeats))
        before = session.ranking(10)
        fresh = adaptive.Session(self.pool)
        for q, a in session.history:
            fresh.answer(q, a)
        self.assertEqual([i for i, _ in before], [i for i, _ in fresh.ranking(10)])

    def test_consistent_student_is_not_flagged(self):
        _, session = self.run_session("Data Scientists")
        self.assertLessEqual(session.consistency_gap, adaptive.CONSISTENCY_LIMIT)
        self.assertEqual(session.outcome, "jelas")

    def test_random_answers_are_flagged(self):
        flagged = 0
        for seed in range(20):
            rng, session = np.random.default_rng(seed), adaptive.Session(self.pool)
            while (q := session.next_question()) is not None:
                session.answer(q, int(rng.integers(0, 5)))
            flagged += session.outcome == "tidak_konsisten"
        self.assertGreaterEqual(flagged, 15)

    def test_alternating_answers_are_flagged(self):
        session, k = adaptive.Session(self.pool), 0
        while (q := session.next_question()) is not None:
            session.answer(q, 4 if k % 2 == 0 else 0)
            k += 1
        self.assertEqual(session.outcome, "tidak_konsisten")

    def test_probabilities_sum_to_one_and_job_zone_filter(self):
        _, session = self.run_session("Physicists")
        self.assertAlmostEqual(session.probabilities.sum(), 1.0)
        zones = self.pool.data.job_zones
        self.assertTrue(all(zones[i] <= 3 for i, _ in session.ranking(10, max_job_zone=3)))


if __name__ == "__main__":
    unittest.main()
