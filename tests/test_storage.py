"""Storage behaves the same on SQLite and Postgres.

The Postgres half runs only when TEST_DATABASE_URL points at a scratch database, for example:
    TEST_DATABASE_URL=postgresql://localhost:54329/postgres .venv/bin/python -m unittest tests.test_storage
"""
import os
import sqlite3
import tempfile
import unittest

from crs import service
from crs.storage import Store


class StorageContract:
    def test_session_answers_feedback_and_export(self):
        store = self.store
        sid = store.create_session(max_job_zone=4, consent=True, cohort="XII-A")
        row, answers = store.get_session(sid)
        self.assertEqual((row["consent"], row["cohort"], row["max_job_zone"], row["finished_early"]), (1, "XII-A", 4, 0))
        self.assertEqual(list(answers), [])
        self.assertIsNone(store.get_session("tidak-ada"))

        session = service.rebuild_session([])
        for seq in range(3):
            q = session.next_question()
            session.answer(q, 3)
            store.add_answer(sid, seq, q.kind, q.index, 3, q.repeat)
        self.assertEqual(store.count_answers(sid), 3)
        row, answers = store.get_session(sid)
        self.assertEqual([a["seq"] for a in answers], [0, 1, 2])
        rebuilt = service.rebuild_session(answers)
        self.assertEqual(rebuilt.next_question(), session.next_question())

        store.mark_finished(sid, "jelas", early=True)
        store.mark_finished(sid, "jelas")                      # a later normal finish must not undo "early"
        row, _ = store.get_session(sid)
        self.assertEqual((row["finished_early"], row["outcome"]), (1, "jelas"))
        self.assertTrue(row["finished_at"])

        self.assertIsNone(store.get_feedback(sid))
        store.save_feedback(sid, 3, 4, ["29-1141.00"], None, "")
        store.save_feedback(sid, 5, 4, ["29-1141.00"], [5, 1, 5, 1, 5, 1, 5, 1, 5, 1], "bagus")   # replaces
        fb = store.get_feedback(sid)
        self.assertEqual((fb["relevance"], fb["ease"], fb["comment"]), (5, 4, "bagus"))

        self.assertIn(sid, store.all_session_ids())
        line = next(l for l in service.export_sessions(store).splitlines() if l.startswith(sid))
        # the export recomputes the outcome from the answers: three "suka" answers = likes everything
        self.assertIn(",XII-A,4,1,1,3,0,beragam,", line)
        self.assertIn(",5,4,100.0,29-1141.00,bagus", line)
        self.assertEqual(sum(l.startswith(sid) for l in service.export_answers(store).splitlines()), 3)


class SqliteStorageTest(StorageContract, unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        os.environ["CRS_DB"] = os.path.join(self.tmp.name, "test.sqlite3")
        self.store = Store()

    def tearDown(self):
        os.environ.pop("CRS_DB", None)
        self.tmp.cleanup()

    def test_backend(self):
        self.assertEqual(self.store.backend, "sqlite")

    def test_falls_back_to_a_temporary_file_when_the_data_folder_is_not_writable(self):
        from crs import storage
        os.environ.pop("CRS_DB")
        original = storage.DEFAULT_DB
        storage.DEFAULT_DB = os.path.join(self.tmp.name, "tidak", "ada", "crs.sqlite3")
        fallback = os.path.join(tempfile.gettempdir(), "crs.sqlite3")
        existed = os.path.exists(fallback)
        try:
            store = Store()
            sid = store.create_session(consent=True)
            self.assertIsNotNone(store.get_session(sid))
            self.assertEqual(str(store.sqlite_path()), fallback)
        finally:
            storage.DEFAULT_DB = original
            if not existed and os.path.exists(fallback):
                os.remove(fallback)

    def test_old_database_gets_the_new_columns(self):
        conn = sqlite3.connect(os.environ["CRS_DB"])
        conn.execute("CREATE TABLE sessions (id TEXT PRIMARY KEY, created_at TEXT NOT NULL, max_job_zone INTEGER, "
                     "finished_early INTEGER NOT NULL DEFAULT 0, finished_at TEXT, outcome TEXT)")
        conn.execute("INSERT INTO sessions (id, created_at) VALUES ('lama', '2026-10-01')")
        conn.commit()
        conn.close()
        row, _ = Store().get_session("lama")
        self.assertEqual((row["consent"], row["cohort"]), (0, None))


@unittest.skipUnless(os.environ.get("TEST_DATABASE_URL"), "TEST_DATABASE_URL tidak diisi")
class PostgresStorageTest(StorageContract, unittest.TestCase):
    def setUp(self):
        self.store = Store(os.environ["TEST_DATABASE_URL"])

    def test_backend(self):
        self.assertEqual(self.store.backend, "postgres")

    def test_reconnects_after_the_connection_drops(self):
        sid = self.store.create_session(consent=True)
        self.store._pg.close()                                  # what an idle hosted connection looks like
        self.assertIsNotNone(self.store.get_session(sid))


if __name__ == "__main__":
    unittest.main()
