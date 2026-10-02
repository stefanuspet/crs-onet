"""Adaptive questionnaire with information-gain question selection, plus bias checks.

Question pool (all taken from O*NET):
  item : the 60 Interest Profiler Short Form activities (each measures one RIASEC type)
  area : the 41 Specific Interest Areas
  dwa  : Detailed Work Activities shared by at least two occupations

Model
  Every answer is on a five-point scale (0, .25, .5, .75, 1). For occupation o and question q,
  P(answer | o, q) is a discretised Gaussian around the value O*NET gives that occupation.
  After each answer the probability of every occupation is updated with Bayes' rule; no
  occupation is ever eliminated.

Selection
  Next question = the one with the largest information gain (mutual information between the
  answer and the occupation), i.e. the largest expected drop in the entropy of P(occupation).

Synthetic students are noisy copies of one occupation. Run scripts/flatten_rdf.py first.
"""
import os

os.environ.setdefault("OMP_NUM_THREADS", "1")
os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")

import csv  # noqa: E402
import sys  # noqa: E402
from collections import Counter, defaultdict  # noqa: E402
from pathlib import Path  # noqa: E402

import numpy as np  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from crs import RIASEC, Recommender, load, questionnaire  # noqa: E402

VALUES = np.array([0.0, 0.25, 0.5, 0.75, 1.0])
SIGMA = {"item": 0.30, "area": 0.20, "dwa": 0.30}   # assumed noise of one answer
DWA_YES, DWA_NO = 0.80, 0.30                        # expected answer if the occupation has / lacks the activity
KINDS = ("item", "area", "dwa")
STAGE_NAME = {"item": "luas", "area": "bidang", "dwa": "gali"}


def answer_probs(mu, sigma, careless=0.0):
    """P(answer = each of VALUES | expected value mu); shape mu.shape + (5,).

    careless: probability that an answer does not reflect the student's interest at all
    (misread, misclick, random); such an answer is equally likely to be any of the five options.
    """
    logp = -(VALUES - np.asarray(mu)[..., None]) ** 2 / (2 * sigma ** 2)
    p = np.exp(logp - logp.max(axis=-1, keepdims=True))
    p /= p.sum(axis=-1, keepdims=True)
    return (1 - careless) * p + careless / len(VALUES)


def entropy(p):
    return -(p * np.log(np.clip(p, 1e-300, None))).sum(axis=-1)


