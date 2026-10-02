"""Load the O*NET 31.0 tables produced by scripts/flatten_rdf.py."""
import csv
from collections import defaultdict
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import numpy as np

DATA_DIR = Path(__file__).resolve().parent.parent / "data"

RIASEC = ["Realistic", "Investigative", "Artistic", "Social", "Enterprising", "Conventional"]
COMPETENCY_DOMAINS = ["Abilities", "Knowledge", "EssentialSkills", "TransferableSkills"]
JOB_ZONE_NAMES = {
    2: "Job Zone 1-2: sedikit persiapan (SMA/SMK atau pelatihan singkat)",
    3: "Job Zone 3: persiapan menengah (pelatihan vokasi / D3)",
    4: "Job Zone 4: persiapan tinggi (umumnya S1)",
    5: "Job Zone 5: persiapan sangat tinggi (umumnya S2/S3)",
}


@dataclass
class OnetData:
    codes: list            # O*NET-SOC codes, row order of every matrix below
    titles: list
    descriptions: list
    job_zones: np.ndarray  # 2..5 (O*NET 31.0 merges zones 1 and 2)
    riasec: np.ndarray     # occupations x 6, Occupational Interest scale 1..7
    areas: list            # the 41 Specific Interest Area names
    area_scores: np.ndarray        # occupations x 41, scale 1..7
    competencies: list             # (domain, element name)
    importance: np.ndarray         # occupations x competencies, scale 1..5
    level: np.ndarray              # occupations x competencies, scale 0..7
    related: dict                  # row index -> [row index, ...] ordered by O*NET's related index

    def index_of(self, code_or_title):
        if code_or_title in self.codes:
            return self.codes.index(code_or_title)
        return self.titles.index(code_or_title)


@lru_cache(maxsize=1)
def load(data_dir=DATA_DIR):
    """Occupations that lack interest or competency ratings are left out (878 remain in O*NET 31.0)."""
    ratings = defaultdict(dict)  # soc -> {(domain, element, scale): value}
    with open(Path(data_dir) / "onet_ratings.csv", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            ratings[r["soc_code"]][(r["domain"], r["element_name"], r["scale_id"])] = float(r["value"])

    areas = sorted({k[1] for v in ratings.values() for k in v if k[0] == "SpecificInterestAreas"})
    competencies = sorted({(k[0], k[1]) for v in ratings.values() for k in v if k[0] in COMPETENCY_DOMAINS})
    required = ([("CareerInterestTypes", n, "OI") for n in RIASEC]
                + [("SpecificInterestAreas", a, "OI") for a in areas]
                + [(d, e, s) for d, e in competencies for s in ("IM", "LV")])

    meta = {}
    with open(Path(data_dir) / "onet_occupations.csv", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            meta[r["soc_code"]] = r

    codes = sorted(c for c, v in ratings.items()
                   if all(k in v for k in required) and meta[c]["job_zone"])
    row = {c: i for i, c in enumerate(codes)}

    related = defaultdict(list)
    with open(Path(data_dir) / "onet_related_occupations.csv", encoding="utf-8") as f:
        links = sorted(csv.DictReader(f), key=lambda r: (r["soc_code"], int(r["rank"])))
    for r in links:
        if r["soc_code"] in row and r["related_soc_code"] in row:
            related[row[r["soc_code"]]].append(row[r["related_soc_code"]])

    def matrix(keys):
        return np.array([[ratings[c][k] for k in keys] for c in codes])

    return OnetData(
        codes=codes,
        titles=[meta[c]["title"] for c in codes],
        descriptions=[meta[c]["description"] for c in codes],
        job_zones=np.array([int(meta[c]["job_zone"]) for c in codes]),
        riasec=matrix([("CareerInterestTypes", n, "OI") for n in RIASEC]),
        areas=areas,
        area_scores=matrix([("SpecificInterestAreas", a, "OI") for a in areas]),
        competencies=competencies,
        importance=matrix([(d, e, "IM") for d, e in competencies]),
        level=matrix([(d, e, "LV") for d, e in competencies]),
        related=dict(related),
    )
