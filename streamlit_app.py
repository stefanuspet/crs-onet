"""Jelajah Karier - Streamlit front end.

    .venv/bin/streamlit run streamlit_app.py

By default nothing is stored: the app only shows recommendations ("mode coba"). Storing answers
and feedback is switched on with secrets (in .streamlit/secrets.toml or the Streamlit Cloud settings):
    SIMPAN_DATA   "true" to store sessions, answers and feedback (adds the consent box, the
                  teacher code, the feedback form and the export page)
    DATABASE_URL  Postgres address; without it stored answers go to a local SQLite file
    ADMIN_TOKEN   password for the data export page (open the app with ?admin=1)
"""
import hmac
import os
import secrets as token_source

import streamlit as st

from crs import adaptive, questionnaire, service
from crs.storage import Store

TYPICAL_LENGTH = adaptive.MIN_QUESTIONS + adaptive.CONSISTENCY_QUESTIONS
AGREE = "1 = sangat tidak setuju, 5 = sangat setuju"

st.set_page_config(page_title="Jelajah Karier", layout="centered")


def secret(name):
    try:
        value = st.secrets.get(name)
    except Exception:   # no secrets file at all
        value = None
    return value or os.environ.get(name) or os.environ.get("CRS_" + name)


@st.cache_resource
def get_store():
    return Store(secret("DATABASE_URL"))


@st.cache_resource
def warm_up():
    """Load the O*NET tables and question pool once per server, not once per visitor."""
    adaptive.default_pool()
    service.recommender()
    return True


STORING = str(secret("SIMPAN_DATA") or "").strip().lower() in ("1", "true", "ya", "yes")

state = st.session_state
store = get_store() if STORING else None
warm_up()


# ---------------------------------------------------------------- session helpers
def open_session(session_id, session, max_job_zone, finished_early=False):
    state.sid = session_id
    state.session = session
    state.max_job_zone = max_job_zone
    state.finished_early = finished_early
    state.feedback_given = STORING and store.get_feedback(session_id) is not None
    if STORING:   # the link lets a reload continue from the stored answers
        st.query_params["s"] = session_id


def reset():
    for key in ("sid", "session", "max_job_zone", "finished_early", "feedback_given"):
        state.pop(key, None)
    st.query_params.clear()


def resume_from_link():
    """A reload keeps ?s=<session> in the address, so the student continues where they were."""
    session_id = st.query_params.get("s")
    if "sid" in state or not session_id:
        return
    found = store.get_session(session_id) if STORING else None
    if found is None:
        st.query_params.clear()
        return
    row, answers = found
    open_session(session_id, service.rebuild_session(answers), row["max_job_zone"], bool(row["finished_early"]))


def start(max_job_zone, cohort=None):
    if STORING:
        cohort = (cohort or "").strip()[:40] or None
        session_id = store.create_session(max_job_zone, consent=True, cohort=cohort)
    else:
        session_id = token_source.token_urlsafe(12)   # only lives in this browser tab
    open_session(session_id, adaptive.Session(), max_job_zone)


def record_answer(question, value, expected_seq):
    session = state.session
    seq = len(session.history) + len(session.repeats)
    if seq != expected_seq:   # a second click on an already answered question
        return
    session.answer(question, value)
    if STORING:
        store.add_answer(state.sid, seq, question.kind, question.index, value, question.repeat)


def finish_now():
    state.finished_early = True
    if STORING:
        store.mark_finished(state.sid, state.session.outcome, early=True)


