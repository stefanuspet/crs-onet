"""Indonesian text for what students see: occupation titles and descriptions, competency names,
and work activities.

The CSV files in this folder are the source of truth and can be corrected by hand. The
translations were written for this project and have not been validated by a language or
subject expert. Anything missing from a file falls back to the O*NET English text.
"""
import csv
from functools import lru_cache
from pathlib import Path

HERE = Path(__file__).resolve().parent


def _rows(name):
    with open(HERE / name, encoding="utf-8") as f:
        return list(csv.DictReader(f))


@lru_cache(maxsize=1)
def _occupations():
    return {r["kode"]: r for r in _rows("pekerjaan.csv")}


@lru_cache(maxsize=1)
def _competencies():
    return {r["nama_en"]: r["nama_id"] for r in _rows("kompetensi.csv")}


@lru_cache(maxsize=1)
def _activities():
    return {r["dwa_id"]: r["teks_id"] for r in _rows("aktivitas.csv")}


def occupation_title(code, fallback):
    row = _occupations().get(code)
    return row["judul_id"] if row and row["judul_id"] else fallback


def occupation_description(code, fallback):
    row = _occupations().get(code)
    return row["deskripsi_id"] if row and row["deskripsi_id"] else fallback


def competency(name):
    return _competencies().get(name) or name


def activity(dwa_id, fallback):
    return _activities().get(dwa_id) or fallback
