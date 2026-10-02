"""Check two things on the graph built from the official O*NET 31.0 RDF:

1. How dense is the occupation <-> element bipartite graph?
2. How much does Personalized PageRank differ from plain (global) PageRank?

Edge weight = rating normalised to 0..1 (IM: 1..5, OI: 1..7).
Run scripts/flatten_rdf.py first.
"""
import csv
from pathlib import Path

import numpy as np
from scipy.stats import spearmanr

ROOT = Path(__file__).resolve().parent.parent
ALPHA = 0.85
SCALE_RANGE = {"IM": (1.0, 5.0), "OI": (1.0, 7.0)}

# Profile from the context doc (section 6) plus two contrasting ones.
PROFILES = {
    "Investigative Technical": {
        "Realistic": 0.65, "Investigative": 0.90, "Artistic": 0.40,
        "Social": 0.50, "Enterprising": 0.35, "Conventional": 0.60,
        "Deductive Reasoning": 0.85, "Inductive Reasoning": 0.80,
        "Mathematical Reasoning": 0.75, "Critical Thinking": 0.90,
        "Complex Problem Solving": 0.85, "Systems Analysis": 0.80,
        "Programming": 0.85, "Technology Design": 0.80,
    },
    "Artistic Social": {
        "Realistic": 0.20, "Investigative": 0.35, "Artistic": 0.90,
        "Social": 0.85, "Enterprising": 0.45, "Conventional": 0.25,
        "Originality": 0.90, "Fluency of Ideas": 0.85, "Oral Expression": 0.80,
        "Social Perceptiveness": 0.85, "Active Listening": 0.85,
        "Speaking": 0.80, "Service Orientation": 0.75, "Instructing": 0.70,
    },
    "Realistic Hands-on": {
        "Realistic": 0.90, "Investigative": 0.40, "Artistic": 0.20,
        "Social": 0.30, "Enterprising": 0.30, "Conventional": 0.50,
        "Manual Dexterity": 0.85, "Arm-Hand Steadiness": 0.85,
        "Multilimb Coordination": 0.80, "Repairing": 0.90,
        "Equipment Maintenance": 0.85, "Troubleshooting": 0.80,
        "Operation and Control": 0.80, "Installation": 0.75,
    },
}


def load_graph():
    occ_title, edges = {}, {}
    with open(ROOT / "data" / "onet_ratings.csv", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            if r["scale_id"] not in SCALE_RANGE:
                continue
            lo, hi = SCALE_RANGE[r["scale_id"]]
            w = (float(r["value"]) - lo) / (hi - lo)
            occ_title[r["soc_code"]] = r["title"]
            edges[(r["soc_code"], (r["domain"], r["element_name"]))] = w
    return occ_title, edges


def pagerank(W, personalization, alpha=ALPHA, tol=1e-12, max_iter=1000):
    """Power iteration on a symmetric weight matrix (same model as networkx.pagerank)."""
    P = W / W.sum(axis=1, keepdims=True)
    v = personalization / personalization.sum()
    x = v.copy()
    for _ in range(max_iter):
        x_new = alpha * (x @ P) + (1 - alpha) * v
        if np.abs(x_new - x).sum() < tol:
            return x_new
        x = x_new
    return x


def main():
    occ_title, edges = load_graph()
    occs = sorted(occ_title)
    elems = sorted({e for _, e in edges})
    idx = {n: i for i, n in enumerate(occs + elems)}
    n_occ, n = len(occs), len(occs) + len(elems)

    W = np.zeros((n, n))
    for (o, e), w in edges.items():
        W[idx[o], idx[e]] = W[idx[e], idx[o]] = w

    nonzero = sum(1 for w in edges.values() if w > 0)
    print("=== 1. Kepadatan graph")
    print(f"occupation nodes : {n_occ}")
    print(f"element nodes    : {len(elems)}")
    print(f"pasangan mungkin : {n_occ * len(elems):,}")
    print(f"punya rating     : {len(edges):,} ({len(edges) / (n_occ * len(elems)):.1%})")
    print(f"bobot > 0        : {nonzero:,} ({nonzero / (n_occ * len(elems)):.1%})")

    name_to_elems = {}
    for e in elems:
        name_to_elems.setdefault(e[1], []).append(e)

    global_pr = pagerank(W, np.ones(n))[:n_occ]
    strength = W.sum(axis=1)[:n_occ]
    top_global = np.argsort(-global_pr)[:10]

    print("\n=== 2. PageRank global (tanpa personalization), top 10")
    for rank, i in enumerate(top_global, 1):
        print(f"{rank:2d}. {occ_title[occs[i]]}")
    print(f"Spearman(global PR, total bobot edge occupation) = {spearmanr(global_pr, strength)[0]:.3f}")

    results = {}
    for name, profile in PROFILES.items():
        v = np.zeros(n)
        for el_name, weight in profile.items():
            targets = name_to_elems.get(el_name)
            if not targets:
                raise SystemExit(f"Elemen tidak ditemukan di O*NET: {el_name}")
            for e in targets:
                v[idx[e]] = weight
        ppr = pagerank(W, v)[:n_occ]
        results[name] = ppr
        top = np.argsort(-ppr)[:10]
        lift_top = np.argsort(-(ppr / global_pr))[:10]
        print(f"\n=== Profil: {name}")
        print(f"Spearman(PPR, global PR) = {spearmanr(ppr, global_pr)[0]:.3f}"
              f" | top-10 sama dengan global: {len(set(top) & set(top_global))}/10")
        print(f"{'PPR mentah':45s} | PPR / global PR")
        for a, b in zip(top, lift_top):
            print(f"{occ_title[occs[a]][:45]:45s} | {occ_title[occs[b]][:45]}")

    names = list(results)
    print("\n=== 3. Irisan top-10 antar profil (PPR mentah)")
    for i in range(len(names)):
        for j in range(i + 1, len(names)):
            a = set(np.argsort(-results[names[i]])[:10])
            b = set(np.argsort(-results[names[j]])[:10])
            rho = spearmanr(results[names[i]], results[names[j]])[0]
            print(f"{names[i]} vs {names[j]}: {len(a & b)}/10 sama, Spearman = {rho:.3f}")


if __name__ == "__main__":
    main()