# ---------------------------------------------------------------- views
def view_home():
    st.title("Temukan karier yang sesuai dengan minatmu")
    st.write("Jawab beberapa pertanyaan tentang kegiatan yang kamu sukai. "
             "Setiap jawabanmu menentukan pertanyaan berikutnya.")
    st.markdown("1. Sekitar 30 pertanyaan, 5 sampai 10 menit.\n"
                "2. Tidak ada jawaban benar atau salah. Jawab sesuai yang kamu rasakan.\n"
                "3. Jangan pikirkan gaji atau pendidikan yang dibutuhkan.")
    plan = st.selectbox("Rencana pendidikanmu", list(service.EDUCATION_PLANS),
                        help="Dipakai untuk menyaring pekerjaan yang butuh pendidikan lebih tinggi dari rencanamu.")
    if not STORING:
        st.caption("Hasilnya bahan eksplorasi, bukan keputusan atau tes psikologi resmi. Jawabanmu tidak disimpan.")
        if st.button("Mulai", type="primary"):
            start(service.EDUCATION_PLANS[plan])
            st.rerun()
        return

    cohort = st.text_input("Kode dari guru (opsional)", max_chars=40, placeholder="Kosongkan jika tidak diberi kode")
    with st.container(border=True):
        st.subheader("Tentang datamu")
        st.write("Aplikasi ini adalah proyek mahasiswa. Hasilnya bahan eksplorasi, bukan keputusan atau "
                 "tes psikologi resmi.")
        st.markdown("\n".join(f"- {line}" for line in service.ABOUT_DATA))
        consent = st.checkbox("Saya mengerti dan bersedia jawaban saya dipakai seperti dijelaskan di atas.")

    if st.button("Mulai", type="primary", disabled=not consent):
        start(service.EDUCATION_PLANS[plan], cohort)
        st.rerun()


def view_question(question):
    session = state.session
    answered = len(session.history) + len(session.repeats)
    st.progress(min(1.0, answered / TYPICAL_LENGTH))
    st.caption(f"Pertanyaan {answered + 1} · {adaptive.KIND_LABEL[question.kind]}")
    st.write(service.PROMPTS[question.kind])
    st.subheader(question.text)
    for value, label in enumerate(questionnaire.RESPONSES):
        st.button(label, key=f"answer-{answered}-{value}", width="stretch",
                  on_click=record_answer, args=(question, value, answered))
    if len(session.history) >= adaptive.MIN_QUESTIONS and not question.repeat:
        st.button("Selesai sekarang dan lihat hasil", type="tertiary", on_click=finish_now)


def render_detail(code):
    o = service.occupation_detail(code)
    st.caption(f"Nama di O\\*NET: {o['title_en']} ({o['code']})")
    st.markdown(f"**Tipe minat utama:** {', '.join(o['interests'])}  \n"
                f"**Bidang minat terkuat:** {', '.join(o['areas'])}  \n"
                f"**Sifat kerja yang penting:** {', '.join(o['work_styles'])}")
    if o["education"]:
        st.markdown("**Pendidikan yang dibutuhkan**")
        st.caption("Persentase pekerja di bidang ini (data Amerika Serikat) yang menyebut jenjang tersebut diperlukan.")
        for e in o["education"]:
            st.progress(e["percent"] / 100, text=f"{e['label']}: {e['percent']}%")
    st.markdown("**Kompetensi yang penting**")
    st.caption("Tingkat menunjukkan seberapa tinggi penguasaan yang dituntut pekerjaan ini, pada skala 0 sampai 7.")
    st.table([{"Kompetensi": s["name"], "Tingkat (0-7)": f"{s['level']:.1f}"} for s in o["skills"]])
    if o["software"]:
        st.markdown("**Perangkat lunak yang banyak dipakai:** " + ", ".join(o["software"]))
    st.markdown("**Karier serupa:** " + ", ".join(r["title"] for r in o["related"]))


def view_feedback(result):
    if state.feedback_given:
        st.success("Penilaianmu untuk hasil ini sudah tersimpan. Terima kasih.")
        return
    titles = {r["code"]: r["title"] for r in result["recommendations"]}
    with st.form("penilaian"):
        st.subheader("Bantu kami menilai hasil ini")
        relevance = st.radio("Seberapa sesuai rekomendasi ini dengan dirimu? (1 = tidak sesuai, 5 = sangat sesuai)",
                             [1, 2, 3, 4, 5], index=None, horizontal=True)
        ease = st.radio("Seberapa mudah kuesioner tadi diisi? (1 = sulit, 5 = mudah)",
                        [1, 2, 3, 4, 5], index=None, horizontal=True)
        interested = st.multiselect("Pekerjaan mana yang membuatmu tertarik mencari tahu lebih lanjut?",
                                    list(titles), format_func=titles.get, placeholder="Pilih satu atau lebih")
        with st.expander("Kemudahan penggunaan aplikasi (10 pernyataan, opsional)"):
            st.caption(AGREE)
            sus = [st.radio(f"{n}. {text}", [1, 2, 3, 4, 5], index=None, horizontal=True, key=f"sus-{n}")
                   for n, text in enumerate(service.SUS_ITEMS, 1)]
        comment = st.text_area("Komentar", max_chars=500, placeholder="Opsional. Jangan tulis nama atau kontak.")
        if st.form_submit_button("Kirim penilaian", type="primary"):
            sus_answered = [a for a in sus if a is not None]
            if relevance is None or ease is None:
                st.error("Dua pertanyaan pertama perlu dijawab.")
            elif 0 < len(sus_answered) < len(sus):
                st.error("Bagian kemudahan penggunaan perlu diisi semua, atau dikosongkan semua.")
            else:
                store.save_feedback(state.sid, relevance, ease, service.known_codes(interested),
                                    sus if sus_answered else None, comment.strip())
                state.feedback_given = True
                st.rerun()


