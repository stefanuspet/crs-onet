"""Experiments on the CRS prototype, using data flattened from the official O*NET 31.0 RDF.

A. Reproduce notebook/CRS_Simple.ipynb (same graph, same weights, same PPR).
B. PPR vs similarity on the notebook's student profiles.
C. Synthetic-student evaluation (self-retrieval + Related Occupations recall).
D. Related Occupations as edges (and why they then cannot be ground truth).
E. Edge-weight variants.
F. Alpha sensitivity.
G. Skill-gap scale check.

Run scripts/flatten_rdf.py first.
"""
import csv
from collections import defaultdict
from pathlib import Path

import numpy as np
from scipy.stats import spearmanr

ROOT = Path(__file__).resolve().parent.parent
RIASEC = ["Realistic", "Investigative", "Artistic", "Social", "Enterprising", "Conventional"]
COMP_DOMAINS = ["Abilities", "Knowledge", "EssentialSkills", "TransferableSkills"]

# ---------------------------------------------------------------- student profiles (from the notebook)
NOTEBOOK_PROFILES = {
    "Student 1 (cell 6)": (
        {"Realistic": 0.65, "Investigative": 0.90, "Artistic": 0.40, "Social": 0.50,
         "Enterprising": 0.35, "Conventional": 0.60},
        {"Deductive Reasoning": 0.85, "Inductive Reasoning": 0.80, "Mathematical Reasoning": 0.75,
         "Critical Thinking": 0.90, "Complex Problem Solving": 0.85, "Systems Analysis": 0.80,
         "Systems Evaluation": 0.75, "Programming": 0.85, "Technology Design": 0.80,
         "Written Expression": 0.70, "Oral Comprehension": 0.75, "Active Listening": 0.70,
         "Reading Comprehension": 0.80, "Speaking": 0.65, "Social Perceptiveness": 0.55,
         "Service Orientation": 0.50}),
    "Student 2 (cell 23)": (
        {"Realistic": 0.30, "Investigative": 0.40, "Artistic": 0.90, "Social": 0.85,
         "Enterprising": 0.60, "Conventional": 0.40},
        {"Written Expression": 0.85, "Oral Comprehension": 0.80, "Active Listening": 0.90,
         "Reading Comprehension": 0.80, "Speaking": 0.85, "Social Perceptiveness": 0.90,
         "Service Orientation": 0.85, "Critical Thinking": 0.65, "Complex Problem Solving": 0.60,
         "Programming": 0.40, "Systems Analysis": 0.40, "Systems Evaluation": 0.40,
         "Technology Design": 0.30, "Deductive Reasoning": 0.50, "Inductive Reasoning": 0.50,
         "Mathematical Reasoning": 0.40}),
    "Artistic Social": (
        {"Realistic": 0.20, "Investigative": 0.30, "Artistic": 0.95, "Social": 0.90,
         "Enterprising": 0.60, "Conventional": 0.30},
        {"Written Expression": 0.90, "Speaking": 0.90, "Active Listening": 0.90,
         "Reading Comprehension": 0.85, "Social Perceptiveness": 0.90, "Service Orientation": 0.90,
         "Critical Thinking": 0.70}),
    "Enterprising Social": (
        {"Realistic": 0.30, "Investigative": 0.30, "Artistic": 0.40, "Social": 0.85,
         "Enterprising": 0.95, "Conventional": 0.70},
        {"Speaking": 0.90, "Oral Comprehension": 0.90, "Active Listening": 0.85,
         "Social Perceptiveness": 0.90, "Service Orientation": 0.85, "Written Expression": 0.80,
         "Critical Thinking": 0.75}),
    "Realistic Technical": (
        {"Realistic": 0.95, "Investigative": 0.70, "Artistic": 0.20, "Social": 0.30,
         "Enterprising": 0.40, "Conventional": 0.50},
        {"Mathematical Reasoning": 0.85, "Deductive Reasoning": 0.85, "Inductive Reasoning": 0.80,
         "Complex Problem Solving": 0.85, "Technology Design": 0.90, "Systems Analysis": 0.80,
         "Systems Evaluation": 0.80, "Programming": 0.70}),
}

