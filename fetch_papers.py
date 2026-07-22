#!/usr/bin/env python3
'''VetCardio Papers PubMed collector — slightly stricter filter.

수집 대상:
1. 지정 저널의 개·고양이 심장 관련 논문
2. 추적 연구자가 저자인 개·고양이 심장 관련 논문

이 버전은 heart rate, shock, blood pressure, generic ultrasound처럼
비심장 논문에서도 흔히 나오는 표현 하나만으로는 논문을 포함하지 않습니다.
'''

from __future__ import annotations

import html
import json
import os
import re
import sys
import time
import unicodedata
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable
import xml.etree.ElementTree as ET

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry


OUTPUT = Path(__file__).resolve().parent / "papers.json"
EUTILS = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"
NCBI_API_KEY = os.getenv("NCBI_API_KEY", "").strip()
NCBI_EMAIL = os.getenv("NCBI_EMAIL", "").strip()
AUTHOR_SCOPE_VERSION = "2026-07-22-all-dog-cat-papers"
AUTHOR_LIST_VERSION = "2026-07-22-expanded-authors"
JOURNAL_LIST_VERSION = "2026-07-22-vetq-jsap"


TRACKED_JOURNALS = {
    "Frontiers in Veterinary Science": "Front Vet Sci",
    "BMC Veterinary Research": "BMC Vet Res",
    "The Veterinary Journal": "Vet J",
    "Animals": "Animals (Basel)",
    "Veterinary Sciences": "Vet Sci",
    "Journal of Veterinary Cardiology": "J Vet Cardiol",
    "Journal of Veterinary Emergency and Critical Care":
        "J Vet Emerg Crit Care (San Antonio)",
    "Journal of Veterinary Internal Medicine": "J Vet Intern Med",
    "Veterinary Radiology & Ultrasound": "Vet Radiol Ultrasound",
    "Journal of the American Veterinary Medical Association":
        "J Am Vet Med Assoc",
    "American Journal of Veterinary Research": "Am J Vet Res",
    "Journal of Veterinary Pharmacology and Therapeutics":
        "J Vet Pharmacol Ther",
    "Journal of Feline Medicine and Surgery": "J Feline Med Surg",
    "Veterinary Quarterly": "Vet Q",
    "Journal of Small Animal Practice": "J Small Anim Pract",
}


TRACKED_AUTHORS = {
    "Marisa K. Ames": [("Ames", "MK")],
    "Lance C. Visser": [("Visser", "LC")],
    "Brian A. Scansen": [("Scansen", "BA")],
    "E. Christopher Orton": [("Orton", "EC")],
    "Brianna M. Potter": [("Potter", "BM")],
    "Joshua A. Stern": [("Stern", "JA")],
    "Mark A. Oyama": [("Oyama", "MA")],
    "Joanna L. Kaplan": [("Kaplan", "JL")],
    "Tommaso Vezzosi": [("Vezzosi", "T")],
    "Gerhard Wess": [("Wess", "G")],
    "Mark Rishniw": [("Rishniw", "M")],
    "Virginia Luis Fuentes": [
        ("Luis Fuentes", "V"),
        ("Luis-Fuentes", "V"),
    ],
    "Jens Häggström": [("Haggstrom", "J")],
    "Kathryn M. Meurs": [("Meurs", "KM")],
    "Darcy B. Adin": [("Adin", "DB")],
    "Roberto A. Santilli": [("Santilli", "RA")],
    "Romain Pariaut": [("Pariaut", "R")],
    "N. Sydney Moïse": [("Moise", "NS")],
    "Ashley B. Saunders": [("Saunders", "AB")],
}


SPECIES_QUERY = r'''
(
  "Dogs"[Mesh] OR "Cats"[Mesh]
  OR dog[Title/Abstract] OR dogs[Title/Abstract] OR canine[Title/Abstract]
  OR cat[Title/Abstract] OR cats[Title/Abstract] OR feline[Title/Abstract]
)
'''


