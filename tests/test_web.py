"""Needs the project environment:  .venv/bin/python -m unittest discover tests"""
import os
import tempfile
import unittest

try:
    from fastapi.testclient import TestClient
except ImportError:  # running outside the virtual environment
    TestClient = None

from crs import adaptive


@unittest.skipIf(TestClient is None, "fastapi tidak terpasang; jalankan dengan .venv/bin/python")
class WebTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        os.environ["CRS_DB"] = os.path.join(cls.tmp.name, "test.sqlite3")
        from web.app import app
        cls.client = TestClient(app)

    @classmethod
    def tearDownClass(cls):
        os.environ.pop("CRS_DB", None)
        cls.tmp.cleanup()

    def answer(self, state, value):
        q = state["question"]
        r = self.client.post(f"/api/sessions/{state['session_id']}/answers",
                             json={"kind": q["kind"], "index": q["index"], "repeat": q["repeat"], "value": value})
        self.assertEqual(r.status_code, 200, r.text)
        return r.json()

    def complete(self, choose, **body):
        state = self.client.post("/api/sessions", json=body).json()
        while not state["done"]:
            state = self.answer(state, choose(state["question"], state["answered"]))
        return state

    def test_pages_are_served(self):
        self.assertEqual(self.client.get("/").status_code, 200)
        self.assertEqual(self.client.get("/static/app.js").status_code, 200)

    def test_full_session_and_result(self):
        pool = adaptive.default_pool()
        nurse = pool.data.index_of("Registered Nurses")

        def choose(q, _):
            if q["kind"] == "area":
                return 4 if pool.data.area_scores[nurse, q["index"]] >= 4.5 else 0
            if q["kind"] == "dwa":
                return 4 if pool.has_dwa[nurse, q["index"]] else 1
            return 2
        state = self.complete(choose)
        self.assertGreaterEqual(state["answered"], adaptive.MIN_QUESTIONS + adaptive.CONSISTENCY_QUESTIONS)
        result = self.client.get(f"/api/sessions/{state['session_id']}/result").json()
        self.assertEqual(result["outcome"], "jelas")
        self.assertEqual(result["repeated"], adaptive.CONSISTENCY_QUESTIONS)
        self.assertIn("29-1141.00", [r["code"] for r in result["recommendations"]])   # Registered Nurses
        card = next(r for r in result["recommendations"] if r["code"] == "29-1141.00")
        self.assertEqual((card["title"], card["title_en"]), ("Perawat", "Registered Nurses"))
        self.assertTrue(card["description"].startswith("Menilai masalah"))
        self.assertTrue(card["skills"] and card["related"])

    def test_progress_survives_reload(self):
        state = self.client.post("/api/sessions").json()
        state = self.answer(state, 3)
        again = self.client.get(f"/api/sessions/{state['session_id']}").json()
        self.assertEqual(again["question"], state["question"])
        self.assertEqual(again["answered"], 1)

    def test_stale_or_duplicate_answer_is_rejected(self):
        state = self.client.post("/api/sessions").json()
        q = state["question"]
        body = {"kind": q["kind"], "index": q["index"], "repeat": False, "value": 3}
        url = f"/api/sessions/{state['session_id']}/answers"
        self.assertEqual(self.client.post(url, json=body).status_code, 200)
        self.assertEqual(self.client.post(url, json=body).status_code, 409)
        self.assertEqual(self.client.post(url, json={**body, "value": 9}).status_code, 422)

    def test_result_requires_completion_and_finish_requires_minimum(self):
        state = self.client.post("/api/sessions").json()
        sid = state["session_id"]
        self.assertEqual(self.client.get(f"/api/sessions/{sid}/result").status_code, 409)
        self.assertEqual(self.client.post(f"/api/sessions/{sid}/finish").status_code, 409)
        for _ in range(adaptive.MIN_QUESTIONS):
            state = self.answer(state, 2)
        self.assertTrue(state["can_finish"])
        finished = self.client.post(f"/api/sessions/{sid}/finish").json()
        self.assertTrue(finished["done"])
        self.assertEqual(self.client.get(f"/api/sessions/{sid}/result").status_code, 200)

    def test_diverse_outcome_and_job_zone_filter(self):
        state = self.complete(lambda q, n: 3, max_job_zone=3)
        result = self.client.get(f"/api/sessions/{state['session_id']}/result").json()
        self.assertEqual(result["outcome"], "beragam")
        self.assertEqual(len(result["recommendations"]), 10)
        self.assertTrue(all(r["job_zone"] <= 3 for r in result["recommendations"]))

    def test_occupation_detail_and_unknown_ids(self):
        r = self.client.get("/api/occupations/19-2012.00").json()
        self.assertEqual((r["title"], r["title_en"]), ("Fisikawan", "Physicists"))
        self.assertIn("Fisika", [s["name"] for s in r["skills"]])
        self.assertEqual(r["interests"][0], "Investigatif")
        self.assertTrue(r["skills"][0]["level"] > 0)
        self.assertEqual(self.client.get("/api/occupations/00-0000.00").status_code, 404)
        self.assertEqual(self.client.get("/api/sessions/tidak-ada").status_code, 404)


if __name__ == "__main__":
    unittest.main()
