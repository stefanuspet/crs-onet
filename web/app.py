"""FastAPI front end (alternative to streamlit_app.py; both share crs/service.py and crs/storage.py).

    .venv/bin/uvicorn web.app:app --reload      ->  http://127.0.0.1:8000

The server keeps no questionnaire state in memory: every request rebuilds the session by
replaying its stored answers, so a restart never loses a student's progress.
"""
import hmac
import os
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from crs import adaptive, questionnaire, service
from crs.storage import Store

STATIC = Path(__file__).resolve().parent / "static"

app = FastAPI(title="CRS - Rekomendasi Karier")
store = Store(os.environ.get("DATABASE_URL"))


class NewSession(BaseModel):
    consent: bool = False
    cohort: str | None = Field(default=None, max_length=40)
    max_job_zone: int | None = Field(default=None, ge=2, le=5)


class Answer(BaseModel):
    kind: str
    index: int
    repeat: bool = False
    value: int = Field(ge=0, le=4)


class Feedback(BaseModel):
    relevance: int = Field(ge=1, le=5)
    ease: int = Field(ge=1, le=5)
    interested: list[str] = Field(default_factory=list, max_length=20)
    sus: list[int] | None = None
    comment: str | None = Field(default=None, max_length=500)


def _load(session_id):
    found = store.get_session(session_id)
    if found is None:
        raise HTTPException(404, "Sesi tidak ditemukan")
    row, answers = found
    return row, service.rebuild_session(answers)


def _state(session_id, row, session):
    question = None if row["finished_early"] else session.next_question()
    answered = len(session.history) + len(session.repeats)
    body = {
        "session_id": session_id,
        "done": question is None,
        "answered": answered,
        "can_finish": len(session.history) >= adaptive.MIN_QUESTIONS,
        "responses": questionnaire.RESPONSES,
        "question": None,
    }
    if question is not None:
        body["question"] = {
            "kind": question.kind, "index": question.index, "repeat": question.repeat,
            "label": adaptive.KIND_LABEL[question.kind], "prompt": service.PROMPTS[question.kind],
            "text": question.text, "number": answered + 1,
        }
    return body


@app.post("/api/sessions")
def create_session(body: NewSession):
    if not body.consent:
        raise HTTPException(400, "Persetujuan diperlukan sebelum memulai")
    cohort = (body.cohort or "").strip() or None
    session_id = store.create_session(body.max_job_zone, consent=True, cohort=cohort)
    row, session = _load(session_id)
    return _state(session_id, row, session)


@app.get("/api/sessions/{session_id}")
def get_session(session_id: str):
    row, session = _load(session_id)
    return _state(session_id, row, session)


@app.post("/api/sessions/{session_id}/answers")
def post_answer(session_id: str, answer: Answer):
    row, session = _load(session_id)
    expected = None if row["finished_early"] else session.next_question()
    if expected is None:
        raise HTTPException(409, "Kuesioner sudah selesai")
    if (answer.kind, answer.index, answer.repeat) != (expected.kind, expected.index, expected.repeat):
        # A double click or a stale page: tell the client which question is actually open.
        raise HTTPException(409, "Jawaban bukan untuk pertanyaan yang sedang aktif")
    store.add_answer(session_id, len(session.history) + len(session.repeats),
                     answer.kind, answer.index, answer.value, answer.repeat)
    row, session = _load(session_id)
    state = _state(session_id, row, session)
    if state["done"]:
        store.mark_finished(session_id, session.outcome)
    return state


@app.post("/api/sessions/{session_id}/finish")
def finish_early(session_id: str):
    row, session = _load(session_id)
    if len(session.history) < adaptive.MIN_QUESTIONS:
        raise HTTPException(409, f"Jawab minimal {adaptive.MIN_QUESTIONS} pertanyaan dulu")
    store.mark_finished(session_id, session.outcome, early=session.next_question() is not None)
    row, session = _load(session_id)
    return _state(session_id, row, session)


def _finished(session_id):
    row, session = _load(session_id)
    if not row["finished_early"] and session.next_question() is not None:
        raise HTTPException(409, "Kuesioner belum selesai")
    return row, session


@app.get("/api/sessions/{session_id}/result")
def get_result(session_id: str):
    row, session = _finished(session_id)
    body = service.result(session, bool(row["finished_early"]), row["max_job_zone"])
    body["feedback_given"] = store.get_feedback(session_id) is not None
    body["sus_items"] = service.SUS_ITEMS
    return body


@app.post("/api/sessions/{session_id}/feedback")
def post_feedback(session_id: str, body: Feedback):
    _finished(session_id)
    if not service.valid_sus(body.sus):
        raise HTTPException(422, "Jawaban SUS harus 10 angka antara 1 dan 5")
    store.save_feedback(session_id, body.relevance, body.ease, service.known_codes(body.interested),
                        body.sus, (body.comment or "").strip())
    return {"saved": True}


@app.get("/api/occupations/{code}")
def get_occupation(code: str):
    detail = service.occupation_detail(code)
    if detail is None:
        raise HTTPException(404, "Pekerjaan tidak ditemukan")
    return detail


# ---------------------------------------------------------------- data export for the project team
def _export(token, text, name):
    expected = os.environ.get("CRS_ADMIN_TOKEN")
    if not expected or not token or not hmac.compare_digest(token, expected):
        raise HTTPException(404, "Not Found")   # do not reveal that the export exists
    return Response(text(store), media_type="text/csv; charset=utf-8",
                    headers={"Content-Disposition": f'attachment; filename="{name}"'})


@app.get("/api/admin/sessions.csv")
def export_sessions(token: str = ""):
    return _export(token, service.export_sessions, "sessions.csv")


@app.get("/api/admin/answers.csv")
def export_answers(token: str = ""):
    return _export(token, service.export_answers, "answers.csv")


@app.get("/")
def index():
    return FileResponse(STATIC / "index.html")


app.mount("/static", StaticFiles(directory=STATIC), name="static")