# 너무 넓은 Heart[Mesh], Cardiovascular Diseases[Mesh],
# heart[tiab], cardiac[tiab], cardiovascular[tiab]는 제거했습니다.
CARDIO_QUERY = r'''
(
  "Heart Diseases"[Mesh]
  OR "Cardiomyopathies"[Mesh]
  OR "Heart Failure"[Mesh]
  OR "Arrhythmias, Cardiac"[Mesh]
  OR "Heart Valve Diseases"[Mesh]
  OR "Pulmonary Hypertension"[Mesh]
  OR "Heart Defects, Congenital"[Mesh]
  OR "Pericardial Diseases"[Mesh]
  OR "Echocardiography"[Mesh]
  OR "Electrocardiography"[Mesh]

  OR "myxomatous mitral"[Title/Abstract]
  OR "degenerative mitral"[Title/Abstract]
  OR "mitral regurgitation"[Title/Abstract]
  OR cardiomyopath*[Title/Abstract]
  OR "heart failure"[Title/Abstract]
  OR arrhythm*[Title/Abstract]
  OR "atrial fibrillation"[Title/Abstract]
  OR "ventricular tachycardia"[Title/Abstract]
  OR "atrioventricular block"[Title/Abstract]
  OR pacemaker[Title/Abstract]
  OR "pulmonary hypertension"[Title/Abstract]
  OR echocardiograph*[Title/Abstract]
  OR electrocardiograph*[Title/Abstract]
  OR holter[Title/Abstract]
  OR "patent ductus arteriosus"[Title/Abstract]
  OR "pulmonic stenosis"[Title/Abstract]
  OR "pulmonary stenosis"[Title/Abstract]
  OR "subaortic stenosis"[Title/Abstract]
  OR "ventricular septal defect"[Title/Abstract]
  OR "atrial septal defect"[Title/Abstract]
  OR pericard*[Title/Abstract]
  OR "cardiac tamponade"[Title/Abstract]
  OR "left atrial"[Title/Abstract]
  OR "right atrial"[Title/Abstract]
  OR "ventricular function"[Title/Abstract]
  OR "cardiac troponin"[Title/Abstract]
  OR "natriuretic peptide"[Title/Abstract]
  OR "NT-proBNP"[Title/Abstract]
  OR heartworm[Title/Abstract]
  OR dirofilaria[Title/Abstract]
)
'''


NOT_HUMAN_ONLY = 'NOT ("Humans"[Mesh] NOT "Animals"[Mesh])'


TITLE_CORE_PATTERNS = [
    r"\bmmvd\b",
    r"myxomatous mitral",
    r"degenerative mitral",
    r"mitral regurgitation",
    r"mitral valve",
    r"tricuspid valve",
    r"aortic valve",
    r"pulmonic valve",
    r"pulmonary valve",
    r"cardiomyopath",
    r"\bhcm\b",
    r"\bdcm\b",
    r"heart failure",
    r"congestive heart",
    r"cardiac failure",
    r"arrhythm",
    r"atrial fibrillation",
    r"ventricular tachy",
    r"supraventricular tachy",
    r"bradyarrhythm",
    r"atrioventricular block",
    r"heart block",
    r"pacemaker",
    r"pulmonary hypertension",
    r"echocardiograph",
    r"electrocardiograph",
    r"\bholter\b",
    r"patent ductus arteriosus",
    r"\bpda\b",
    r"pulmonic stenosis",
    r"pulmonary stenosis",
    r"subaortic stenosis",
    r"ventricular septal defect",
    r"atrial septal defect",
    r"tetralogy of fallot",
    r"cor triatriatum",
    r"tricuspid dysplasia",
    r"pericard",
    r"cardiac tamponade",
    r"left atrial",
    r"right atrial",
    r"left ventricular",
    r"right ventricular",
    r"ventricular function",
    r"cardiac function",
    r"balloon valvuloplasty",
    r"mitral valve repair",
    r"edge-to-edge",
    r"heartworm",
    r"dirofilaria",
    r"caval syndrome",
    r"feline arterial thromboembol",
    r"cardiogenic",
]


TITLE_SUPPORT_PATTERNS = [
    r"\bcardiac\b",
    r"\bheart\b",
    r"\bcardiovascular\b",
    r"troponin",
    r"natriuretic peptide",
    r"nt-probnp",
    r"\bbnp\b",
    r"pimobendan",
    r"furosemide",
    r"torsemide",
    r"spironolactone",
    r"benazepril",
    r"enalapril",
    r"atenolol",
    r"sotalol",
    r"clopidogrel",
    r"point-of-care ultrasound",
    r"\bpocus\b",
    r"transcatheter",
    r"catheterization",
]


