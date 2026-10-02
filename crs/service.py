"""What the application shows and stores, independent of the user interface.

Used by both front ends: the Streamlit app (streamlit_app.py) and the FastAPI app (web/app.py).
"""
import csv
import io
import json
from functools import lru_cache

import numpy as np

from . import adaptive, details, i18n, questionnaire
from .data import JOB_ZONE_NAMES, RIASEC
from .recommender import Recommender

RIASEC_LABELS = {"Realistic": "Realistis", "Investigative": "Investigatif", "Artistic": "Artistik",
                 "Social": "Sosial", "Enterprising": "Enterprising", "Conventional": "Konvensional"}
PROMPTS = {"item": "Seberapa suka kamu melakukan kegiatan ini sebagai pekerjaan?",
           "area": "Seberapa suka kamu dengan bidang ini?",
           "dwa": "Seberapa suka kamu melakukan aktivitas kerja ini?"}
# Shown on the first page, next to the consent checkbox.
ABOUT_DATA = [
    "Kami tidak meminta nama, sekolah, atau kontak. Jangan menuliskannya di kolom mana pun.",
    "Jawaban dan penilaianmu disimpan tanpa identitas, dan dipakai untuk memperbaiki serta melaporkan proyek ini.",
    "Kamu boleh berhenti kapan saja.",
]
EDUCATION_PLANS = {
    "Belum tahu / tampilkan semua": None,
    "Lulus SMA/SMK lalu bekerja atau pelatihan singkat": 2,
    "Sampai D3 atau pelatihan vokasi": 3,
    "Sampai S1": 4,
    "Sampai S2/S3": 5,
}
ATTRIBUTION = (
    "Aplikasi ini memuat informasi dari O*NET 31.0 Database dan O*NET Career Exploration Tools oleh "
    "U.S. Department of Labor, Employment and Training Administration (USDOL/ETA), digunakan di bawah "
    "lisensi CC BY 4.0 dan O*NET Tools Developer License. O*NET® adalah merek dagang USDOL/ETA. "
    "Pengembang aplikasi ini telah mengubah sebagian informasi tersebut. USDOL/ETA tidak menyetujui, "
    "mendukung, atau menguji perubahan ini."
)

# System Usability Scale, Indonesian wording after Sharfina & Santoso (2016). Odd items are positive,
# even items negative; answers 1 (sangat tidak setuju) .. 5 (sangat setuju).
SUS_ITEMS = [
    "Saya berpikir akan menggunakan sistem ini lagi.",
    "Saya merasa sistem ini rumit untuk digunakan.",
    "Saya merasa sistem ini mudah digunakan.",
    "Saya membutuhkan bantuan dari orang lain atau teknisi dalam menggunakan sistem ini.",
    "Saya merasa fitur-fitur sistem ini berjalan dengan semestinya.",
    "Saya merasa ada banyak hal yang tidak konsisten pada sistem ini.",
    "Saya merasa orang lain akan memahami cara menggunakan sistem ini dengan cepat.",
    "Saya merasa sistem ini membingungkan.",
    "Saya merasa tidak ada hambatan dalam menggunakan sistem ini.",
    "Saya perlu membiasakan diri terlebih dahulu sebelum menggunakan sistem ini.",
]


def sus_score(answers):
    """Standard SUS scoring: 0..100."""
    return 2.5 * sum((a - 1) if k % 2 == 0 else (5 - a) for k, a in enumerate(answers))


@lru_cache(maxsize=1)
def recommender():
    return Recommender()


def rebuild_session(answers):
    """Replay stored answer rows (kind, idx, value, is_repeat) into a questionnaire session."""
    pool = adaptive.default_pool()
    session = adaptive.Session(pool)
    for a in answers:
        q = pool.question(a["kind"], a["idx"])
        if a["is_repeat"]:
            q = adaptive.Question(q.kind, q.index, q.text, repeat=True)
        session.answer(q, a["value"])
    return session


def title(i):
    d = recommender().data
    return i18n.occupation_title(d.codes[i], d.titles[i])


def card(i, session=None):
    """What a result card shows for occupation row i."""
    rec = recommender()
    d = rec.data
    zone = int(d.job_zones[i])
    areas, activities = session.reasons(i) if session else ([], [])
    return {
        "reason_areas": areas, "reason_activities": activities,
        "code": d.codes[i], "title": title(i), "title_en": d.titles[i],
        "description": i18n.occupation_description(d.codes[i], d.descriptions[i]),
        "job_zone": zone, "job_zone_name": JOB_ZONE_NAMES[zone],
        "skills": list(dict.fromkeys(i18n.competency(g.name) for g in rec.skill_gaps(i)))[:5],
        "related": [{"code": d.codes[j], "title": title(j)} for j in d.related.get(i, [])[:3]],
    }


