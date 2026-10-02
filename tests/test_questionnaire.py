import unittest
from collections import Counter

from crs import RIASEC, Recommender, questionnaire


class QuestionnaireTest(unittest.TestCase):
    def test_sixty_items_ten_per_type(self):
        items = questionnaire.items()
        self.assertEqual([it.number for it in items], list(range(1, 61)))
        self.assertEqual(Counter(it.riasec for it in items), dict.fromkeys(RIASEC, 10))
        self.assertEqual(len({it.text_en for it in items}), 60)
        self.assertEqual(len({it.text_id for it in items}), 60)

    def test_scoring(self):
        answers = {it.number: 4 if it.riasec == "Investigative" else 1 for it in questionnaire.items()}
        scores = questionnaire.score(answers)
        self.assertEqual(scores["Investigative"], 40)
        self.assertEqual(scores["Artistic"], 10)

    def test_rejects_incomplete_invalid_and_flat_answers(self):
        full = {it.number: 2 for it in questionnaire.items()}
        with self.assertRaises(ValueError):
            questionnaire.score({1: 3})
        with self.assertRaises(ValueError):
            questionnaire.score({**full, 5: 9})
        with self.assertRaises(ValueError):
            questionnaire.score(full)

    def test_every_area_has_a_label(self):
        self.assertEqual(set(questionnaire.AREA_LABELS), set(Recommender().data.areas))

    def test_quiz_scores_feed_the_recommender(self):
        answers = {it.number: 4 if it.riasec == "Artistic" else 0 for it in questionnaire.items()}
        top = Recommender().recommend(questionnaire.score(answers), ["Music"], top_n=5)
        self.assertTrue(all(r.fit_label in ("Sangat cocok", "Cocok") for r in top))
        self.assertIn("Artistic", top[0].top_interests)


if __name__ == "__main__":
    unittest.main()