ABSTRACT_CORE_PATTERNS = [
    r"myxomatous mitral",
    r"degenerative mitral",
    r"mitral regurgitation",
    r"mitral valve disease",
    r"cardiomyopath",
    r"heart failure",
    r"congestive heart",
    r"arrhythm",
    r"atrial fibrillation",
    r"ventricular tachy",
    r"atrioventricular block",
    r"pacemaker",
    r"pulmonary hypertension",
    r"echocardiograph",
    r"electrocardiograph",
    r"\bholter\b",
    r"patent ductus arteriosus",
    r"pulmonic stenosis",
    r"pulmonary stenosis",
    r"subaortic stenosis",
    r"ventricular septal defect",
    r"atrial septal defect",
    r"pericardial effusion",
    r"cardiac tamponade",
    r"left atrial",
    r"right atrial",
    r"left ventricular",
    r"right ventricular",
    r"ventricular function",
    r"cardiac function",
    r"cardiac remodeling",
    r"cardiac remodelling",
    r"heartworm",
    r"dirofilaria",
    r"feline arterial thromboembol",
    r"atrial thrombus",
    r"cardiogenic",
]


NONCARDIAC_TITLE_PATTERNS = [
    r"neuromyopath",
    r"neurolog",
    r"spinal",
    r"septic shock",
    r"\bsepsis\b",
    r"quadratus lumborum",
    r"abdominal surgery",
    r"regional anesthesia",
    r"regional anaesthesia",
    r"nerve block",
    r"analgesi",
    r"orthopedic",
    r"orthopaedic",
    r"renal disease",
    r"kidney disease",
    r"chronic kidney",
    r"urinary",
    r"gastrointestinal",
    r"enteropath",
    r"hepat",
    r"dermat",
    r"neoplas",
    r"tumor",
    r"tumour",
    r"oncolog",
    r"pneumonia",
]


STRONG_CARDIAC_MESH = {
    "heart diseases",
    "cardiomyopathies",
    "heart failure",
    "arrhythmias, cardiac",
    "heart valve diseases",
    "pulmonary hypertension",
    "heart defects, congenital",
    "pericardial diseases",
    "echocardiography",
    "electrocardiography",
}


TOPIC_PATTERNS = {
    "MMVD / Mitral Valve": [
        r"\bmmvd\b", r"myxomatous mitral", r"degenerative mitral",
        r"mitral regurgitation", r"mitral valve",
    ],
    "Cardiomyopathy": [
        r"cardiomyopath", r"\bhcm\b", r"\bdcm\b",
        r"myocardial thickening",
    ],
    "Pulmonary Hypertension": [
        r"pulmonary hypertension", r"pulmonary arterial hypertension",
        r"\bpah\b",
    ],
    "Arrhythmia": [
        r"arrhythm", r"atrial fibrillation", r"ventricular tachy",
        r"supraventricular tachy", r"heart block",
        r"atrioventricular block", r"pacemaker",
    ],
    "Congenital Heart Disease": [
        r"congenital heart", r"patent ductus", r"\bpda\b",
        r"pulmonic stenosis", r"pulmonary stenosis",
        r"subaortic stenosis", r"ventricular septal defect",
        r"atrial septal defect", r"tetralogy of fallot",
        r"cor triatriatum", r"tricuspid dysplasia",
    ],
    "Heart Failure": [
        r"heart failure", r"congestive heart", r"cardiogenic edema",
        r"cardiogenic pulmonary edema",
    ],
    "Pericardial Disease": [
        r"pericard", r"cardiac tamponade",
    ],
    "Systemic Hypertension": [
        r"systemic hypertension", r"arterial hypertension",
    ],
    "Cardiac Thromboembolism": [
        r"feline arterial thromboembol", r"atrial thrombus",
        r"left atrial thrombus", r"cardiogenic thromboembol",
    ],
    "Heartworm": [
        r"heartworm", r"dirofilaria", r"caval syndrome",
    ],
    "Echocardiography": [
        r"echocardiograph", r"speckle.?tracking",
        r"left atrial volume", r"right atrial",
        r"left ventricular", r"right ventricular",
    ],
    "ECG / Holter": [
        r"electrocardiograph", r"\becg\b", r"\bekg\b", r"holter",
    ],
    "Intervention / Surgery": [
        r"transcatheter", r"device occlusion",
        r"balloon valvuloplasty", r"cardiac surgery",
        r"mitral valve repair", r"edge-to-edge",
    ],
    "Biomarkers": [
        r"cardiac troponin", r"natriuretic peptide",
        r"nt-probnp", r"\bbnp\b",
    ],
    "Pharmacology": [
        r"pimobendan", r"furosemide", r"torsemide",
        r"spironolactone", r"benazepril", r"enalapril",
        r"atenolol", r"sotalol", r"clopidogrel",
    ],
    "Cardiac Emergency / CPR": [
        r"cardiac arrest", r"cardiopulmonary resuscitation", r"\bcpr\b",
    ],
}


