"""Demo di terminal.

    python3 -m crs --adaptif
    python3 -m crs --quiz
    python3 -m crs --riasec 16,36,12,16,8,24 --areas "Information Technology,Mathematics/Statistics"

--riasec: enam skor berurutan R,I,A,S,E,C (skala apa pun).
"""
import argparse

from . import RIASEC, Recommender, adaptive, i18n, questionnaire
from .data import JOB_ZONE_NAMES


def run_quiz(areas):
    print(questionnaire.INSTRUCTION)
    print("Jawab dengan angka: " + ", ".join(f"{i + 1} = {r}" for i, r in enumerate(questionnaire.RESPONSES)))
    answers = {}
    for item in questionnaire.items():
        while item.number not in answers:
            reply = input(f"{item.number:2d}/60  {item.text_id}: ").strip()
            if reply in {"1", "2", "3", "4", "5"}:
                answers[item.number] = int(reply) - 1
    print("\nPilih 3-5 bidang yang paling kamu minati:")
    for n, area in enumerate(areas, 1):
        print(f"  {n:2d}. {questionnaire.AREA_LABELS[area]}")
    picked = input("Nomor bidang, dipisah koma: ")
    favourite = [areas[int(n) - 1] for n in picked.replace(" ", "").split(",") if n]
    return questionnaire.score(answers), favourite


def run_adaptive(rec, top_n, max_job_zone):
    """Adaptive questionnaire: every answer decides the next question."""
    print("Kuesioner adaptif. Bayangkan kamu melakukan hal berikut sebagai pekerjaan: seberapa suka kamu?")
    print("Jawab dengan angka: " + ", ".join(f"{i + 1} = {r}" for i, r in enumerate(questionnaire.RESPONSES)))
    print("Ketik s untuk selesai lebih awal.\n")
    session, d = adaptive.Session(), rec.data
    while (q := session.next_question()) is not None:
        reply = input(f"{len(session.history) + 1:2d}. [{adaptive.KIND_LABEL[q.kind]}] {q.text}: ").strip().lower()
        if reply == "s":
            break
        if reply in {"1", "2", "3", "4", "5"}:
            session.answer(q, int(reply) - 1)
            if not q.repeat:
                best = session.ranking(1)[0][0]
                print(f"      (masih mungkin: ~{session.candidates:.0f} pekerjaan; "
                      f"terdepan: {i18n.occupation_title(d.codes[best], d.titles[best])})")

    print(f"\nSelesai setelah {len(session.history)} pertanyaan"
          + (f" dan {len(session.repeats)} pertanyaan ulang." if session.repeats else "."))
    if session.outcome == "tidak_konsisten":
        changed = sum(abs(a - b) >= 2 for _, a, b in session.repeats)
        print(f"\nJawabanmu kurang konsisten: dari {len(session.repeats)} pertanyaan yang diulang, "
              f"{changed} dijawab jauh berbeda dari jawaban pertamamu.")
        print("Hasil di bawah kurang bisa dipercaya. Coba ulangi kuesioner dengan lebih tenang, "
              "dan jawab sesuai yang benar-benar kamu rasakan.")
    elif session.outcome == "beragam":
        print(f"\nMinatmu cukup beragam: jawabanmu tidak mengerucut ke satu kelompok pekerjaan"
              f" (masih sekitar {session.candidates:.0f} pekerjaan yang sama-sama mungkin)."
              if session.reached_limit else
              "\nMinatmu cukup beragam: kamu menyukai hampir semua yang ditanyakan.")
        print("Itu bukan hasil yang buruk. Artinya kamu punya beberapa arah, bukan satu.")
        if session.liked_areas():
            print("Bidang yang kamu sukai: " + ", ".join(session.liked_areas()))
        print("Daftar di bawah adalah beberapa arah yang mungkin, bukan satu jawaban pasti. "
              "Sebaiknya dibicarakan dengan guru BK.")
        top_n = max(top_n, 10)
    elif session.outcome == "belum_jelas":
        print("\nMinatmu belum terlihat jelas: hanya sedikit dari yang ditanyakan yang kamu sukai, "
              "sehingga sistem tidak bisa memilih arah.")
        print("Daftar di bawah belum bisa dijadikan pegangan. Coba ulangi di lain waktu, "
              "atau bicarakan dengan guru BK.")
    # The model's probabilities are overconfident (near 100% for the first place), so only the order is shown.
    for rank, (i, _) in enumerate(session.ranking(top_n, max_job_zone), 1):
        print(f"\n{rank}. {i18n.occupation_title(d.codes[i], d.titles[i])} ({d.codes[i]})")
        print(f"   {i18n.occupation_description(d.codes[i], d.descriptions[i])}")
        print(f"   Persiapan          : {JOB_ZONE_NAMES[int(d.job_zones[i])]}")
        skills = list(dict.fromkeys(i18n.competency(g.name) for g in rec.skill_gaps(i)))[:5]
        print(f"   Perlu dikembangkan : {', '.join(skills)}")
        related = [i18n.occupation_title(d.codes[j], d.titles[j]) for j in d.related.get(i, [])[:3]]
        print(f"   Karier serupa      : {', '.join(related)}")