NOTEBOOK_TOP10_STUDENT1 = [
    "Physicists", "Robotics Engineers", "Manufacturing Engineers",
    "Bioengineers and Biomedical Engineers", "Anesthesiologists",
    "Marine Engineers and Naval Architects", "Oral and Maxillofacial Surgeons",
    "Emergency Medicine Physicians", "Urologists", "Ophthalmologists, Except Pediatric",
]


# ---------------------------------------------------------------- data
class Data:
    def __init__(self, only_complete=False):
        self.title = {}
        raw = defaultdict(dict)  # (soc, domain, element) -> {scale: value}
        with open(ROOT / "data" / "onet_ratings.csv", encoding="utf-8") as f:
            for r in csv.DictReader(f):
                if r["domain"] in ("WorkActivities", "SpecificInterestAreas") or r["scale_id"] == "IH":
                    continue
                self.title[r["soc_code"]] = r["title"]
                raw[(r["soc_code"], r["domain"], r["element_name"])][r["scale_id"]] = float(r["value"])
        if only_complete:  # drop occupations that only have interest data (no abilities/skills/knowledge)
            has_comp = {soc for (soc, dom, _) in raw if dom in COMP_DOMAINS}
            raw = {k: v for k, v in raw.items() if k[0] in has_comp}
            self.title = {k: v for k, v in self.title.items() if k in has_comp}
        self.raw = raw
        self.occs = sorted(self.title)
        self.occ_idx = {o: i for i, o in enumerate(self.occs)}
        self.elems = [("CareerInterestTypes", n) for n in RIASEC] + sorted(
            {(d, e) for (_, d, e) in raw if d in COMP_DOMAINS})
        self.elem_idx = {e: i for i, e in enumerate(self.elems)}
        self.by_name = defaultdict(list)
        for e, i in self.elem_idx.items():
            self.by_name[e[1]].append(i)
        self.n_int = len(RIASEC)

        self.related = defaultdict(list)  # occ index -> [(related occ index, tier)]
        with open(ROOT / "data" / "onet_related_occupations.csv", encoding="utf-8") as f:
            for r in csv.DictReader(f):
                if r["soc_code"] in self.occ_idx and r["related_soc_code"] in self.occ_idx:
                    self.related[self.occ_idx[r["soc_code"]]].append(
                        (self.occ_idx[r["related_soc_code"]], r["tier"]))

    def features(self, mode="mean"):
        """Occupation x element matrix of weights in 0..1 (NaN where O*NET has no rating)."""
        F = np.full((len(self.occs), len(self.elems)), np.nan)
        for (soc, dom, el), sc in self.raw.items():
            i, j = self.occ_idx[soc], self.elem_idx[(dom, el)]
            if dom == "CareerInterestTypes":
                F[i, j] = (sc["OI"] - 1) / 6
            elif mode == "mean":        # what the notebook does: pivot_table averages IM and LV, then /7
                F[i, j] = (sc["IM"] + sc["LV"]) / 2 / 7
            elif mode == "IM":
                F[i, j] = (sc["IM"] - 1) / 4
            elif mode == "LV":
                F[i, j] = sc["LV"] / 7
            elif mode == "IMxLV":
                F[i, j] = (sc["IM"] - 1) / 4 * sc["LV"] / 7
            elif mode == "LV|IM>=3":    # keep an edge only if the element is at least "Important"
                F[i, j] = sc["LV"] / 7 if sc["IM"] >= 3 else 0.0
        return F