MONTHS = {
    "Jan": 1, "Feb": 2, "Mar": 3, "Apr": 4, "May": 5,
    "Jun": 6, "Jul": 7, "Aug": 8, "Sep": 9, "Oct": 10,
    "Nov": 11, "Dec": 12,
}


def make_session() -> requests.Session:
    retry = Retry(
        total=5,
        backoff_factor=1,
        status_forcelist=(429, 500, 502, 503, 504),
        allowed_methods=frozenset(("GET", "POST")),
    )
    session = requests.Session()
    session.mount("https://", HTTPAdapter(max_retries=retry))
    session.headers["User-Agent"] = (
        "vetcardio-papers/1.1 (GitHub Actions)"
    )
    return session


SESSION = make_session()


def common_params() -> dict[str, str]:
    params = {"tool": "vetcardio_papers"}
    if NCBI_API_KEY:
        params["api_key"] = NCBI_API_KEY
    if NCBI_EMAIL:
        params["email"] = NCBI_EMAIL
    return params


def pause() -> None:
    time.sleep(0.12 if NCBI_API_KEY else 0.38)


def normalize(query: str) -> str:
    return re.sub(r"\s+", " ", query).strip()


def text_of(element: ET.Element | None) -> str:
    if element is None:
        return ""
    return html.unescape("".join(element.itertext())).strip()


