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

    def start(self, **body):
        r = self.client.post("/api/sessions", json={"consent": True, **body})
        self.assertEqual(r.status_code, 200, r.text)
        return r.json()

    def complete(self, choose, **body):
        state = self.start(**body)
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
        state = self.start()
        state = self.answer(state, 3)
        again = self.client.get(f"/api/sessions/{state['session_id']}").json()
        self.assertEqual(again["question"], state["question"])
        self.assertEqual(again["answered"], 1)

    def test_stale_or_duplicate_answer_is_rejected(self):
        state = self.start()
        q = state["question"]
        body = {"kind": q["kind"], "index": q["index"], "repeat": False, "value": 3}
        url = f"/api/sessions/{state['session_id']}/answers"
        self.assertEqual(self.client.post(url, json=body).status_code, 200)
        self.assertEqual(self.client.post(url, json=body).status_code, 409)
        self.assertEqual(self.client.post(url, json={**body, "value": 9}).status_code, 422)

    def test_result_requires_completion_and_finish_requires_minimum(self):
        state = self.start()
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

    def test_consent_is_required(self):
        self.assertEqual(self.client.post("/api/sessions", json={}).status_code, 400)
        self.assertEqual(self.client.post("/api/sessions", json={"consent": False}).status_code, 400)

    def test_result_explains_why_and_accepts_feedback(self):
        pool = adaptive.default_pool()
        nurse = pool.data.index_of("Registered Nurses")

        def choose(q, _):
            if q["kind"] == "area":
                return 4 if pool.data.area_scores[nurse, q["index"]] >= 4.5 else 0
            return (4 if pool.has_dwa[nurse, q["index"]] else 1) if q["kind"] == "dwa" else 2
        state = self.complete(choose, cohort="  XII-A ")
        sid = state["session_id"]
        result = self.client.get(f"/api/sessions/{sid}/result").json()
        card = next(r for r in result["recommendations"] if r["code"] == "29-1141.00")
        self.assertTrue(card["reason_areas"] or card["reason_activities"])
        self.assertFalse(result["feedback_given"])
        self.assertEqual(len(result["sus_items"]), 10)

        url = f"/api/sessions/{sid}/feedback"
        self.assertEqual(self.client.post(url, json={"relevance": 9, "ease": 3}).status_code, 422)
        self.assertEqual(self.client.post(url, json={"relevance": 4, "ease": 5, "sus": [3, 3]}).status_code, 422)
        ok = self.client.post(url, json={"relevance": 4, "ease": 5, "interested": ["29-1141.00", "bukan-kode"],
                                         "sus": [5, 1, 5, 1, 5, 1, 5, 1, 5, 1], "comment": " bagus "})
        self.assertEqual(ok.status_code, 200, ok.text)
        self.assertTrue(self.client.get(f"/api/sessions/{sid}/result").json()["feedback_given"])

        # export is hidden without the right token
        self.assertEqual(self.client.get("/api/admin/sessions.csv").status_code, 404)
        os.environ["CRS_ADMIN_TOKEN"] = "rahasia"
        try:
            self.assertEqual(self.client.get("/api/admin/sessions.csv?token=salah").status_code, 404)
            text = self.client.get("/api/admin/sessions.csv?token=rahasia").text
            row = next(line for line in text.splitlines() if line.startswith(sid))
            self.assertIn(",XII-A,", row)
            self.assertIn(",jelas,", row)
            self.assertIn(",4,5,100.0,29-1141.00,bagus", row)
            answers = self.client.get("/api/admin/answers.csv?token=rahasia").text
            self.assertEqual(sum(line.startswith(sid) for line in answers.splitlines()), state["answered"])
        finally:
            del os.environ["CRS_ADMIN_TOKEN"]

    def test_feedback_requires_a_finished_session(self):
        state = self.start()
        r = self.client.post(f"/api/sessions/{state['session_id']}/feedback", json={"relevance": 3, "ease": 3})
        self.assertEqual(r.status_code, 409)

    def test_occupation_detail_and_unknown_ids(self):
        r = self.client.get("/api/occupations/19-2012.00").json()
        self.assertEqual((r["title"], r["title_en"]), ("Fisikawan", "Physicists"))
        self.assertIn("Fisika", [s["name"] for s in r["skills"]])
        self.assertEqual(r["interests"][0], "Investigatif")
        self.assertEqual(r["education"][0]["label"][:6], "Doktor")
        self.assertTrue(r["work_styles"] and r["software"])
        self.assertTrue(r["skills"][0]["level"] > 0)
        self.assertEqual(self.client.get("/api/occupations/00-0000.00").status_code, 404)
        self.assertEqual(self.client.get("/api/sessions/tidak-ada").status_code, 404)


if __name__ == "__main__":
    unittest.main()