def view_result():
    result = service.result(state.session, state.finished_early, state.max_job_zone)
    st.title(result["headline"])
    if result["outcome"] == "jelas":
        for note in result["notes"]:
            st.write(note)
    else:
        text = "\n\n".join(result["notes"])
        if result["liked_areas"]:
            text += "\n\nBidang yang kamu sukai: " + ", ".join(result["liked_areas"])
        st.warning(text)
    repeated = f" dan {result['repeated']} pertanyaan ulang" if result["repeated"] else ""
    st.caption(f"Dihitung dari {result['answered']} jawaban{repeated}.")

    for rank, r in enumerate(result["recommendations"], 1):
        with st.container(border=True):
            st.subheader(f"{rank}. {r['title']}")
            st.write(r["description"])
            reasons = [f"bidang {a}" for a in r["reason_areas"]] + r["reason_activities"]
            if reasons:
                st.info("**Kenapa muncul:** kamu menyukai\n" + "\n".join(f"- {t}" for t in reasons))
            st.markdown(f"**Persiapan:** {r['job_zone_name']}  \n"
                        f"**Perlu dikembangkan:** {', '.join(r['skills'])}  \n"
                        f"**Karier serupa:** {', '.join(o['title'] for o in r['related'])}")
            with st.expander("Lihat detail"):
                render_detail(r["code"])

    if STORING:
        view_feedback(result)
    st.button("Ulangi dari awal", type="tertiary", on_click=reset)


def view_admin():
    st.title("Ekspor data")
    if not STORING:
        st.info("Aplikasi berjalan dalam mode coba: tidak ada jawaban yang disimpan, jadi tidak ada yang "
                "bisa diekspor. Isi SIMPAN_DATA = \"true\" di pengaturan rahasia untuk menyalakan penyimpanan.")
        return
    expected = secret("ADMIN_TOKEN")
    if not expected:
        st.error("Ekspor belum diaktifkan: ADMIN_TOKEN belum diisi di pengaturan rahasia aplikasi.")
        return
    token = st.text_input("Kata sandi", type="password")
    if not token:
        return
    if not hmac.compare_digest(token, expected):
        st.error("Kata sandi salah.")
        return
    st.caption(f"Penyimpanan: {store.backend} · {len(store.all_session_ids())} sesi tersimpan")
    if store.backend == "sqlite":
        st.warning("Data disimpan di berkas sementara di server ini dan bisa hilang saat aplikasi dinyalakan "
                   "ulang. Cukup untuk demo; untuk uji coba ke siswa, isi DATABASE_URL (Postgres).")
    st.download_button("Unduh ringkasan sesi (sessions.csv)", service.export_sessions(store),
                       "sessions.csv", "text/csv")
    st.download_button("Unduh semua jawaban (answers.csv)", service.export_answers(store),
                       "answers.csv", "text/csv")


# ---------------------------------------------------------------- router
def main():
    if "admin" in st.query_params:
        view_admin()
        return
    resume_from_link()
    if "sid" not in state:
        view_home()
    else:
        question = None if state.finished_early else state.session.next_question()
        if question is not None:
            view_question(question)
        else:
            if STORING and not state.finished_early and state.get("marked_finished") != state.sid:
                store.mark_finished(state.sid, state.session.outcome)
                state.marked_finished = state.sid
            view_result()
    st.divider()
    st.caption(service.ATTRIBUTION.replace("*", "\\*"))   # keep "O*NET" from being read as markdown italics


main()