def occupation_detail(code):
    """Everything the detail view shows, or None for an unknown code."""
    rec = recommender()
    d = rec.data
    if code not in d.codes:
        return None
    i = d.codes.index(code)
    detail = card(i)
    detail["interests"] = [RIASEC_LABELS[RIASEC[j]] for j in np.argsort(-d.riasec[i])[:3]]
    detail["areas"] = [questionnaire.AREA_LABELS[d.areas[j]] for j in np.argsort(-d.area_scores[i])[:3]]
    detail["skills"] = [{"name": i18n.competency(g.name), "importance": round(g.importance, 2),
                         "level": round(g.required * 7, 1)} for g in rec.skill_gaps(i, limit=10)]
    detail["related"] = [{"code": d.codes[j], "title": title(j), "job_zone": int(d.job_zones[j])}
                         for j in d.related.get(i, [])[:10]]
    detail["education"] = [{"label": label, "percent": percent} for label, percent in details.education(code)]
    detail["work_styles"] = details.work_styles(code)
    detail["software"] = details.software(code)
    return detail


def result_text(session, finished_early):
    """(headline, [paragraphs]) for the result page."""
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


def result(session, finished_early, max_job_zone):
    outcome = session.outcome
    headline, notes = result_text(session, finished_early)
    top_n = 10 if outcome == "beragam" else 5
    return {
        "outcome": outcome, "headline": headline, "notes": notes,
        "liked_areas": session.liked_areas() if outcome == "beragam" else [],
        "answered": len(session.history), "repeated": len(session.repeats),
        "max_job_zone": max_job_zone,
        "recommendations": [card(i, session) for i, _ in session.ranking(top_n, max_job_zone)],
    }


def valid_sus(answers):
    return answers is None or (len(answers) == len(SUS_ITEMS) and all(a in range(1, 6) for a in answers))


def known_codes(codes):
    known = set(recommender().data.codes)
    return [c for c in codes if c in known]


# ---------------------------------------------------------------- export for the project team
def _to_csv(header, rows):
    out = io.StringIO()
    writer = csv.writer(out)
    writer.writerow(header)
    writer.writerows(rows)
    return out.getvalue()


def export_sessions(store):
    """CSV text, one row per session: outcome, top five recommendations and feedback."""
    d, rows = recommender().data, []
    for session_id in store.all_session_ids():
        row, answers = store.get_session(session_id)
        session = rebuild_session(answers)
        fb = store.get_feedback(session_id)
        sus = json.loads(fb["sus"]) if fb and fb["sus"] else None
        done = bool(row["finished_early"]) or session.next_question() is None
        top = [d.codes[i] for i, _ in session.ranking(5, row["max_job_zone"])] if done else []
        gap = session.consistency_gap
        rows.append([
            session_id, row["created_at"], row["finished_at"] or "", row["cohort"] or "", row["max_job_zone"] or "",
            int(done), row["finished_early"], len(session.history), len(session.repeats),
            session.outcome if done else "", "" if gap is None else round(gap, 3), *top, *[""] * (5 - len(top)),
            fb["relevance"] if fb else "", fb["ease"] if fb else "", "" if sus is None else sus_score(sus),
            " ".join(json.loads(fb["interested"])) if fb else "", (fb["comment"] or "") if fb else "",
        ])
    return _to_csv(["session_id", "created_at", "finished_at", "cohort", "max_job_zone", "done", "finished_early",
                    "n_answers", "n_repeats", "outcome", "consistency_gap", "top1", "top2", "top3", "top4", "top5",
                    "relevance", "ease", "sus_score", "interested", "comment"], rows)


def export_answers(store):
    """CSV text with every answer of every session, in order (for calibration)."""
    pool = adaptive.default_pool()
    rows = [[a["session_id"], a["seq"], a["kind"], a["idx"], pool.question(a["kind"], a["idx"]).text,
             a["value"], a["is_repeat"], a["answered_at"]] for a in store.all_answers()]
    return _to_csv(["session_id", "seq", "kind", "index", "text", "value", "is_repeat", "answered_at"], rows)
