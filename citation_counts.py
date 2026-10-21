"""Refresh OpenAlex citation counts by exact DOI; retain cached counts on failure."""
from datetime import datetime, timedelta, timezone
import time

import requests

FIELDS = ("citation_count", "citation_updated_at", "citation_checked_at")


def normalize_doi(value):
    return str(value or "").strip().lower().removeprefix("https://doi.org/").removeprefix("http://doi.org/")


def enrich_citations(papers, previous_papers, now, session=None, pause=time.sleep):
    session = session or requests.Session()
    previous = {normalize_doi(p.get("doi")): p for p in previous_papers if p.get("doi")}
    pending = {}
    cutoff = now - timedelta(days=7)
    for paper in papers:
        doi = normalize_doi(paper.get("doi"))
        if not doi:
            continue
        cached = previous.get(doi, {})
        for field in FIELDS:
            if field in cached:
                paper[field] = cached[field]
        try:
            checked = datetime.fromisoformat(paper.get("citation_checked_at", ""))
            if checked.tzinfo and checked >= cutoff:
                continue
        except (ValueError, TypeError):
            pass
        pending.setdefault(doi, []).append(paper)

    dois = sorted(pending)
    failures = 0
    matched = 0
    for start in range(0, len(dois), 100):
        batch = dois[start:start + 100]
        if start:
            pause(1.1)
        try:
            response = session.get(
                "https://api.openalex.org/works",
                params={"filter": "doi:" + "|".join(batch), "per_page": 100,
                        "select": "doi,cited_by_count"},
                headers={"User-Agent": "VetCardioPapers/1.0 (https://minvetcardio.github.io/vetcardio-papers/)"},
                timeout=30,
            )
            response.raise_for_status()
            rows = response.json()["results"]
            if not isinstance(rows, list):
                raise ValueError("Invalid OpenAlex response")
            counts = {}
            for row in rows:
                doi = normalize_doi(row.get("doi"))
                count = row.get("cited_by_count")
                if doi in batch and type(count) is int and count >= 0:
                    counts[doi] = count
            for doi in batch:
                for paper in pending[doi]:
                    paper["citation_checked_at"] = now.isoformat()
                    if doi in counts:
                        paper["citation_count"] = counts[doi]
                        paper["citation_updated_at"] = now.isoformat()
                        matched += 1
            failures = 0
        except (requests.RequestException, ValueError, KeyError, TypeError) as error:
            print(f"OpenAlex warning: citation batch unavailable ({type(error).__name__}); retaining cached counts")
            failures += 1
            if failures >= 3:
                break
    print(f"OpenAlex: refreshed {matched} citation counts")

