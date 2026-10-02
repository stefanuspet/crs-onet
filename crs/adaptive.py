"""Adaptive interest questionnaire: each answer decides which question comes next.

Question pool (all from O*NET 31.0):
    item : the 60 Interest Profiler Short Form activities
    area : the 41 Specific Interest Areas
    dwa  : Detailed Work Activities shared by at least two occupations

Every answer is on a five-point scale. P(answer | occupation) is a discretised Gaussian around the
value O*NET gives that occupation, mixed with a small probability of a careless answer. Answers
update P(occupation) with Bayes' rule (no occupation is ever eliminated), and the next question is
the one with the largest information gain. Asking stops once few occupations remain plausible.

The numeric settings below are provisional; they have only been checked on synthetic students
(scripts/adaptive_questionnaire.py) and should be re-estimated from pilot data.
"""
import csv
from collections import defaultdict
from dataclasses import dataclass
from functools import lru_cache

import numpy as np

from . import i18n, questionnaire
from .data import DATA_DIR, RIASEC, load

VALUES = np.array([0.0, 0.25, 0.5, 0.75, 1.0])
SIGMA = {"item": 0.30, "area": 0.20, "dwa": 0.30}  # assumed noise of one answer
DWA_YES, DWA_NO = 0.80, 0.30                       # expected answer if the occupation has / lacks the activity
CARELESS = 0.10                                    # probability that an answer says nothing about the student
MIN_QUESTIONS, MAX_QUESTIONS = 20, 80
STOP_CANDIDATES = 5                                # stop when exp(entropy) of P(occupation) is at most this
# A student who answers "suka" or "sangat suka" to at least this share of all questions likes nearly
# everything. Synthetic single-occupation students stay at or below 0.85.
BROAD_LIKING = 0.90
# Consistency check: at the end, some earlier questions are asked again. The repeats do not change
# the result; they only show whether the student answers the same question the same way.
CONSISTENCY_QUESTIONS = 8
# Mean change (in answer steps, 0..4) above which the answers count as inconsistent. In simulation this
# flags 89% of random responders, 0% of consistent students and 12% of fairly noisy ones.
CONSISTENCY_LIMIT = 1.25
KINDS = ("item", "area", "dwa")
KIND_LABEL = {"item": "Kegiatan", "area": "Bidang", "dwa": "Aktivitas kerja"}


def _answer_probs(mu, sigma):
    logp = -(VALUES - np.asarray(mu)[..., None]) ** 2 / (2 * sigma ** 2)
    p = np.exp(logp - logp.max(axis=-1, keepdims=True))
    p /= p.sum(axis=-1, keepdims=True)
    return (1 - CARELESS) * p + CARELESS / len(VALUES)


def _entropy(p):
    return -(p * np.log(np.clip(p, 1e-300, None))).sum(axis=-1)


@dataclass(frozen=True)
class Question:
    kind: str     # "item", "area" or "dwa"
    index: int
    text: str
    repeat: bool = False   # asked a second time, as a consistency check


class QuestionPool:
    """Answer-probability tables for every question; built once and shared by all sessions."""

    def __init__(self, data=None):
        self.data = d = data or load()
        self.items = questionnaire.items()
        self.item_type = np.array([RIASEC.index(it.riasec) for it in self.items])

        row = {c: i for i, c in enumerate(d.codes)}
        names, members = {}, defaultdict(set)
        with open(DATA_DIR / "onet_dwa.csv", encoding="utf-8") as f:
            for r in csv.DictReader(f):
                if r["soc_code"] in row:
                    names[r["dwa_id"]] = r["dwa_name"]
                    members[r["dwa_id"]].add(row[r["soc_code"]])
        # An activity found in a single occupation would identify it outright; keep shared ones.
        ids = sorted(k for k, v in members.items() if len(v) >= 2)
        self.dwa_names = [i18n.activity(k, names[k]) for k in ids]
        self.has_dwa = np.zeros((len(d.codes), len(ids)))
        for j, k in enumerate(ids):
            self.has_dwa[list(members[k]), j] = 1.0
        self.size = {"item": len(self.items), "area": len(d.areas), "dwa": len(ids)}

        self.p_type = _answer_probs((d.riasec - 1) / 6, SIGMA["item"])       # occupation x type x 5
        self.p_area = _answer_probs((d.area_scores - 1) / 6, SIGMA["area"])  # occupation x area x 5
        self.p_yes = _answer_probs(DWA_YES, SIGMA["dwa"])
        self.p_no = _answer_probs(DWA_NO, SIGMA["dwa"])
        self.h_type, self.h_area = _entropy(self.p_type), _entropy(self.p_area)
        self.h_yes, self.h_no = _entropy(self.p_yes), _entropy(self.p_no)

    def question(self, kind, j):
        if kind == "item":
            text = self.items[j].text_id
        elif kind == "area":
            text = questionnaire.AREA_LABELS[self.data.areas[j]]
        else:
            text = self.dwa_names[j]
        return Question(kind, j, text)

    def info_gain(self, kind, p):
        """Mutual information between the answer and the occupation, for every question of a kind."""
        if kind == "item":
            pred = np.einsum("o,ota->ta", p, self.p_type)
            return (_entropy(pred) - p @ self.h_type)[self.item_type]
        if kind == "area":
            pred = np.einsum("o,oja->ja", p, self.p_area)
            return _entropy(pred) - p @ self.h_area
        share = p @ self.has_dwa
        pred = share[:, None] * self.p_yes + (1 - share)[:, None] * self.p_no
        return _entropy(pred) - (share * self.h_yes + (1 - share) * self.h_no)

    def log_likelihood(self, kind, j, answer):
        if kind == "item":
            return np.log(self.p_type[:, self.item_type[j], answer])
        if kind == "area":
            return np.log(self.p_area[:, j, answer])
        return np.where(self.has_dwa[:, j] > 0, np.log(self.p_yes[answer]), np.log(self.p_no[answer]))