def ppr_operator(F, alpha, dup_skill_cols=None, related=None, related_share=0.0):
    """Return (R, n_occ, elem_offset): scores for a personalization row vector v are v @ R.

    Graph: occupation <-> element, both directions, weight F (same as the notebook).
    dup_skill_cols: element columns duplicated as extra nodes (the notebook's 'skill:*' nodes).
    related: occ -> [(occ, tier)]; related_share = share of an occupation's out-weight sent to them.
    """
    n_occ, n_el = F.shape
    Fz = np.nan_to_num(F)
    dup = Fz[:, dup_skill_cols] if dup_skill_cols is not None else np.zeros((n_occ, 0))
    n = n_occ + n_el + dup.shape[1]
    W = np.zeros((n, n))
    W[:n_occ, n_occ:n_occ + n_el] = Fz
    W[n_occ:n_occ + n_el, :n_occ] = Fz.T
    W[:n_occ, n_occ + n_el:] = dup
    W[n_occ + n_el:, :n_occ] = dup.T
    if related and related_share > 0:
        strength = W[:n_occ].sum(axis=1)
        for i, rel in related.items():
            total = strength[i] * related_share / (1 - related_share)
            for j, _ in rel:
                W[i, j] = total / len(rel)
    rs = W.sum(axis=1, keepdims=True)
    assert (rs > 0).all(), "dangling node"
    P = W / rs
    R = (1 - alpha) * np.linalg.inv(np.eye(n) - alpha * P)
    return R[n_occ:n_occ + n_el, :n_occ]  # element (personalization) rows -> occupation columns


def student_vector(data, riasec, competency):
    v = np.zeros(len(data.elems))
    for name, s in {**riasec, **competency}.items():
        assert data.by_name[name], f"unknown element {name}"
        for j in data.by_name[name]:
            v[j] = s
    return v


def mad_similarity(F, v, mask, n_int):
    """The notebook's baseline: 0.5 * interest fit + 0.5 * competency fit (1 - mean abs diff)."""
    int_fit = 1 - np.abs(F[:, :n_int] - v[:n_int]).mean(axis=1)
    cm = mask.copy()
    cm[:n_int] = False
    comp_fit = 1 - np.abs(np.nan_to_num(F[:, cm]) - v[cm]).mean(axis=1)
    return 0.5 * int_fit + 0.5 * comp_fit


def cosine_similarity(F, v, mask):
    A = np.nan_to_num(F[:, mask])
    b = v[mask]
    return (A @ b) / (np.linalg.norm(A, axis=1) * np.linalg.norm(b) + 1e-12)


def top(scores, data, k=10):
    return [data.title[data.occs[i]] for i in np.argsort(-scores)[:k]]


# ---------------------------------------------------------------- synthetic-student evaluation
def make_students(data, F, n_comp=16, noise=0.10, seed=0):
    """One synthetic student per occupation: its 6 interests + n_comp random competencies, with noise."""
    rng = np.random.default_rng(seed)
    full = np.where(~np.isnan(F).any(axis=1))[0]
    V = np.zeros((len(full), F.shape[1]))
    M = np.zeros_like(V, dtype=bool)
    for r, i in enumerate(full):
        cols = np.concatenate([np.arange(data.n_int),
                               data.n_int + rng.choice(F.shape[1] - data.n_int, n_comp, replace=False)])
        V[r, cols] = np.clip(F[i, cols] + rng.normal(0, noise, len(cols)), 0.01, 1)
        M[r, cols] = True
    return full, V, M


def evaluate(S, true_idx, data, tiers=("Primary-Short", "Primary-Long")):
    """S: students x occupations. Returns Hit@1, Hit@10, MRR and Related-Occupations Recall@10."""
    ranks = np.array([1 + (S[r] > S[r, t]).sum() for r, t in enumerate(true_idx)])
    recalls = []
    for r, t in enumerate(true_idx):
        gt = {j for j, tier in data.related[t] if tier in tiers}
        s = S[r].copy()
        s[t] = -np.inf
        recalls.append(len(gt & set(np.argsort(-s)[:10])) / len(gt))
    return (ranks == 1).mean(), (ranks <= 10).mean(), (1 / ranks).mean(), float(np.mean(recalls))


def eval_methods(data, F, R, full, V, M, with_baselines=True):
    out = {}
    ppr = V @ R
    glob = np.ones(R.shape[0]) @ R
    out["PPR mentah"] = evaluate(ppr, full, data)
    out["PPR / global"] = evaluate(ppr / glob, full, data)
    if with_baselines:
        out["Similarity notebook (MAD)"] = evaluate(
            np.array([mad_similarity(F, V[r], M[r], data.n_int) for r in range(len(V))]), full, data)
        out["Cosine similarity"] = evaluate(
            np.array([cosine_similarity(F, V[r], M[r]) for r in range(len(V))]), full, data)
    return out