class Model:
    def __init__(self, sigma_scale=1.0, careless=0.0):
        self.d = d = load()
        self.n = len(d.codes)
        self.R = (d.riasec - 1) / 6
        self.A = (d.area_scores - 1) / 6
        self.items = questionnaire.items()
        self.item_type = np.array([RIASEC.index(it.riasec) for it in self.items])

        row = {c: i for i, c in enumerate(d.codes)}
        names, members = {}, defaultdict(set)
        with open(ROOT / "data" / "onet_dwa.csv", encoding="utf-8") as f:
            for r in csv.DictReader(f):
                if r["soc_code"] in row:
                    names[r["dwa_id"]] = r["dwa_name"]
                    members[r["dwa_id"]].add(row[r["soc_code"]])
        ids = sorted(k for k, v in members.items() if len(v) >= 2)
        self.dwa_names = [names[k] for k in ids]
        self.M = np.zeros((self.n, len(ids)))
        for j, k in enumerate(ids):
            self.M[list(members[k]), j] = 1.0
        self.size = {"item": 60, "area": len(d.areas), "dwa": len(ids)}

        s = {k: v * sigma_scale for k, v in SIGMA.items()}
        self.P_type = answer_probs(self.R, s["item"], careless)   # occupation x RIASEC type x 5
        self.P_area = answer_probs(self.A, s["area"], careless)   # occupation x area x 5
        self.P_yes = answer_probs(DWA_YES, s["dwa"], careless)    # 5
        self.P_no = answer_probs(DWA_NO, s["dwa"], careless)
        self.H_type, self.H_area = entropy(self.P_type), entropy(self.P_area)
        self.H_yes, self.H_no = entropy(self.P_yes), entropy(self.P_no)
        self.logP_type, self.logP_area = np.log(self.P_type), np.log(self.P_area)
        self.dwa_llr = np.log(self.P_yes) - np.log(self.P_no)  # per answer: evidence for members
        self.log_no = np.log(self.P_no)

    # ---- information gain of every question of one kind, given current P(occupation) = p
    def info_gain(self, kind, p):
        if kind == "item":
            pred = np.einsum("o,ota->ta", p, self.P_type)
            return (entropy(pred) - p @ self.H_type)[self.item_type]
        if kind == "area":
            pred = np.einsum("o,oja->ja", p, self.P_area)
            return entropy(pred) - p @ self.H_area
        m = p @ self.M
        pred = m[:, None] * self.P_yes + (1 - m)[:, None] * self.P_no
        return entropy(pred) - (m * self.H_yes + (1 - m) * self.H_no)

    def log_likelihood(self, kind, j, a):
        """log P(answer index a | each occupation) for question (kind, j)."""
        if kind == "item":
            return self.logP_type[:, self.item_type[j], a]
        if kind == "area":
            return self.logP_area[:, j, a]
        return self.log_no[a] + self.M[:, j] * self.dwa_llr[a]

    def text(self, kind, j):
        if kind == "item":
            return self.items[j].text_id
        if kind == "area":
            return "Bidang: " + questionnaire.AREA_LABELS[self.d.areas[j]]
        return self.dwa_names[j]

    def run(self, answers, plan, mode="ig", rng=None, first=None, flip_steps=(),
            stop_candidates=None, max_questions=None):
        """answers: {kind: array of answer indices}. plan: (items, areas, dwa) or an int (free order).
        mode: 'ig' or 'random'. first: forced first question (kind, j). flip_steps: steps answered reversed.
        stop_candidates: after the plan, keep asking (any kind) until the effective number of still
        plausible occupations, exp(entropy), is at most this, or max_questions is reached.
        Returns (log posterior, [(kind, j, answer index)])."""
        logp = np.zeros(self.n)
        asked = {k: np.zeros(self.size[k], dtype=bool) for k in KINDS}
        stages = [(KINDS, plan)] if isinstance(plan, int) else [((k,), c) for k, c in zip(KINDS, plan)]
        if stop_candidates is not None:
            stages.append((KINDS, max_questions - sum(c for _, c in stages)))
        transcript = []
        for stage, (kinds, count) in enumerate(stages):
            extending = stop_candidates is not None and stage == len(stages) - 1
            for _ in range(count):
                p = np.exp(logp - logp.max())
                p /= p.sum()
                if extending and np.exp(entropy(p)) <= stop_candidates:
                    break
                best = None
                if first is not None and not transcript:
                    best = first
                else:
                    for kind in kinds:
                        gain = self.info_gain(kind, p) if mode == "ig" else rng.random(self.size[kind])
                        gain = np.where(asked[kind], -np.inf, gain)
                        j = int(np.argmax(gain))
                        if best is None or gain[j] > best[2]:
                            best = (kind, j, gain[j])
                kind, j = best[0], best[1]
                a = int(answers[kind][j])
                if len(transcript) in flip_steps:
                    a = 4 - a
                asked[kind][j] = True
                transcript.append((kind, j, a))
                logp = logp + self.log_likelihood(kind, j, a)
        return logp, transcript

    def all_answers_posterior(self, answers, kinds=KINDS):
        """Reference: the student answers every question of the given kinds."""
        logp = np.zeros(self.n)
        if "item" in kinds:
            logp += self.logP_type[:, self.item_type, answers["item"]].sum(axis=1)
        if "area" in kinds:
            logp += self.logP_area[:, np.arange(self.size["area"]), answers["area"]].sum(axis=1)
        if "dwa" in kinds:
            logp += self.M @ self.dwa_llr[answers["dwa"]]
        return logp


