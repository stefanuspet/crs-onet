"""Flatten the official O*NET 31.0 RDF (N-Triples) into tidy CSV tables.

The RDF models every rating as an intermediate node:

    Occupation --hasRating--> <Domain>Rating --refersTo--> Element
                                             --refersTo--> Scale
                                             --dataValue-> float

This script collapses that pattern into one row per
(occupation, element, scale) and also extracts the Related Occupations links.

Outputs (in data/):
    onet_occupations.csv          soc_code,title,job_zone,description
    onet_ratings.csv              soc_code,title,domain,element_id,element_name,scale_id,value
    onet_related_occupations.csv  soc_code,related_soc_code,tier,rank
    onet_dwa.csv                  soc_code,dwa_id,dwa_name   (Detailed Work Activities, via the occupation's tasks)
"""
import csv
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RDF_DIR = ROOT / "data" / "db_31_0_nt"
OUT_DIR = ROOT / "data"

# Domains used for the recommendation core (see context doc, section 16).
DOMAINS = [
    "CareerInterestTypesRating",
    "SpecificInterestAreasRating",
    "AbilitiesRating",
    "EssentialSkillsRating",
    "TransferableSkillsRating",
    "KnowledgeRating",
    "WorkActivitiesRating",
]

TRIPLE = re.compile(r'^<([^>]+)> <([^>]+)> (?:<([^>]+)>|"((?:[^"\\]|\\.)*)"\S*) \.$')


def triples(filename):
    """Yield (subject, predicate local name, object IRI or None, literal or None)."""
    with open(RDF_DIR / filename, encoding="utf-8") as f:
        for line in f:
            m = TRIPLE.match(line.rstrip("\n"))
            if m:
                s, p, o, lit = m.groups()
                yield s, p.rsplit("/", 1)[-1].rsplit("#", 1)[-1], o, lit


def main():
    elements, scales = {}, {}
    for s, p, _, lit in triples("Element.nt"):
        if p in ("elementID", "elementName"):
            elements.setdefault(s, {})[p] = lit
    for s, p, _, lit in triples("Scale.nt"):
        if p == "scaleID":
            scales[s] = lit

    occupations = {}    # iri -> {"code":..., "title":...}
    rating_owner = {}   # rating iri -> occupation iri
    related_owner = {}  # linkage iri -> occupation iri
    task_owner = {}     # task iri -> occupation iri
    for s, p, o, lit in triples("Occupation.nt"):
        if p == "onetSOCCode":
            occupations.setdefault(s, {})["code"] = lit
        elif p == "title":
            occupations.setdefault(s, {})["title"] = lit
        elif p == "description":
            occupations.setdefault(s, {})["description"] = lit
        elif p == "hasRating":
            rating_owner[o] = s
        elif p == "hasRelatedOccupation":
            related_owner[o] = s
        elif p == "hasTask":
            task_owner[o] = s

    zone_number = {s: lit for s, p, _, lit in triples("JobZone.nt") if p == "jobZone"}
    for s, p, o, _ in triples("JobZoneRating.nt"):
        if p == "refersTo" and o in zone_number and s in rating_owner:
            occupations[rating_owner[s]]["job_zone"] = zone_number[o]
    with open(OUT_DIR / "onet_occupations.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["soc_code", "title", "job_zone", "description"])
        for occ in sorted(occupations.values(), key=lambda x: x["code"]):
            w.writerow([occ["code"], occ["title"], occ.get("job_zone", ""), occ["description"]])
    print(f"onet_occupations.csv: {len(occupations):,} rows")

    n_rows = 0
    with open(OUT_DIR / "onet_ratings.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["soc_code", "title", "domain", "element_id", "element_name", "scale_id", "value"])
        for domain in DOMAINS:
            ratings = {}
            for s, p, o, lit in triples(domain + ".nt"):
                r = ratings.setdefault(s, {})
                if p == "dataValue":
                    r["value"] = lit
                elif p == "refersTo":
                    if o in elements:
                        r["element"] = o
                    elif o in scales:
                        r["scale"] = o
            for iri, r in ratings.items():
                occ = occupations.get(rating_owner.get(iri))
                if not occ or "element" not in r or "scale" not in r or "value" not in r:
                    continue
                el = elements[r["element"]]
                w.writerow([occ["code"], occ["title"], domain.removesuffix("Rating"),
                            el["elementID"], el["elementName"], scales[r["scale"]], r["value"]])
                n_rows += 1
            print(f"{domain:28s} {len(ratings):>8,} rating nodes")
    print(f"onet_ratings.csv: {n_rows:,} rows")

    links = {}
    for s, p, o, lit in triples("RelatedOccupationLinkage.nt"):
        l = links.setdefault(s, {})
        if p == "refersTo":
            l["target"] = o
        elif p == "relatednessTier":
            l["tier"] = lit
        elif p == "relatedIndex":
            l["rank"] = lit
    with open(OUT_DIR / "onet_related_occupations.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["soc_code", "related_soc_code", "tier", "rank"])
        n = 0
        for iri, l in links.items():
            src = occupations.get(related_owner.get(iri))
            dst = occupations.get(l.get("target"))
            if src and dst:
                w.writerow([src["code"], dst["code"], l.get("tier", ""), l.get("rank", "")])
                n += 1
    print(f"onet_related_occupations.csv: {n:,} rows")

    pairs = set()
    for s, p, o, _ in triples("Task.nt"):
        if p == "linkedTo" and o in elements and s in task_owner:
            el = elements[o]
            pairs.add((occupations[task_owner[s]]["code"], el["elementID"], el["elementName"]))
    with open(OUT_DIR / "onet_dwa.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["soc_code", "dwa_id", "dwa_name"])
        w.writerows(sorted(pairs))
    print(f"onet_dwa.csv: {len(pairs):,} rows")


if __name__ == "__main__":
    main()