def print_eval(results):
    print(f"   {'metode':28s} {'Hit@1':>7s} {'Hit@10':>7s} {'MRR':>7s} {'RelRecall@10':>13s}")
    for name, (h1, h10, mrr, rec) in results.items():
        print(f"   {name:28s} {h1:7.1%} {h10:7.1%} {mrr:7.3f} {rec:13.1%}")


# ---------------------------------------------------------------- main
def main():
    data = Data()
    F = data.features("mean")
    ess_cols = [j for e, j in data.elem_idx.items() if e[0] == "EssentialSkills"]
    n_occ = len(data.occs)
    full_rows = (~np.isnan(F).any(axis=1)).sum()

    print("=" * 78)
    print("A. REPRODUKSI NOTEBOOK (dari RDF resmi)")
    R_nb = ppr_operator(F, 0.85, dup_skill_cols=ess_cols)
    n_nodes = n_occ + len(data.elems) + len(ess_cols)
    n_edges = 2 * (np.count_nonzero(~np.isnan(F)) + np.count_nonzero(~np.isnan(F[:, ess_cols])))
    print(f"node: {n_nodes} (notebook: 1059) | edge: {n_edges:,} (notebook: 247,676)")
    print(f"occupation dengan data lengkap: {full_rows} | hanya punya minat: {n_occ - full_rows}")
    v1 = student_vector(data, *NOTEBOOK_PROFILES["Student 1 (cell 6)"])
    mine = top(v1 @ R_nb, data)
    print(f"top-10 Student 1 identik dengan output notebook: {mine == NOTEBOOK_TOP10_STUDENT1}")
    scores = np.sort(v1 @ R_nb)[::-1]
    print(f"skor PPR peringkat 1 vs 10 vs 100: {scores[0]:.6f} / {scores[9]:.6f} / {scores[99]:.6f}"
          f"  (selisih #1-#10 = {(scores[0] / scores[9] - 1):.1%})")

    lift_nb = (v1 @ R_nb) / (np.ones(R_nb.shape[0]) @ R_nb)
    incomplete = {data.title[data.occs[i]] for i in np.where(np.isnan(F).any(axis=1))[0]}
    print(f"top-10 PPR/global di graph notebook yang ternyata occupation tanpa data kompetensi: "
          f"{len(set(top(lift_nb, data)) & incomplete)}/10")

    # From here on: only the 910 occupations with complete ratings, no duplicated skill nodes.
    data = Data(only_complete=True)
    F = data.features("mean")
    R = ppr_operator(F, 0.85)
    v1 = student_vector(data, *NOTEBOOK_PROFILES["Student 1 (cell 6)"])

    print("\n" + "=" * 78)
    print("B. PPR vs SIMILARITY pada profil siswa di notebook")
    print("   (910 occupation lengkap, tanpa node duplikat, alpha 0.85)")
    glob = np.ones(R.shape[0]) @ R
    ppr_all = {}
    for name, (ri, co) in NOTEBOOK_PROFILES.items():
        v = student_vector(data, ri, co)
        mask = v > 0
        ppr = v @ R
        ppr_all[name] = ppr
        lift = ppr / glob
        mad = mad_similarity(F, v, mask, data.n_int)
        cos = cosine_similarity(F, v, mask)
        print(f"\n--- {name}")
        print(f"   Spearman: PPR~global {spearmanr(ppr, glob)[0]:.3f} | PPR~cosine {spearmanr(ppr, cos)[0]:.3f}"
              f" | PPR/global~cosine {spearmanr(lift, cos)[0]:.3f} | PPR/global~MAD {spearmanr(lift, mad)[0]:.3f}")
        cols = [("PPR mentah", top(ppr, data, 5)), ("PPR / global", top(lift, data, 5)),
                ("Cosine", top(cos, data, 5)), ("MAD (notebook)", top(mad, data, 5))]
        print("   " + " | ".join(f"{h:30s}" for h, _ in cols))
        for k in range(5):
            print("   " + " | ".join(f"{c[k][:30]:30s}" for _, c in cols))
    names = list(ppr_all)
    union = set()
    for nme in names:
        union |= set(np.argsort(-ppr_all[nme])[:10])
    print(f"\n   Gabungan top-10 PPR mentah dari {len(names)} profil: {len(union)} occupation unik (maks {10 * len(names)})")
    union = set()
    for nme in names:
        union |= set(np.argsort(-(ppr_all[nme] / glob))[:10])
    print(f"   Gabungan top-10 PPR/global dari {len(names)} profil: {len(union)} occupation unik")

    print("\n" + "=" * 78)
    print("C. EVALUASI SISWA SINTETIS (910 siswa; tiap siswa = 6 minat + 16 kompetensi acak")
    print("   dari satu occupation, diberi noise sd 0.10). Graph tanpa node duplikat.")
    full, V, M = make_students(data, F)
    print_eval(eval_methods(data, F, R, full, V, M))
    ess = [j for e, j in data.elem_idx.items() if e[0] == "EssentialSkills"]
    print("   (dengan node 'skill:' duplikat seperti di notebook)")
    print_eval(eval_methods(data, F, ppr_operator(F, 0.85, dup_skill_cols=ess), full, V, M, with_baselines=False))
    print(f"   (acak: Hit@10 = {10 / len(data.occs):.1%}, RelRecall@10 = {10 / (len(data.occs) - 1):.1%})")

    print("\n" + "=" * 78)
    print("D. RELATED OCCUPATIONS SEBAGAI EDGE (share = porsi bobot keluar occupation)")
    for share in (0.0, 0.2, 0.5):
        Rr = ppr_operator(F, 0.85, related=data.related, related_share=share)
        print(f" share = {share}")
        print_eval(eval_methods(data, F, Rr, full, V, M, with_baselines=False))

    print("\n" + "=" * 78)
    print("E. VARIAN BOBOT EDGE (alpha 0.85, tanpa duplikat)")
    for mode in ("mean", "IM", "LV", "IMxLV", "LV|IM>=3"):
        Fm = data.features(mode)
        density = np.count_nonzero(np.nan_to_num(Fm)) / Fm.size
        fullm, Vm, Mm = make_students(data, Fm)
        print(f"\n bobot = {mode}  (pasangan berbobot > 0: {density:.1%})")
        print_eval(eval_methods(data, Fm, ppr_operator(Fm, 0.85), fullm, Vm, Mm))

    print("\n" + "=" * 78)
    print("F. SENSITIVITAS ALPHA (bobot mean, tanpa duplikat)")
    base_raw = set(np.argsort(-(v1 @ R))[:10])
    base_lift = set(np.argsort(-((v1 @ R) / (np.ones(R.shape[0]) @ R)))[:10])
    for alpha in (0.15, 0.5, 0.7, 0.85, 0.95):
        Ra = ppr_operator(F, alpha)
        res = eval_methods(data, F, Ra, full, V, M, with_baselines=False)
        p = v1 @ Ra
        g = np.ones(Ra.shape[0]) @ Ra
        o_raw = len(base_raw & set(np.argsort(-p)[:10]))
        o_lift = len(base_lift & set(np.argsort(-(p / g))[:10]))
        print(f" alpha = {alpha}: top-10 Student 1 sama dgn alpha 0.85 -> mentah {o_raw}/10, /global {o_lift}/10")
        print_eval(res)

    print("\n" + "=" * 78)
    print("G. SKALA SKILL GAP (Physicists, 19-2012.00)")
    print(f"   {'elemen':26s} {'IM(1-5)':>8s} {'LV(0-7)':>8s} {'notebook':>9s} {'LV/7':>6s} {'siswa':>6s}"
          f" {'gap nb':>7s} {'gap LV':>7s}")
    comp = NOTEBOOK_PROFILES["Student 1 (cell 6)"][1]
    for (soc, dom, el), sc in sorted(data.raw.items()):
        if soc == "19-2012.00" and el in comp and dom != "CareerInterestTypes":
            nb = (sc["IM"] + sc["LV"]) / 2 / 7
            lv = sc["LV"] / 7
            print(f"   {el:26s} {sc['IM']:8.2f} {sc['LV']:8.2f} {nb:9.3f} {lv:6.3f} {comp[el]:6.2f}"
                  f" {max(nb - comp[el], 0):7.3f} {max(lv - comp[el], 0):7.3f}")


if __name__ == "__main__":
    main()
