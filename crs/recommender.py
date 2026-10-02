"""Career recommendation for high-school students, based on O*NET 31.0.

Ranking uses interests only:
    score = Pearson(student RIASEC, occupation RIASEC) + fit of the student's favourite interest areas

Competencies do not affect the ranking. They are reported per occupation as a skill gap,
i.e. what the student would need to develop to get there.
"""
from dataclasses import dataclass, field

import numpy as np

from .data import JOB_ZONE_NAMES, RIASEC, OnetData, load

IMPORTANT = 3.0   # O*NET Importance scale: 3 = "Important"
# Cut-offs O*NET's own Interest Profiler uses for the RIASEC profile correlation
# (Gregory & Lewis, 2016, "Linking Client Assessment Profiles to O*NET Occupational Profiles").
BEST_FIT, GREAT_FIT = 0.729, 0.608
LEVEL_MAX = 7.0   # O*NET Level scale runs 0..7


@dataclass
class SkillGap:
    domain: str
    name: str
    importance: float      # 1..5
    required: float        # occupation's required level, 0..1
    student: float | None  # student's level, 0..1 (None = not assessed)

    @property
    def gap(self):
        return None if self.student is None else max(self.required - self.student, 0.0)


@dataclass
class Recommendation:
    rank: int
    code: str
    title: str
    description: str
    score: float
    interest_fit: float     # Pearson correlation with the occupation's RIASEC profile, -1..1
    fit_label: str
    area_fit: float
    job_zone: int
    job_zone_name: str
    top_interests: list     # the occupation's three strongest RIASEC types
    matched_areas: list     # the student's favourite areas that are strong for this occupation
    related: list = field(default_factory=list)      # titles of similar occupations
    skill_gaps: list = field(default_factory=list)   # [SkillGap], most important first


def fit_label(r):
    if r >= BEST_FIT:
        return "Sangat cocok"
    if r >= GREAT_FIT:
        return "Cocok"
    return "Cukup cocok" if r >= 0 else "Kurang cocok"


def _standardise_rows(X):
    X = X - X.mean(axis=1, keepdims=True)
    norm = np.linalg.norm(X, axis=1, keepdims=True)
    return np.divide(X, norm, out=np.zeros_like(X), where=norm > 0)


class Recommender:
    def __init__(self, data: OnetData | None = None):
        self.data = data or load()
        self._riasec_z = _standardise_rows(self.data.riasec)
        self._area_z = _standardise_rows(self.data.area_scores)

    def scores(self, riasec, favourite_areas=()):
        """Return (total, interest_fit, area_fit) arrays over all occupations."""
        d = self.data
        missing = [n for n in RIASEC if n not in riasec]
        if missing:
            raise ValueError(f"Skor RIASEC belum lengkap: {missing}")
        unknown = [a for a in favourite_areas if a not in d.areas]
        if unknown:
            raise ValueError(f"Bidang minat tidak dikenal: {unknown}")

        student = _standardise_rows(np.array([[float(riasec[n]) for n in RIASEC]]))[0]
        interest_fit = self._riasec_z @ student
        area_fit = np.zeros(len(d.codes))
        if favourite_areas:
            cols = [d.areas.index(a) for a in favourite_areas]
            area_fit = self._area_z[:, cols].sum(axis=1) / np.sqrt(len(cols))
        return interest_fit + area_fit, interest_fit, area_fit

    def recommend(self, riasec, favourite_areas=(), competencies=None, max_job_zone=None, top_n=10):
        """riasec: {type: score} on any scale. favourite_areas: names from data.areas (3-5 works best).
        competencies: optional {element name: level 0..1}, used only for the skill gap.
        max_job_zone: 2..5, hide occupations that need more preparation than this."""
        d = self.data
        total, interest_fit, area_fit = self.scores(riasec, favourite_areas)
        eligible = np.ones(len(d.codes), dtype=bool) if max_job_zone is None else d.job_zones <= max_job_zone
        order = [i for i in np.argsort(-total) if eligible[i]][:top_n]

        results = []
        for rank, i in enumerate(order, 1):
            zone = int(d.job_zones[i])
            results.append(Recommendation(
                rank=rank, code=d.codes[i], title=d.titles[i], description=d.descriptions[i],
                score=float(total[i]), interest_fit=float(interest_fit[i]), fit_label=fit_label(interest_fit[i]),
                area_fit=float(area_fit[i]),
                job_zone=zone, job_zone_name=JOB_ZONE_NAMES[zone],
                top_interests=[RIASEC[j] for j in np.argsort(-d.riasec[i])[:3]],
                matched_areas=[a for a in favourite_areas
                               if self._area_z[i, d.areas.index(a)] > 0],
                related=[d.titles[j] for j in d.related.get(i, [])[:5]],
                skill_gaps=self.skill_gaps(i, competencies),
            ))
        return results

    def skill_gaps(self, occupation, competencies=None, limit=10):
        """Competencies that are important for the occupation (Importance >= 3), most important first.
        Required level is the O*NET Level scale / 7."""
        d = self.data
        i = occupation if isinstance(occupation, (int, np.integer)) else d.index_of(occupation)
        competencies = competencies or {}
        gaps = [SkillGap(domain=dom, name=name, importance=float(d.importance[i, j]),
                         required=float(d.level[i, j]) / LEVEL_MAX, student=competencies.get(name))
                for j, (dom, name) in enumerate(d.competencies) if d.importance[i, j] >= IMPORTANT]
        gaps.sort(key=lambda g: (-g.importance, -g.required))
        return gaps[:limit]