def synthetic_answers(model, i, seed=0):
    """Five-point answers of a student whose interests match occupation i."""
    rng = np.random.default_rng([seed, i])
    related = model.d.related.get(i, [])
    rel_share = model.M[related].mean(axis=0) if related else np.zeros(model.size["dwa"])
    mean_dwa = np.where(model.M[i] > 0, 0.85, 0.25 + 0.275 * rel_share)

    def five(mean, sd):
        return np.clip(np.round((mean + rng.normal(0, sd, np.shape(mean))) * 4), 0, 4).astype(int)

    return {"item": five(model.R[i, model.item_type], 0.25),
            "area": five(model.A[i], 0.15),
            "dwa": five(mean_dwa, 0.20)}


def top10(scores):
    return set(np.argsort(-scores)[:10])


def hit_and_recall(scores, i, d):
    hit = (scores > scores[i]).sum() < 10
    s = scores.copy()
    s[i] = -np.inf
    primary = set(d.related.get(i, [])[:10])
    recall = len(primary & top10(s)) / len(primary) if primary else np.nan
    return hit, recall


def summarise(results):
    hits, recalls = zip(*results)
    return np.mean(hits), np.nanmean(recalls)


def main():
    m = Model()
    d, n = m.d, m.n
    students = range(n)
    answers = [synthetic_answers(m, i) for i in students]
    print(f"{n} pekerjaan = {n} siswa sintetis; kolam pertanyaan: 60 butir, {m.size['area']} bidang, {m.size['dwa']} aktivitas\n")

    # ------------------------------------------------------------------ A. accuracy
    print("A. KETEPATAN (Hit@10 / RelRecall@10; acak 1.1%)")
    rec, flat = Recommender(d), []
    for i in students:
        totals = dict(zip(RIASEC, np.bincount(m.item_type, weights=answers[i]["item"], minlength=6)))
        noise = np.random.default_rng([1, i]).random(m.size["area"]) * 1e-6
        fav = [d.areas[j] for j in np.argsort(-(answers[i]["area"] + noise))[:5]]
        flat.append(rec.scores(totals, fav)[0])
    h, r = summarise([hit_and_recall(flat[i], i, d) for i in students])
    print(f"   {'Sistem sekarang (60 butir + pilih 5 bidang, Pearson)':58s} {h:6.1%} / {r:5.1%}")

    runs = {}
    configs = [("Corong 12+6+6, information gain", (12, 6, 6), "ig"),
               ("Bebas 24 pertanyaan, information gain", 24, "ig"),
               ("Corong 12+6+6, pertanyaan acak (kontrol)", (12, 6, 6), "random"),
               ("Corong 8+5+7, information gain", (8, 5, 7), "ig"),
               ("Corong 6+4+5, information gain", (6, 4, 5), "ig")]
    for label, plan, mode in configs:
        out = [m.run(answers[i], plan, mode, rng=np.random.default_rng([2, i])) for i in students]
        runs[label] = out
        h, r = summarise([hit_and_recall(out[i][0], i, d) for i in students])
        n_q = plan if isinstance(plan, int) else sum(plan)
        print(f"   {label + f' [{n_q}]':58s} {h:6.1%} / {r:5.1%}")
    main_label, free_label = configs[0][0], configs[1][0]
    kinds = Counter(k for _, tr in runs[free_label] for k, _, _ in tr)
    first_dwa = np.mean([next((s for s, (k, _, _) in enumerate(tr) if k == "dwa"), 24) for _, tr in runs[free_label]])
    print(f"   Mode bebas rata-rata memilih: {kinds['item'] / n:.1f} butir, {kinds['area'] / n:.1f} bidang, "
          f"{kinds['dwa'] / n:.1f} aktivitas; aktivitas pertama muncul di pertanyaan ke-{first_dwa + 1:.1f}")

    base = [runs[main_label][i][0] for i in students]

    # ------------------------------------------------------------------ 1. agreement with full versions
    print("\n1. KESESUAIAN DENGAN VERSI LENGKAP (irisan 10 besar, rata-rata dari 10)")
    full_all = [m.all_answers_posterior(answers[i]) for i in students]
    full_101 = [m.all_answers_posterior(answers[i], ("item", "area")) for i in students]
    rand = [runs[configs[2][0]][i][0] for i in students]
    for name, ref in (("semua 2.092 pertanyaan dijawab", full_all), ("60 butir + 41 bidang dijawab (101)", full_101)):
        a = np.mean([len(top10(base[i]) & top10(ref[i])) for i in students])
        b = np.mean([len(top10(rand[i]) & top10(ref[i])) for i in students])
        same1 = np.mean([np.argmax(base[i]) == np.argmax(ref[i]) for i in students])
        h, r = summarise([hit_and_recall(ref[i], i, d) for i in students])
        print(f"   acuan: {name:36s} adaptif {a:4.1f} | acak {b:4.1f} | peringkat 1 sama {same1:5.1%}"
              f" | ketepatan acuan {h:5.1%} / {r:5.1%}")

    # ------------------------------------------------------------------ 2. wrong answers
    print("\n2. KETAHANAN TERHADAP JAWABAN KELIRU (jawaban dibalik; corong 12+6+6)")
    print(f"   {'jawaban yang dibalik':34s} {'Hit@10':>7s} {'RelRecall':>10s} {'irisan 10 besar dgn tanpa keliru':>34s}")
    for label, steps in (("tidak ada", lambda g: ()), ("pertanyaan pertama", lambda g: (0,)),
                         ("1 acak dari 24", lambda g: tuple(g.choice(24, 1, replace=False))),
                         ("2 acak dari 24", lambda g: tuple(g.choice(24, 2, replace=False))),
                         ("4 acak dari 24", lambda g: tuple(g.choice(24, 4, replace=False)))):
        out = [m.run(answers[i], (12, 6, 6), flip_steps=steps(np.random.default_rng([3, i])))[0] for i in students]
        h, r = summarise([hit_and_recall(out[i], i, d) for i in students])
        ov = np.mean([len(top10(out[i]) & top10(base[i])) for i in students])
        print(f"   {label:34s} {h:7.1%} {r:10.1%} {ov:34.1f}")

    # ------------------------------------------------------------------ 3. fairness across groups
    print("\n3. KEADILAN ANTAR-KELOMPOK PEKERJAAN (corong 12+6+6; Hit@10 / RelRecall@10)")
    per = [hit_and_recall(base[i], i, d) for i in students]
    flat_per = [hit_and_recall(flat[i], i, d) for i in students]
    dominant = np.argmax(d.riasec, axis=1)
    print("   minat dominan   jumlah   adaptif           sistem sekarang")
    for t, name in enumerate(RIASEC):
        idx = np.where(dominant == t)[0]
        h, r = summarise([per[i] for i in idx])
        fh, fr = summarise([flat_per[i] for i in idx])
        print(f"   {name:15s} {len(idx):6d}   {h:6.1%} / {r:5.1%}   {fh:6.1%} / {fr:5.1%}")
    print("   jenjang persiapan")
    for z in sorted(set(d.job_zones)):
        idx = np.where(d.job_zones == z)[0]
        h, r = summarise([per[i] for i in idx])
        fh, fr = summarise([flat_per[i] for i in idx])
        print(f"   Job Zone {z:<6d} {len(idx):6d}   {h:6.1%} / {r:5.1%}   {fh:6.1%} / {fr:5.1%}")

    # ------------------------------------------------------------------ 4. coverage
    print("\n4. CAKUPAN (pekerjaan yang muncul di 10 besar; idealnya tiap pekerjaan muncul ~10 kali)")
    for name, scores in (("corong adaptif 12+6+6", base), ("sistem sekarang", flat)):
        counts = Counter(j for i in students for j in top10(scores[i]))
        c = np.array([counts.get(j, 0) for j in range(n)])
        print(f"   {name:24s} pernah muncul {np.mean(c > 0):6.1%} | tidak pernah {int((c == 0).sum()):3d} | "
              f"paling sering {c.max():3d} kali ({d.titles[int(np.argmax(c))]})")

    # ------------------------------------------------------------------ 5. first question
    print("\n5. PENGARUH PERTANYAAN PERTAMA (pertanyaan pembuka dipaksa; sisanya information gain)")
    default_first = Counter(tr[0][:2] for _, tr in runs[main_label])
    kind0, j0 = default_first.most_common(1)[0][0]
    print(f"   pembuka bawaan: \"{m.text(kind0, j0)}\" (dipakai untuk {default_first.most_common(1)[0][1]} dari {n} siswa)")
    for t in range(6):
        j = int(np.where(m.item_type == t)[0][0])
        out = [m.run(answers[i], (12, 6, 6), first=("item", j))[0] for i in students]
        h, r = summarise([hit_and_recall(out[i], i, d) for i in students])
        ov = np.mean([len(top10(out[i]) & top10(base[i])) for i in students])
        print(f"   pembuka butir {RIASEC[t]:13s} Hit@10 {h:6.1%} | RelRecall {r:5.1%} | irisan 10 besar dgn bawaan {ov:4.1f}")

    # ------------------------------------------------------------------ 6. sensitivity to the noise settings
    print("\n6. SENSITIVITAS ANGKA PENGATURAN (sigma dikali faktor; corong 12+6+6)")
    for scale in (0.5, 0.75, 1.0, 1.5, 2.0):
        ms = Model(sigma_scale=scale)
        out = [ms.run(answers[i], (12, 6, 6))[0] for i in students]
        h, r = summarise([hit_and_recall(out[i], i, d) for i in students])
        ov = np.mean([len(top10(out[i]) & top10(base[i])) for i in students])
        print(f"   sigma x {scale:<4} Hit@10 {h:6.1%} | RelRecall {r:5.1%} | irisan 10 besar dgn x1.0: {ov:4.1f}")

    # ------------------------------------------------------------------ example session
    print("\nCONTOH SESI (siswa sintetis yang cocok dengan 'Data Scientists', corong 12+6+6)")
    i = d.index_of("Data Scientists")
    logp, transcript = m.run(answers[i], (12, 6, 6))
    for step, (kind, j, a) in enumerate(transcript, 1):
        print(f"   {step:2d} [{STAGE_NAME[kind]:6s}] {m.text(kind, j)[:74]:74s} -> {questionnaire.RESPONSES[a]}")
    print("   Rekomendasi: " + "; ".join(d.titles[j] for j in np.argsort(-logp)[:5]))


