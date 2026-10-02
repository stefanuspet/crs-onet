"""Extra occupation details shown on the detail page: required education, work styles, software.

Read from the tables produced by scripts/flatten_rdf.py.
"""
import csv
from collections import defaultdict
from functools import lru_cache

from .data import DATA_DIR

# O*NET's twelve "Required Level of Education" categories, with the closest Indonesian equivalents.
EDUCATION_LABELS = {
    1: "Di bawah SMA",
    2: "SMA/SMK atau sederajat",
    3: "Sertifikat setelah SMA (kursus atau pelatihan)",
    4: "Kuliah tanpa gelar",
    5: "Diploma (D2/D3)",
    6: "Sarjana (S1/D4)",
    7: "Sertifikat setelah S1",
    8: "Magister (S2)",
    9: "Sertifikat setelah S2",
    10: "Pendidikan profesi tingkat doktor (misalnya dokter)",
    11: "Doktor (S3)",
    12: "Pascadoktoral",
}

WORK_STYLE_LABELS = {
    "Achievement Orientation": "Orientasi Prestasi",
    "Adaptability": "Kemampuan Beradaptasi",
    "Attention to Detail": "Ketelitian",
    "Cautiousness": "Kehati-hatian",
    "Cooperation": "Kerja Sama",
    "Dependability": "Dapat Diandalkan",
    "Empathy": "Empati",
    "Humility": "Kerendahan Hati",
    "Initiative": "Inisiatif",
    "Innovation": "Inovasi",
    "Integrity": "Integritas",
    "Intellectual Curiosity": "Rasa Ingin Tahu",
    "Leadership Orientation": "Jiwa Kepemimpinan",
    "Optimism": "Optimisme",
    "Perseverance": "Ketekunan",
    "Self-Confidence": "Percaya Diri",
    "Self-Control": "Pengendalian Diri",
    "Sincerity": "Ketulusan",
    "Social Orientation": "Suka Bergaul",
    "Stress Tolerance": "Tahan Tekanan",
    "Tolerance for Ambiguity": "Toleransi terhadap Ketidakpastian",
}


def _read(name):
    with open(DATA_DIR / name, encoding="utf-8") as f:
        yield from csv.DictReader(f)


@lru_cache(maxsize=1)
def _education():
    table = defaultdict(list)
    for r in _read("onet_education.csv"):
        table[r["soc_code"]].append((int(r["category"]), float(r["percent"])))
    return table


@lru_cache(maxsize=1)
def _work_styles():
    table = defaultdict(list)
    for r in _read("onet_work_styles.csv"):
        table[r["soc_code"]].append((r["style"], float(r["impact"])))
    return table


@lru_cache(maxsize=1)
def _software():
    table = defaultdict(list)
    for r in _read("onet_software.csv"):
        table[r["soc_code"]].append((r["software"], r["in_demand"] == "true", r["hot_technology"] == "true"))
    return table


def education(code, min_percent=5.0, limit=4):
    """[(label, percent of workers who say this level is required)], largest first."""
    rows = sorted(_education().get(code, []), key=lambda x: -x[1])
    return [(EDUCATION_LABELS[c], round(p)) for c, p in rows if p >= min_percent][:limit]


def work_styles(code, limit=5):
    """The work styles with the largest positive impact for this occupation."""
    rows = sorted(_work_styles().get(code, []), key=lambda x: -x[1])
    return [WORK_STYLE_LABELS.get(name, name) for name, _ in rows[:limit]]


def software(code, limit=12):
    """Software used in the occupation that O*NET marks as in demand (else as a 'hot technology')."""
    rows = _software().get(code, [])
    in_demand = sorted(name for name, demand, _ in rows if demand)
    hot = sorted(name for name, demand, is_hot in rows if is_hot and not demand)
    return (in_demand + hot)[:limit]
