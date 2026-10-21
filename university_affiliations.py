"""Normalize US/Canadian university names from published affiliations only.

Veterinary college names: https://www.aavmc.org/about/our-member-institutions/
Canadian colleges: https://www.cfavm.ca/en/our-members.html
Aliases include historical spellings; researcher names never imply affiliation.
"""
import re
import unicodedata

VERSION = "2026-10-21-affiliations-v1"

# Country, canonical university name, additional unambiguous affiliation names.
UNIVERSITIES = [
    ("US", "Auburn University", []),
    ("US", "Colorado State University", []),
    ("US", "Cornell University", []),
    ("US", "Iowa State University", []),
    ("US", "Kansas State University", []),
    ("US", "Lincoln Memorial University", []),
    ("US", "Long Island University", []),
    ("US", "Louisiana State University", []),
    ("US", "Michigan State University", ["Michigan Sate University"]),
    ("US", "Midwestern University", []),
    ("US", "Mississippi State University", []),
    ("US", "North Carolina State University", ["North Carolina State", "NC State University"]),
    ("US", "Ohio State University", []),
    ("US", "Oklahoma State University", []),
    ("US", "Oregon State University", []),
    ("US", "Purdue University", []),
    ("US", "Texas A&M University", ["Texas A M University", "Texas AM University"]),
    ("US", "Texas Tech University", []),
    ("US", "Tufts University", []),
    ("US", "Tuskegee University", ["Tuskegee Institute"]),
    ("US", "University of Arizona", []),
    ("US", "University of California, Davis", ["UC Davis", "University of California at Davis"]),
    ("US", "University of Florida", []),
    ("US", "University of Georgia", []),
    ("US", "University of Illinois", ["University of Illinois at Urbana Champaign"]),
    ("US", "University of Minnesota", []),
    ("US", "University of Missouri", []),
    ("US", "University of Pennsylvania", ["Penn Vet", "University ofPennsylvania"]),
    ("US", "University of Tennessee", []),
    ("US", "University of Wisconsin", []),
    ("US", "Virginia Tech", ["Virginia Polytechnic Institute"]),
    ("US", "Washington State University", []),
    ("US", "Western University of Health Sciences", []),
    ("US", "University of Alaska Fairbanks", []),
    ("US", "Utah State University", []),
    ("US", "Clemson University", []),
    ("US", "Arkansas State University", []),
    ("US", "South Dakota State University", []),
    ("US", "North Dakota State University", []),
    ("US", "University of Nebraska-Lincoln", ["University of Nebraska Lincoln"]),
    ("US", "University of Connecticut", []),
    ("US", "University of Kentucky", []),
    ("US", "University of Wyoming", []),
    ("US", "Pennsylvania State University", ["Penn State University"]),
    ("US", "University of Maryland", []),
    ("US", "Stanford University", []),
    ("US", "Johns Hopkins University", []),
    ("US", "Massachusetts Institute of Technology", []),
    ("US", "University of Michigan", []),
    ("US", "Boston University", []),
    ("US", "Columbia University", []),
    ("US", "Duke University", []),
    ("US", "Emory University", []),
    ("US", "Harvard University", ["Harvard Medical School"]),
    ("US", "Kennesaw State University", []),
    ("US", "La Sierra University", []),
    ("US", "Rice University", []),
    ("US", "Rochester Institute of Technology", []),
    ("US", "Temple University", []),
    ("US", "Tulane University", []),
    ("US", "University of California, Riverside", ["University of California at Riverside"]),
    ("US", "University of California, San Diego", ["University of California at San Diego"]),
    ("US", "University of California, San Francisco", ["University of California at San Francisco"]),
    ("US", "University of Chicago", []),
    ("US", "University of Colorado", []),
    ("US", "University of Massachusetts", []),
    ("US", "University of North Carolina", []),
    ("US", "University of Rochester", []),
    ("US", "University of San Francisco", []),
    ("US", "University of Texas at Austin", []),
    ("US", "University of Texas Medical Branch", []),
    ("US", "University of Texas MD Anderson Cancer Center", []),
    ("US", "University of Texas Health Science Center at San Antonio", []),
    ("US", "University of Utah", []),
    ("US", "University of Washington", []),
    ("US", "Washington University in St. Louis", []),
    ("US", "SUNY Upstate Medical University", []),
    ("US", "Yale University", []),
    ("CA", "University of Calgary", []),
    ("CA", "University of Guelph", ["Ontario Veterinary College"]),
    ("CA", "Université de Montréal", ["University of Montreal", "Universite de Montreal"]),
    ("CA", "University of Prince Edward Island", ["Atlantic Veterinary College"]),
    ("CA", "University of Saskatchewan", ["Western College of Veterinary Medicine"]),
    ("CA", "McGill University", []),
    ("CA", "McMaster University", []),
    ("CA", "University of Ottawa", []),
]


def normalize(value):
    value = unicodedata.normalize("NFKD", value.casefold())
    value = "".join(c for c in value if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9]+", " ", value.replace("&", " and ")).strip()


RULES = [
    (name, [re.compile(r"\b" + re.escape(normalize(alias)) + r"\b")
            for alias in [name, *aliases]])
    for _, name, aliases in UNIVERSITIES
]

# Older records sometimes put the street address between university and campus.
for name, patterns in RULES:
    if name == "University of California, Davis":
        patterns.append(re.compile(r"\buniversity of california (?:one shields? avenue )?davis\b"))
    if name == "Virginia Tech":
        patterns.append(re.compile(r"\bvirginia maryland (?:regional )?college of veterinary medicine\b.*\bblacksburg\b"))
    if name == "Washington University in St. Louis":
        patterns.append(re.compile(r"(?<!george )(?<!central )(?<!eastern )(?<!western )\bwashington university\b.*\bst louis\b"))


def match_universities(affiliations):
    """Match full institution names, retaining every collaborating university."""
    texts = [normalize(value) for value in affiliations]
    return sorted(name for name, patterns in RULES
                  if any(pattern.search(text) for pattern in patterns for text in texts))


def parse_affiliations(article):
    """Includes all authors and legacy Article/Affiliation PubMed records."""
    return list(dict.fromkeys(
        text for node in article.findall(".//Article//Affiliation")
        if (text := re.sub(r"\s+", " ", "".join(node.itertext())).strip())
    ))


def university_catalog(papers):
    present = {name for paper in papers for name in paper.get("universities", [])}
    return [{"name": name, "country": country}
            for country, name, _ in UNIVERSITIES if name in present]
