"""Which student input gives the best recommendations when only interests are measured?

Compares, on synthetic students (noisy copy of one occupation's interest profile):
  - 6 RIASEC scores (what the O*NET Interest Profiler produces)
  - 41 Specific Interest Areas, fully rated
  - RIASEC + "pick your top-k areas" (a short, realistic second question)

Metrics: Hit@10 (source occupation found) and Recall@10 of O*NET primary Related Occupations.
Run scripts/flatten_rdf.py first.
"""
import csv
from collections import defaultdict
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
RIASEC = ["Realistic", "Investigative", "Artistic", "Social", "Enterprising", "Conventional"]


def load():
    val = defaultdict(dict)
    with open(ROOT / "data" / "onet_ratings.csv", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            if r["scale_id"] == "OI":
                val[r["soc_code"]][(r["domain"], r["element_name"])] = (float(r["value"]) - 1) / 6
    areas = sorted({k[1] for v in val.values() for k in v if k[0] == "SpecificInterestAreas"})
    occs = sorted(o for o, v in val.items() if len(v) == len(RIASEC) + len(areas))
    R = np.array([[val[o][("CareerInterestTypes", n)] for n in RIASEC] for o in occs])
    A = np.array([[val[o][("SpecificInterestAreas", n)] for n in areas] for o in occs])
    idx = {o: i for i, o in enumerate(occs)}
    related = defaultdict(set)
    with open(ROOT / "data" / "onet_related_occupations.csv", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            if r["tier"].startswith("Primary") and r["soc_code"] in idx and r["related_soc_code"] in idx:
                related[idx[r["soc_code"]]].add(idx[r["related_soc_code"]])
    return occs, areas, R, A, related


def zrows(X):
    X = X - X.mean(axis=1, keepdims=True)
    return X / (np.linalg.norm(X, axis=1, keepdims=True) + 1e-12)


def pearson(S, O):       # students x occupations profile correlation
    return zrows(S) @ zrows(O).T


def cosine(S, O):
    return (S / np.linalg.norm(S, axis=1, keepdims=True)) @ (O / np.linalg.norm(O, axis=1, keepdims=True)).T


def neg_mad(S, O):
    return -np.abs(S[:, None, :] - O[None, :, :]).mean(axis=2)


def evaluate(S, related):
    n = len(S)
    ranks = np.array([1 + (S[i] > S[i, i]).sum() for i in range(n)])
    rec = []
    for i in range(n):
        if not related[i]:
            continue
        s = S[i].copy()
        s[i] = -np.inf
        rec.append(len(related[i] & set(np.argsort(-s)[:10])) / len(related[i]))
    return (ranks <= 10).mean(), np.mean(rec)


def main():
    occs, areas, R, A, related = load()
    print(f"{len(occs)} occupation, {len(areas)} specific interest areas")
    print(f"{'input siswa / metode':52s} {'Hit@10':>7s} {'RelRecall@10':>13s}")
    for noise in (0.10, 0.20):
        rng = np.random.default_rng(0)
        Rs = np.clip(R + rng.normal(0, noise, R.shape), 0, 1)
        As = np.clip(A + rng.normal(0, noise, A.shape), 0, 1)
        print(f"-- noise sd {noise}")
        rows = {
            "RIASEC (6): Pearson": pearson(Rs, R),
            "RIASEC (6): cosine": cosine(Rs, R),
            "RIASEC (6): 1 - mean abs diff": neg_mad(Rs, R),
            "41 bidang, dinilai semua: Pearson": pearson(As, A),
            "RIASEC + 41 bidang: rata-rata dua Pearson": (pearson(Rs, R) + pearson(As, A)) / 2,
        }
        for k in (3, 5, 8):
            picks = np.zeros_like(As)
            np.put_along_axis(picks, np.argsort(-As, axis=1)[:, :k], 1.0, axis=1)
            area_fit = (picks @ zrows(A).T) / np.sqrt(k)   # how strongly the picked areas stand out for each occupation
            rows[f"RIASEC + pilih {k} bidang favorit"] = pearson(Rs, R) + area_fit
        picks = np.zeros_like(As)
        np.put_along_axis(picks, np.argsort(-As, axis=1)[:, :5], 1.0, axis=1)
        rows["hanya pilih 5 bidang favorit"] = picks @ zrows(A).T
        for name, S in rows.items():
            h, r = evaluate(S, related)
            print(f"{name:52s} {h:7.1%} {r:13.1%}")
    print(f"(acak: {10 / len(occs):.1%})")


if __name__ == "__main__":
    main()
