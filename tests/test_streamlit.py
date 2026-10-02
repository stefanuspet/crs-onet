"""Runs the Streamlit app headlessly. Needs the project environment (.venv)."""
import os
import sqlite3
import tempfile
import unittest
from pathlib import Path

try:
    from streamlit.testing.v1 import AppTest
except ImportError:  # running outside the virtual environment
    AppTest = None

from crs import adaptive

APP = str(Path(__file__).resolve().parent.parent / "streamlit_app.py")


@unittest.skipIf(AppTest is None, "streamlit tidak terpasang; jalankan dengan .venv/bin/python")
class StreamlitAppTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = os.path.join(self.tmp.name, "test.sqlite3")
        os.environ["CRS_DB"] = self.db
        os.environ["CRS_ADMIN_TOKEN"] = "rahasia"
        os.environ["CRS_SIMPAN_DATA"] = "true"
        os.environ.pop("DATABASE_URL", None)

    def tearDown(self):
        os.environ.pop("CRS_DB", None)
        os.environ.pop("CRS_ADMIN_TOKEN", None)
        os.environ.pop("CRS_SIMPAN_DATA", None)
        self.tmp.cleanup()

    def app(self, **query):
        at = AppTest.from_file(APP, default_timeout=120)
        for k, v in query.items():
            at.query_params[k] = v
        at.run()
        self.assertFalse(at.exception, at.exception)
        return at

    def answer_buttons(self, at):
        return [b for b in at.button if str(b.key).startswith("answer-")]

    def start(self, at):
        self.assertTrue(at.button[0].disabled)          # no consent yet
        at.checkbox[0].check().run()
        self.assertFalse(at.button[0].disabled)
        at.button[0].click().run()
        self.assertFalse(at.exception, at.exception)

    def complete(self, at, choose):
        while (buttons := self.answer_buttons(at)):
            text = at.subheader[0].value
            buttons[choose(text)].click().run()
            self.assertFalse(at.exception, at.exception)
        return at

    def rows(self, sql):
        return sqlite3.connect(self.db).execute(sql).fetchall()

    def test_full_session_feedback_and_storage(self):
        at = self.app()
        self.assertIn("Temukan karier", at.title[0].value)
        self.start(at)
        sid = at.query_params["s"][0]
        self.assertEqual(len(self.answer_buttons(at)), 5)

        pool = adaptive.default_pool()
        nurse = pool.data.index_of("Registered Nurses")
        liked = {pool.question("area", j).text for j in range(pool.size["area"])
                 if pool.data.area_scores[nurse, j] >= 4.5}
        liked |= {pool.question("dwa", j).text for j in range(pool.size["dwa"]) if pool.has_dwa[nurse, j]}
        self.complete(at, lambda text: 4 if text in liked else 1)

        self.assertIn("Karier yang mungkin cocok", at.title[0].value)
        self.assertIn("1. Perawat", [s.value for s in at.subheader])
        self.assertTrue(any("Kenapa muncul" in i.value for i in at.info))
        n_answers = adaptive.MIN_QUESTIONS + adaptive.CONSISTENCY_QUESTIONS
        self.assertGreaterEqual(self.rows("SELECT COUNT(*) FROM answers")[0][0], n_answers)
        self.assertEqual(self.rows("SELECT consent, outcome FROM sessions")[0], (1, "jelas"))

        # feedback: incomplete is refused, complete is stored
        at.button(key="FormSubmitter:penilaian-Kirim penilaian").click().run()
        self.assertTrue(any("perlu dijawab" in e.value for e in at.error))
        at.radio[0].set_value(4)
        at.radio[1].set_value(5)
        at.button(key="FormSubmitter:penilaian-Kirim penilaian").click().run()
        self.assertFalse(at.exception, at.exception)
        self.assertTrue(any("sudah tersimpan" in s.value for s in at.success))
        self.assertEqual(self.rows("SELECT session_id, relevance, ease, sus FROM feedback"), [(sid, 4, 5, None)])

        # a reload with the same link shows the same result instead of starting over
        again = self.app(s=sid)
        self.assertIn("Karier yang mungkin cocok", again.title[0].value)
        self.assertTrue(any("sudah tersimpan" in s.value for s in again.success))

    def test_reload_in_the_middle_continues(self):
        at = self.app()
        self.start(at)
        sid = at.query_params["s"][0]
        for _ in range(3):
            self.answer_buttons(at)[2].click().run()
        question = at.subheader[0].value
        again = self.app(s=sid)
        self.assertEqual(again.subheader[0].value, question)
        self.assertEqual(self.rows("SELECT COUNT(*) FROM answers")[0][0], 3)

    def test_unknown_session_link_falls_back_to_home(self):
        at = self.app(s="tidak-ada")
        self.assertIn("Temukan karier", at.title[0].value)

    def test_trial_mode_stores_nothing(self):
        del os.environ["CRS_SIMPAN_DATA"]
        at = self.app()
        self.assertEqual(len(at.checkbox), 0)                     # no consent box
        self.assertEqual(len(at.text_input), 0)                   # no teacher code
        self.assertTrue(any("tidak disimpan" in c.value for c in at.caption))
        at.button[0].click().run()                                # "Mulai" works straight away
        self.assertNotIn("s", at.query_params)
        self.complete(at, lambda text: 3)
        self.assertFalse(at.exception, at.exception)
        self.assertIn("Minatmu cukup beragam", at.title[0].value)
        self.assertGreaterEqual(len([s for s in at.subheader if s.value[0].isdigit()]), 5)
        self.assertEqual(len(at.radio), 0)                        # no feedback form
        self.assertFalse(os.path.exists(self.db))                 # nothing was written anywhere

        admin = self.app(admin="1")
        self.assertTrue(any("mode coba" in i.value for i in admin.info))
        self.assertEqual(len(admin.text_input), 0)

    def test_admin_export_needs_the_password(self):
        at = self.app(admin="1")
        self.assertEqual(at.title[0].value, "Ekspor data")
        self.assertEqual(len(at.get("download_button")), 0)
        at.text_input[0].set_value("salah").run()
        self.assertTrue(any("salah" in e.value for e in at.error))
        self.assertEqual(len(at.get("download_button")), 0)
        at.text_input[0].set_value("rahasia").run()
        self.assertFalse(at.exception, at.exception)
        self.assertEqual(len(at.get("download_button")), 2)


if __name__ == "__main__":
    unittest.main()