def clean(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def has_pattern(text: str, patterns: list[str]) -> bool:
    return any(re.search(pattern, text, re.I) for pattern in patterns)


def count_patterns(text: str, patterns: list[str]) -> int:
    return sum(
        1 for pattern in patterns
        if re.search(pattern, text, re.I)
    )


def is_relevant(
    title: str,
    abstract: str,
    mesh_terms: list[str],
) -> bool:
    title_core = has_pattern(title, TITLE_CORE_PATTERNS)
    title_support = has_pattern(title, TITLE_SUPPORT_PATTERNS)
    abstract_core_count = count_patterns(
        abstract, ABSTRACT_CORE_PATTERNS
    )
    mesh_core = bool(
        {term.lower() for term in mesh_terms} & STRONG_CARDIAC_MESH
    )
    noncardiac_title = has_pattern(
        title, NONCARDIAC_TITLE_PATTERNS
    )

    if noncardiac_title and not title_core:
        return False
    if title_core:
        return True
    if title_support and abstract_core_count >= 1:
        return True
    if mesh_core and abstract_core_count >= 1:
        return True
    if abstract_core_count >= 2:
        return True
    return False


def esearch(query: str) -> list[str]:
    query = normalize(query)

    response = SESSION.post(
        f"{EUTILS}/esearch.fcgi",
        data={
            **common_params(),
            "db": "pubmed",
            "term": query,
            "retmode": "json",
            "retmax": "0",
        },
        timeout=60,
    )
    response.raise_for_status()

    count = int(response.json()["esearchresult"]["count"])
    print(f"검색 후보: {count:,}개")

    ids: list[str] = []
    page_size = 5000

    for start in range(0, count, page_size):
        response = SESSION.post(
            f"{EUTILS}/esearch.fcgi",
            data={
                **common_params(),
                "db": "pubmed",
                "term": query,
                "retmode": "json",
                "retstart": str(start),
                "retmax": str(page_size),
                "sort": "pub date",
            },
            timeout=90,
        )
        response.raise_for_status()
        ids.extend(response.json()["esearchresult"]["idlist"])
        pause()

    return list(dict.fromkeys(ids))


def efetch(pmids: list[str]) -> Iterable[ET.Element]:
    batch_size = 200

    for start in range(0, len(pmids), batch_size):
        batch = pmids[start:start + batch_size]

        response = SESSION.post(
            f"{EUTILS}/efetch.fcgi",
            data={
                **common_params(),
                "db": "pubmed",
                "id": ",".join(batch),
                "retmode": "xml",
            },
            timeout=120,
        )
        response.raise_for_status()

        root = ET.fromstring(response.content)
        yield from root.findall("./PubmedArticle")

        print(
            f"수집: {min(start + batch_size, len(pmids)):,}"
            f"/{len(pmids):,}"
        )
        pause()


def parse_date(article: ET.Element) -> tuple[str, str]:
    article_date = article.find(".//Article/ArticleDate")

    if article_date is not None:
        year = text_of(article_date.find("Year"))
        month = text_of(article_date.find("Month")).zfill(2) or "01"
        day = text_of(article_date.find("Day")).zfill(2) or "01"

        if year:
            return f"{year}-{month}-{day}", f"{year}-{month}-{day}"

    pub_date = article.find(".//JournalIssue/PubDate")

    if pub_date is not None:
        medline = text_of(pub_date.find("MedlineDate"))
        year = text_of(pub_date.find("Year"))

        if not year and medline:
            match = re.search(r"(19|20)\d{2}", medline)
            year = match.group(0) if match else ""

        if year:
            month_text = text_of(pub_date.find("Month"))
            month = (
                int(month_text)
                if month_text.isdigit()
                else MONTHS.get(month_text, 1)
            )
            day_text = text_of(pub_date.find("Day"))
            day = int(day_text) if day_text.isdigit() else 1
            return (
                f"{year}-{month:02d}-{day:02d}",
                medline or f"{year}-{month:02d}",
            )

    return "0000-01-01", "날짜 정보 없음"


def parse_authors(
    article: ET.Element,
) -> tuple[list[dict[str, str]], str]:
    rows: list[dict[str, str]] = []
    names: list[str] = []

    for author in article.findall(".//Article/AuthorList/Author"):
        collective = text_of(author.find("CollectiveName"))

        if collective:
            rows.append({
                "last": collective,
                "fore": "",
                "initials": "",
            })
            names.append(collective)
            continue

        last = text_of(author.find("LastName"))
        fore = text_of(author.find("ForeName"))
        initials = text_of(author.find("Initials"))

        if last:
            rows.append({
                "last": last,
                "fore": fore,
                "initials": initials,
            })
            names.append(clean(f"{fore or initials} {last}"))

    return rows, ", ".join(names)


def normalize_author_name(value: str) -> str:
    """성의 악센트, 하이픈, 공백 차이를 무시하여 비교합니다."""
    decomposed = unicodedata.normalize("NFKD", value)
    ascii_text = "".join(
        character
        for character in decomposed
        if not unicodedata.combining(character)
    )
    return re.sub(r"[^a-z]", "", ascii_text.casefold())


def matched_authors(
    rows: list[dict[str, str]],
) -> list[str]:
    matches: list[str] = []

    for display_name, aliases in TRACKED_AUTHORS.items():
        for target_last, target_initials in aliases:
            target_last_normalized = normalize_author_name(target_last)

            for author in rows:
                author_initials = re.sub(
                    r"[^A-Za-z]", "", author["initials"]
                ).upper()

                if (
                    normalize_author_name(author["last"])
                    == target_last_normalized
                    and author_initials.startswith(
                        target_initials.upper()
                    )
                ):
                    matches.append(display_name)
                    break

            if display_name in matches:
                break

    return matches


def classify_species(text: str, mesh_terms: list[str]) -> str:
    combined = f"{text} {' '.join(mesh_terms)}".lower()

    dog = (
        bool(re.search(r"\b(dog|dogs|canine|canines)\b", combined))
        or "dogs" in mesh_terms
    )
    cat = (
        bool(re.search(r"\b(cat|cats|feline|felines)\b", combined))
        or "cats" in mesh_terms
    )

    if dog and cat:
        return "Both"
    if dog:
        return "Canine"
    if cat:
        return "Feline"
    return "Unclear"


def classify_topics(text: str) -> list[str]:
    topics = [
        topic
        for topic, patterns in TOPIC_PATTERNS.items()
        if has_pattern(text, patterns)
    ]
    return topics or ["Other Veterinary Medicine"]


def parse_article(
    node: ET.Element,
    journal_pmids: set[str],
    author_pmids: set[str],
) -> dict | None:
    pmid = text_of(node.find(".//MedlineCitation/PMID"))
    title = clean(text_of(node.find(".//Article/ArticleTitle")))

    if not pmid or not title:
        return None

    abstract_parts: list[str] = []

    for item in node.findall(".//Article/Abstract/AbstractText"):
        label = item.attrib.get("Label", "").strip()
        value = clean(text_of(item))
        if value:
            abstract_parts.append(
                f"{label}: {value}" if label else value
            )

    abstract = "\n".join(abstract_parts)

    mesh_terms = [
        clean(text_of(item)).lower()
        for item in node.findall(
            ".//MeshHeading/DescriptorName"
        )
    ]

    author_rows, author_text = parse_authors(node)
    tracked = matched_authors(author_rows)

    # 지정 저널 경로는 심장 관련성 필터를 적용합니다.
    # 추적 연구자 경로는 개·고양이 논문이면 비심장 논문도 포함합니다.
    is_tracked_author_paper = (
        pmid in author_pmids and bool(tracked)
    )
    if (
        not is_tracked_author_paper
        and not is_relevant(title, abstract, mesh_terms)
    ):
        return None

    journal = (
        clean(text_of(node.find(".//Article/Journal/Title")))
        or clean(text_of(node.find(
            ".//MedlineJournalInfo/MedlineTA"
        )))
    )

    sort_date, publication_date = parse_date(node)
    doi = ""
    pmcid = ""

    for article_id in node.findall(
        ".//PubmedData/ArticleIdList/ArticleId"
    ):
        id_type = article_id.attrib.get("IdType")
        if id_type == "doi":
            doi = text_of(article_id)
        elif id_type == "pmc":
            pmcid = text_of(article_id)

    classification_text = " ".join([
        title,
        abstract,
        journal,
        " ".join(mesh_terms),
    ])

    return {
        "pmid": pmid,
        "title": title,
        "authors_text": author_text,
        "journal": journal,
        "publication_date": publication_date,
        "sort_date": sort_date,
        "abstract": abstract,
        "doi": doi,
        "pmcid": pmcid,
        "pubmed_url": f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/",
        "species": classify_species(
            classification_text, mesh_terms
        ),
        "topics": classify_topics(classification_text),
        "selected_journal": pmid in journal_pmids,
        "matched_authors": tracked,
    }


def main() -> None:
    journal_terms = " OR ".join(
        f'"{journal}"[Journal]'
        for journal in TRACKED_JOURNALS.values()
    )
    author_terms = " OR ".join(
        f'"{last} {initials}"[Author]'
        for aliases in TRACKED_AUTHORS.values()
        for last, initials in aliases
    )

    journal_query = (
        f"({journal_terms}) AND {SPECIES_QUERY} "
        f"AND {CARDIO_QUERY} {NOT_HUMAN_ONLY}"
    )
    # 추적 연구자는 심장 분야로 제한하지 않고,
    # 개·고양이가 포함된 모든 PubMed 논문을 수집합니다.
    author_query = (
        f"({author_terms}) AND {SPECIES_QUERY} "
        f"{NOT_HUMAN_ONLY}"
    )

    print("1/4 지정 저널 후보 검색")
    journal_pmids = set(esearch(journal_query))

    print("2/4 추적 연구자 후보 검색")
    author_pmids = set(esearch(author_query))

    all_pmids = sorted(
        journal_pmids | author_pmids,
        key=int,
        reverse=True,
    )

    if not all_pmids:
        raise RuntimeError(
            "검색 결과가 0개라서 기존 papers.json을 변경하지 않습니다."
        )

    print(
        f"3/4 후보 {len(all_pmids):,}개에서 "
        "지정 저널의 비심장 논문을 제거하고 추적 연구자 논문은 유지합니다."
    )

    papers: list[dict] = []

    for node in efetch(all_pmids):
        parsed = parse_article(node, journal_pmids, author_pmids)
        if parsed is not None:
            papers.append(parsed)

    papers.sort(
        key=lambda paper: (
            paper["sort_date"],
            int(paper["pmid"]),
        ),
        reverse=True,
    )

    data = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "total": len(papers),
        "filter_version": "unified-authors-journals-2026-07-22",
        "tracked_journals": list(TRACKED_JOURNALS.keys()),
        "tracked_authors": list(TRACKED_AUTHORS.keys()),
        "papers": papers,
    }

    temporary = OUTPUT.with_suffix(".tmp")
    temporary.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    temporary.replace(OUTPUT)

    print(f"4/4 완료: 관련 논문 {len(papers):,}개 저장")


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print(f"오류: {error}", file=sys.stderr)
        raise