def main():
    p = argparse.ArgumentParser(description="Rekomendasi karier berbasis O*NET 31.0")
    p.add_argument("--adaptif", action="store_true", help="kuesioner adaptif (20-80 pertanyaan + 8 pertanyaan ulang)")
    p.add_argument("--quiz", action="store_true", help="isi kuesioner minat 60 butir")
    p.add_argument("--riasec", help="enam skor R,I,A,S,E,C dipisah koma")
    p.add_argument("--areas", default="", help="bidang minat favorit (nama O*NET), dipisah koma")
    p.add_argument("--max-job-zone", type=int, choices=[2, 3, 4, 5])
    p.add_argument("--top", type=int, default=5)
    p.add_argument("--list-areas", action="store_true")
    args = p.parse_args()

    rec = Recommender()
    if args.list_areas:
        for area in rec.data.areas:
            print(f"{area}  ({questionnaire.AREA_LABELS[area]})")
        return

    if args.adaptif:
        run_adaptive(rec, args.top, args.max_job_zone)
        return

    if args.quiz:
        riasec, areas = run_quiz(rec.data.areas)
        print("\nSkor minatmu (0-40): " + ", ".join(f"{k} {v}" for k, v in riasec.items()))
    elif args.riasec:
        scores = [float(x) for x in args.riasec.split(",")]
        if len(scores) != 6:
            p.error("--riasec butuh tepat enam angka")
        riasec = dict(zip(RIASEC, scores))
        areas = [a.strip() for a in args.areas.split(",") if a.strip()]
    else:
        p.error("pakai --adaptif, --quiz, atau --riasec")

    for r in rec.recommend(riasec, areas, max_job_zone=args.max_job_zone, top_n=args.top):
        print(f"\n{r.rank}. {i18n.occupation_title(r.code, r.title)} ({r.code})  [{r.fit_label}]")
        print(f"   {i18n.occupation_description(r.code, r.description)}")
        print(f"   Minat utama pekerjaan ini  : {', '.join(r.top_interests)} (korelasi {r.interest_fit:+.2f})")
        if r.matched_areas:
            print(f"   Bidang favoritmu yang cocok: "
                  f"{', '.join(questionnaire.AREA_LABELS[a] for a in r.matched_areas)}")
        print(f"   Persiapan                  : {r.job_zone_name}")
        skills = list(dict.fromkeys(i18n.competency(g.name) for g in r.skill_gaps))[:5]
        print(f"   Perlu dikembangkan         : {', '.join(skills)}")
        en_to_code = dict(zip(rec.data.titles, rec.data.codes))
        related = [i18n.occupation_title(en_to_code[t], t) for t in r.related[:3]]
        print(f"   Karier serupa              : {', '.join(related)}")


if __name__ == "__main__":
    main()