def improvements():
    """Two fixes for sensitivity to wrong answers: a careless-answer probability in the model,
    and asking extra questions until few occupations remain plausible."""
    answers = None
    print("Corong 12+6+6 sebagai dasar. Angka: Hit@10 / RelRecall@10. 'Dibalik' = jawaban siswa dibalik,")
    print("dipilih acak dari 24 pertanyaan pertama. 'n' = rata-rata jumlah pertanyaan.\n")
    header = f"{'peluang asal':>12s} {'aturan berhenti':28s}"
    for k in (0, 1, 2, 4):
        header += f" | {str(k) + ' dibalik':>19s}"
    print(header + " | irisan dgn lengkap")
    for careless in (0.0, 0.05, 0.10, 0.20):
        m = Model(careless=careless)
        d, n = m.d, m.n
        if answers is None:
            answers = [synthetic_answers(m, i) for i in range(n)]
        full = [m.all_answers_posterior(answers[i]) for i in range(n)]
        for label, stop, max_q in (("tetap 24", None, None),
                                   ("sampai <= 10 kandidat, maks 40", 10, 40),
                                   ("sampai <= 5 kandidat, maks 40", 5, 40),
                                   ("sampai <= 5 kandidat, maks 60", 5, 60)):
            line, overlap = f"{careless:12.2f} {label:28s}", None
            for k in (0, 1, 2, 4):
                out = [m.run(answers[i], (12, 6, 6), stop_candidates=stop, max_questions=max_q,
                             flip_steps=tuple(np.random.default_rng([3, i]).choice(24, k, replace=False)) if k else ())
                       for i in range(n)]
                h, r = summarise([hit_and_recall(out[i][0], i, d) for i in range(n)])
                q = np.mean([len(tr) for _, tr in out])
                line += f" | {h:5.1%}/{r:5.1%} n={q:4.1f}"
                if k == 0:
                    overlap = np.mean([len(top10(out[i][0]) & top10(full[i])) for i in range(n)])
            print(line + f" | {overlap:4.1f}")
        print()


if __name__ == "__main__":
    improvements() if "perbaikan" in sys.argv[1:] else main()
