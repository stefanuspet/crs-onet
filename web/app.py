"""Web API and pages for the career recommendation system.

    .venv/bin/uvicorn web.app:app --reload      ->  http://127.0.0.1:8000

The server keeps no questionnaire state in memory: every request rebuilds the session by
replaying its stored answers, so a restart never loses a student's progress.
"""
from pathlib import Path

import numpy as np
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from crs import RIASEC, Recommender, adaptive, i18n, questionnaire
from crs.data import JOB_ZONE_NAMES

from . import store

STATIC = Path(__file__).resolve().parent / "static"
RIASEC_LABELS = {"Realistic": "Realistis", "Investigative": "Investigatif", "Artistic": "Artistik",
                 "Social": "Sosial", "Enterprising": "Enterprising", "Conventional": "Konvensional"}
PROMPTS = {"item": "Seberapa suka kamu melakukan kegiatan ini sebagai pekerjaan?",
           "area": "Seberapa suka kamu dengan bidang ini?",
           "dwa": "Seberapa suka kamu melakukan aktivitas kerja ini?"}

app = FastAPI(title="CRS - Rekomendasi Karier")
_recommender = None


def recommender():
    global _recommender
    if _recommender is None:
        _recommender = Recommender()
    return _recommender


class NewSession(BaseModel):
    max_job_zone: int | None = Field(default=None, ge=2, le=5)


class Answer(BaseModel):
    kind: str
    index: int
    repeat: bool = False
    value: int = Field(ge=0, le=4)


def _load(session_id):
    """Rebuild the questionnaire session from its stored answers."""
    found = store.get_session(session_id)
    if found is None:
        raise HTTPException(404, "Sesi tidak ditemukan")
    row, answers = found
    pool = adaptive.default_pool()
    session = adaptive.Session(pool)
    for a in answers:
        q = pool.question(a["kind"], a["idx"])
        if a["is_repeat"]:
            q = adaptive.Question(q.kind, q.index, q.text, repeat=True)
        session.answer(q, a["value"])
    return row, session


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
            "label": adaptive.KIND_LABEL[question.kind], "prompt": PROMPTS[question.kind],
            "text": question.text, "number": answered + 1,
        }
    return body


def _title(i):
    d = recommender().data
    return i18n.occupation_title(d.codes[i], d.titles[i])


def _card(i):
    d, rec = recommender().data, recommender()
    zone = int(d.job_zones[i])
    return {
        "code": d.codes[i], "title": _title(i), "title_en": d.titles[i],
        "description": i18n.occupation_description(d.codes[i], d.descriptions[i]),
        "job_zone": zone, "job_zone_name": JOB_ZONE_NAMES[zone],
        "skills": list(dict.fromkeys(i18n.competency(g.name) for g in rec.skill_gaps(i)))[:5],
        "related": [{"code": d.codes[j], "title": _title(j)} for j in d.related.get(i, [])[:3]],
    }


def _result_text(session, finished_early):
    outcome = session.outcome
    if outcome == "tidak_konsisten":
        changed = sum(abs(a - b) >= 2 for _, a, b in session.repeats)
        return ("Jawabanmu kurang konsisten",
                [f"Dari {len(session.repeats)} pertanyaan yang diulang, {changed} kamu jawab jauh berbeda "
                 "dari jawaban pertamamu.",
                 "Hasil di bawah kurang bisa dipercaya. Coba ulangi kuesioner dengan lebih tenang, dan jawab "
                 "sesuai yang benar-benar kamu rasakan."])
    if outcome == "beragam":
        first = (f"Jawabanmu tidak mengerucut ke satu kelompok pekerjaan: masih sekitar "
                 f"{session.candidates:.0f} pekerjaan yang sama-sama mungkin."
                 if session.reached_limit else "Kamu menyukai hampir semua yang ditanyakan.")
        return ("Minatmu cukup beragam",
                [first, "Itu bukan hasil yang buruk. Artinya kamu punya beberapa arah, bukan satu.",
                 "Daftar di bawah adalah beberapa arah yang mungkin, bukan satu jawaban pasti. "
                 "Sebaiknya dibicarakan dengan guru BK."])
    if outcome == "belum_jelas":
        return ("Minatmu belum terlihat jelas",
                ["Hanya sedikit dari yang ditanyakan yang kamu sukai, sehingga sistem tidak bisa memilih arah.",
                 "Daftar di bawah belum bisa dijadikan pegangan. Coba ulangi di lain waktu, atau bicarakan "
                 "dengan guru BK."])
    notes = ["Urutan di bawah dihitung dari jawabanmu. Anggap sebagai bahan eksplorasi, bukan keputusan."]
    if finished_early:
        notes.append("Kamu menyelesaikan kuesioner lebih awal, jadi hasil ini dihitung dari lebih sedikit jawaban "
                     "dan tanpa pemeriksaan konsistensi.")
    return "Karier yang mungkin cocok untukmu", notes


@app.post("/api/sessions")
def create_session(body: NewSession | None = None):
    session_id = store.create_session(body.max_job_zone if body else None)
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
    store.add_answer(session_id, answer.kind, answer.index, answer.value, answer.repeat)
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


@app.get("/api/sessions/{session_id}/result")
def get_result(session_id: str):
    row, session = _load(session_id)
    if not row["finished_early"] and session.next_question() is not None:
        raise HTTPException(409, "Kuesioner belum selesai")
    outcome = session.outcome
    headline, notes = _result_text(session, bool(row["finished_early"]))
    top_n = 10 if outcome == "beragam" else 5
    return {
        "outcome": outcome, "headline": headline, "notes": notes,
        "liked_areas": session.liked_areas() if outcome == "beragam" else [],
        "answered": len(session.history), "repeated": len(session.repeats),
        "max_job_zone": row["max_job_zone"],
        "recommendations": [_card(i) for i, _ in session.ranking(top_n, row["max_job_zone"])],
    }


@app.get("/api/occupations/{code}")
def get_occupation(code: str):
    rec = recommender()
    d = rec.data
    if code not in d.codes:
        raise HTTPException(404, "Pekerjaan tidak ditemukan")
    i = d.codes.index(code)
    card = _card(i)
    card["interests"] = [RIASEC_LABELS[RIASEC[j]] for j in np.argsort(-d.riasec[i])[:3]]
    card["areas"] = [questionnaire.AREA_LABELS[d.areas[j]] for j in np.argsort(-d.area_scores[i])[:3]]
    card["skills"] = [{"name": i18n.competency(g.name), "importance": round(g.importance, 2),
                       "level": round(g.required * 7, 1)} for g in rec.skill_gaps(i, limit=10)]
    card["related"] = [{"code": d.codes[j], "title": _title(j), "job_zone": int(d.job_zones[j])}
                       for j in d.related.get(i, [])[:10]]
    return card


@app.get("/")
def index():
    return FileResponse(STATIC / "index.html")


app.mount("/static", StaticFiles(directory=STATIC), name="static")
