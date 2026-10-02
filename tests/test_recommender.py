"""Run with:  python3 -m unittest discover tests"""
import unittest

import numpy as np

from crs import RIASEC, Recommender


class RecommenderTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rec = Recommender()
        cls.data = cls.rec.data

    def test_data_is_complete(self):
        d = self.data
        self.assertEqual(len(d.codes), 878)
        self.assertEqual(len(d.areas), 41)
        self.assertEqual(d.riasec.shape, (878, 6))
        self.assertFalse(np.isnan(d.level).any())
        self.assertEqual(set(d.job_zones), {2, 3, 4, 5})

    def test_own_profile_returns_the_occupation(self):
        i = self.data.index_of("Physicists")
        riasec = dict(zip(RIASEC, self.data.riasec[i]))
        titles = [r.title for r in self.rec.recommend(
            riasec, ["Physical Science", "Mathematics/Statistics"])]
        self.assertIn("Physicists", titles[:3])

    def test_riasec_scale_does_not_matter(self):
        a = {"Realistic": 2, "Investigative": 9, "Artistic": 4, "Social": 5, "Enterprising": 1, "Conventional": 6}
        b = {k: v * 4 for k, v in a.items()}
        self.assertEqual([r.code for r in self.rec.recommend(a)], [r.code for r in self.rec.recommend(b)])

    def test_job_zone_filter(self):
        riasec = dict(zip(RIASEC, [1, 7, 2, 2, 1, 4]))
        self.assertTrue(all(r.job_zone <= 3 for r in self.rec.recommend(riasec, max_job_zone=3)))

    def test_skill_gap_uses_level_scale(self):
        gaps = {g.name: g for g in self.rec.skill_gaps("Physicists", {"Mathematical Reasoning": 0.75}, limit=200)}
        g = gaps["Mathematical Reasoning"]
        self.assertAlmostEqual(g.required, 6.0 / 7)       # O*NET Level 6.00 on a 0..7 scale
        self.assertAlmostEqual(g.gap, 6.0 / 7 - 0.75)
        self.assertTrue(all(x.importance >= 3 for x in gaps.values()))
        self.assertIsNone(gaps["Physics"].gap)            # not assessed -> no gap number

    def test_invalid_input(self):
        with self.assertRaises(ValueError):
            self.rec.recommend({"Realistic": 1})
        with self.assertRaises(ValueError):
            self.rec.recommend(dict(zip(RIASEC, range(6))), ["Not An Area"])

    def test_quality_on_synthetic_students(self):
        """Regression guard: noisy copies of each occupation's interests should find it again,
        and should surface O*NET's primary Related Occupations far above chance (1.1%)."""
        d, rng = self.data, np.random.default_rng(0)
        R = np.clip((d.riasec - 1) / 6 + rng.normal(0, 0.10, d.riasec.shape), 0, 1)
        A = np.clip((d.area_scores - 1) / 6 + rng.normal(0, 0.10, d.area_scores.shape), 0, 1)
        hits, recalls = [], []
        for i in range(len(d.codes)):
            fav = [d.areas[j] for j in np.argsort(-A[i])[:5]]
            total, _, _ = self.rec.scores(dict(zip(RIASEC, R[i])), fav)
            hits.append((total > total[i]).sum() < 10)
            primary = set(d.related.get(i, [])[:10])
            total[i] = -np.inf
            if primary:
                recalls.append(len(primary & set(np.argsort(-total)[:10])) / len(primary))
        self.assertGreater(np.mean(hits), 0.80)
        self.assertGreater(np.mean(recalls), 0.28)


if __name__ == "__main__":
    unittest.main()
