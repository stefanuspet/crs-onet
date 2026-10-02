"""Can adaptive questioning reach the same quality with fewer questions?

Stage 1: the student's six RIASEC scores (from the 60-item questionnaire).
Stage 2: the student rates interest areas one at a time (41 available).
  - adaptive: ask next the area on which the currently most likely occupations disagree most
  - fixed:    always the same order (areas that vary most across all occupations first)
  - random:   random order

Occupations are scored by how close their profile is to the answers so far (Gaussian likelihood).
Synthetic students: noisy copy of one occupation's interest profile.
"""
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from crs import load  # noqa: E402

SIGMA = 0.15     # assumed answer noise in the scoring model
NOISE = 0.10     # actual noise used to generate the synthetic students
CHECKPOINTS = (0, 3, 5, 8, 10, 15, 20, 41)


def evaluate(final_scores, d):
    hits, recalls = [], []
    for i, s in enumerate(final_scores):
        hits.append((s > s[i]).sum() < 10)
        s = s.copy()
        s[i] = -np.inf
        primary = set(d.related.get(i, [])[:10])
        if primary:
            recalls.append(len(primary & set(np.argsort(-s)[:10])) / len(primary))
    return np.mean(hits), np.mean(recalls)


def main():
    d = load()
    R = (d.riasec - 1) / 6
    A = (d.area_scores - 1) / 6
    rng = np.random.default_rng(0)
    Rs = np.clip(R + rng.normal(0, NOISE, R.shape), 0, 1)
    As = np.clip(A + rng.normal(0, NOISE, A.shape), 0, 1)
    n, m = A.shape
    fixed_order = list(np.argsort(-A.var(axis=0)))

    results = {mode: {k: [] for k in CHECKPOINTS} for mode in ("adaptive", "fixed", "random")}
    for mode in results:
        for i in range(n):
            loglik = -((R - Rs[i]) ** 2).sum(axis=1) / (2 * SIGMA ** 2)
            remaining = list(range(m))
            order = list(rng.permutation(m)) if mode == "random" else fixed_order
            for asked in range(m + 1):
                if asked in CHECKPOINTS:
                    results[mode][asked].append(loglik.copy())
                if asked == m:
                    break
                if mode == "adaptive":
                    p = np.exp(loglik - loglik.max())
                    p /= p.sum()
                    mean = p @ A[:, remaining]
                    var = p @ (A[:, remaining] - mean) ** 2      # disagreement among likely occupations
                    j = remaining[int(np.argmax(var))]
                else:
                    j = next(a for a in order if a in remaining)
                remaining.remove(j)
                loglik -= (A[:, j] - As[i, j]) ** 2 / (2 * SIGMA ** 2)

    print(f"{n} siswa sintetis. Angka: Hit@10 / RelRecall@10")
    print(f"{'pertanyaan bidang':>18s} | {'adaptif':>15s} | {'urutan tetap':>15s} | {'acak':>15s}")
    for k in CHECKPOINTS:
        cells = []
        for mode in ("adaptive", "fixed", "random"):
            h, r = evaluate(results[mode][k], d)
            cells.append(f"{h:6.1%} / {r:5.1%}")
        print(f"{k:>18d} | " + " | ".join(f"{c:>15s}" for c in cells))


if __name__ == "__main__":
    main()