@lru_cache(maxsize=1)
def default_pool():
    return QuestionPool()


class Session:
    """One student's run through the questionnaire.

        s = Session()
        while (q := s.next_question()) is not None:
            s.answer(q, value)        # value 0..4
        s.ranking()
    """

    def __init__(self, pool=None):
        self.pool = pool or default_pool()
        self._logp = np.zeros(len(self.pool.data.codes))
        self._asked = {k: np.zeros(self.pool.size[k], dtype=bool) for k in KINDS}
        self.history = []   # [(Question, answer)]
        self.repeats = []   # [(Question, first answer, second answer)]

    @property
    def probabilities(self):
        p = np.exp(self._logp - self._logp.max())
        return p / p.sum()

    @property
    def candidates(self):
        """Effective number of occupations that are still plausible."""
        return float(np.exp(_entropy(self.probabilities)))

    @property
    def reached_limit(self):
        """The question limit was hit while many occupations were still plausible."""
        return len(self.history) >= MAX_QUESTIONS and self.candidates > STOP_CANDIDATES

    @property
    def outcome(self):
        """'tidak_konsisten' : repeated questions were answered very differently the second time
        'jelas'       : the answers narrowed down to a small group of occupations
        'beragam'     : diverse interests: the student likes nearly everything asked, or the limit
                        was reached with a fair number of likes
        'belum_jelas' : the limit was reached and the student liked very little"""
        gap = self.consistency_gap
        if gap is not None and gap > CONSISTENCY_LIMIT:
            return "tidak_konsisten"
        liked = np.mean([a >= 3 for _, a in self.history]) if self.history else 0.0
        if liked >= BROAD_LIKING:
            return "beragam"
        if self.reached_limit:
            return "beragam" if liked >= 0.25 else "belum_jelas"
        return "jelas"

    def liked_areas(self):
        """Interest areas the student answered 'suka' or 'sangat suka' to, best-liked first."""
        liked = [(a, q.text) for q, a in self.history if q.kind == "area" and a >= 3]
        return [text for _, text in sorted(liked, key=lambda x: -x[0])]

    def reasons(self, occupation, limit=3):
        """Why an occupation fits this student: (liked areas that are strong for it,
        liked work activities that it involves)."""
        pool = self.pool
        areas = [q.text for q, a in self.history
                 if q.kind == "area" and a >= 3 and pool.data.area_scores[occupation, q.index] >= 4.0]
        activities = [q.text for q, a in self.history
                      if q.kind == "dwa" and a >= 3 and pool.has_dwa[occupation, q.index] > 0]
        return areas[:limit], activities[:limit]

    def _to_repeat(self):
        """Earlier questions to ask again: strongest answers first (a careless answer is least likely
        to land on the same extreme twice), then in the order they were asked."""
        order = sorted(range(len(self.history)), key=lambda k: (-abs(self.history[k][1] - 2), k))
        return [self.history[k] for k in order[:CONSISTENCY_QUESTIONS]]

    @property
    def consistency_gap(self):
        """Mean change between first and second answer, in answer steps (0 = identical). None if unchecked."""
        if not self.repeats:
            return None
        return float(np.mean([abs(a - b) for _, a, b in self.repeats]))

    def next_question(self):
        n = len(self.history)
        if n >= MAX_QUESTIONS or (n >= MIN_QUESTIONS and self.candidates <= STOP_CANDIDATES):
            pending = self._to_repeat()[len(self.repeats):]
            if not pending:
                return None
            q = pending[0][0]
            return Question(q.kind, q.index, q.text, repeat=True)
        p, best = self.probabilities, None
        for kind in KINDS:
            gain = np.where(self._asked[kind], -np.inf, self.pool.info_gain(kind, p))
            j = int(np.argmax(gain))
            if best is None or gain[j] > best[0]:
                best = (gain[j], kind, j)
        return self.pool.question(best[1], best[2])

    def answer(self, question, value):
        if value not in range(len(VALUES)):
            raise ValueError(f"Jawaban harus 0..{len(VALUES) - 1}, bukan {value!r}")
        if question.repeat:
            first = self._to_repeat()[len(self.repeats)]
            if (first[0].kind, first[0].index) != (question.kind, question.index):
                raise ValueError("Bukan pertanyaan ulang yang sedang ditunggu")
            self.repeats.append((first[0], first[1], value))
            return
        if self._asked[question.kind][question.index]:
            raise ValueError("Pertanyaan ini sudah dijawab")
        self._asked[question.kind][question.index] = True
        self._logp = self._logp + self.pool.log_likelihood(question.kind, question.index, value)
        self.history.append((question, value))

    def ranking(self, top_n=10, max_job_zone=None):
        """[(occupation row index, probability)], most likely first."""
        d, p = self.pool.data, self.probabilities
        order = [i for i in np.argsort(-p) if max_job_zone is None or d.job_zones[i] <= max_job_zone]
        return [(int(i), float(p[i])) for i in order[:top_n]]
