#!/usr/bin/env python3
from __future__ import annotations
import html, json, os, re, sys, time
from datetime import datetime, timezone
from pathlib import Path
import xml.etree.ElementTree as ET
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

OUT = Path(__file__).resolve().parent / "papers.json"
BASE = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"
API_KEY = os.getenv("NCBI_API_KEY", "").strip()
EMAIL = os.getenv("NCBI_EMAIL", "").strip()

JOURNALS = {
 "Frontiers in Veterinary Science":"Front Vet Sci",
 "BMC Veterinary Research":"BMC Vet Res",
 "The Veterinary Journal":"Vet J",
 "Animals":"Animals (Basel)",
 "Veterinary Sciences":"Vet Sci",
 "Journal of Veterinary Cardiology":"J Vet Cardiol",
 "Journal of Veterinary Emergency and Critical Care":"J Vet Emerg Crit Care (San Antonio)",
 "Journal of Veterinary Internal Medicine":"J Vet Intern Med",
 "Veterinary Radiology & Ultrasound":"Vet Radiol Ultrasound",
 "Journal of the American Veterinary Medical Association":"J Am Vet Med Assoc",
 "American Journal of Veterinary Research":"Am J Vet Res",
}
AUTHORS = {
 "Marisa K. Ames":("Ames","MK"),
 "Lance C. Visser":("Visser","LC"),
 "Brian A. Scansen":("Scansen","BA"),
 "E. Christopher Orton":("Orton","EC"),
 "Brianna M. Potter":("Potter","BM"),
 "Joshua A. Stern":("Stern","JA"),
 "Mark A. Oyama":("Oyama","MA"),
 "Joanna L. Kaplan":("Kaplan","JL"),
 "Tommaso Vezzosi":("Vezzosi","T"),
 "Gerhard Wess":("Wess","G"),
}
SPECIES = '''("Dogs"[Mesh] OR "Cats"[Mesh] OR dog[tiab] OR dogs[tiab] OR canine[tiab] OR cat[tiab] OR cats[tiab] OR feline[tiab])'''
CARDIO = '''("Cardiovascular Diseases"[Mesh] OR "Heart"[Mesh] OR cardiology[tiab] OR cardiovascular[tiab] OR cardiac[tiab] OR heart[tiab] OR echocardiograph*[tiab] OR electrocardiograph*[tiab] OR arrhythm*[tiab] OR myocard*[tiab] OR pericard*[tiab] OR valv*[tiab] OR "mitral regurgitation"[tiab] OR "pulmonary hypertension"[tiab] OR "patent ductus arteriosus"[tiab] OR "heart failure"[tiab] OR "systemic hypertension"[tiab] OR thromboembol*[tiab] OR "cardiac troponin"[tiab] OR "natriuretic peptide"[tiab] OR "NT-proBNP"[tiab] OR "left atrial"[tiab] OR "right atrial"[tiab] OR "ventricular function"[tiab])'''
NOT_HUMAN_ONLY = 'NOT ("Humans"[Mesh] NOT "Animals"[Mesh])'

TOPICS = {
 "MMVD / Mitral Valve":[r"\bmmvd\b",r"myxomatous mitral",r"degenerative mitral",r"mitral regurgitation",r"mitral valve"],
 "Cardiomyopathy":[r"cardiomyopath",r"\bhcm\b",r"\bdcm\b",r"myocardial thickening"],
 "Pulmonary Hypertension":[r"pulmonary hypertension",r"pulmonary arterial hypertension",r"\bpah\b"],
 "Arrhythmia":[r"arrhythm",r"atrial fibrillation",r"ventricular tachy",r"heart block",r"atrioventricular block",r"pacemaker"],
 "Congenital Heart Disease":[r"congenital heart",r"patent ductus",r"\bpda\b",r"pulmonic stenosis",r"subaortic stenosis",r"septal defect",r"tetralogy of fallot",r"cor triatriatum",r"tricuspid dysplasia"],
 "Heart Failure":[r"heart failure",r"congestive heart",r"pulmonary edema",r"cardiogenic edema"],
 "Pericardial Disease":[r"pericard",r"cardiac tamponade"],
 "Systemic Hypertension":[r"systemic hypertension",r"arterial hypertension",r"blood pressure"],
 "Thromboembolism":[r"thromboembol",r"arterial thrombus",r"atrial thrombus"],
 "Heartworm":[r"heartworm",r"dirofilaria",r"caval syndrome"],
 "Echocardiography":[r"echocardiograph",r"doppler",r"speckle.?tracking",r"left atrial volume"],
 "ECG / Holter":[r"electrocardiograph",r"\becg\b",r"\bekg\b",r"holter"],
 "Intervention / Surgery":[r"transcatheter",r"device occlusion",r"balloon valvuloplasty",r"cardiac surgery",r"mitral valve repair",r"edge-to-edge"],
 "Biomarkers":[r"troponin",r"natriuretic peptide",r"nt-probnp",r"\bbnp\b",r"biomarker"],
 "Pharmacology":[r"pimobendan",r"furosemide",r"torsemide",r"spironolactone",r"benazepril",r"enalapril",r"atenolol",r"sotalol",r"clopidogrel",r"rapamycin"],
 "Advanced Imaging":[r"computed tomography",r"\bct angiograph",r"magnetic resonance",r"\bmri\b",r"radiograph"],
 "Emergency / Critical Care":[r"emergency",r"critical care",r"shock",r"cardiopulmonary resuscitation",r"\bcpr\b",r"point-of-care ultrasound",r"\bpocus\b"],
}
MONTH = {"Jan":1,"Feb":2,"Mar":3,"Apr":4,"May":5,"Jun":6,"Jul":7,"Aug":8,"Sep":9,"Oct":10,"Nov":11,"Dec":12}

retry = Retry(total=5,backoff_factor=1,status_forcelist=(429,500,502,503,504),allowed_methods=frozenset(("GET","POST")))
S = requests.Session(); S.mount("https://",HTTPAdapter(max_retries=retry))
S.headers["User-Agent"]="vetcardio-papers/1.0 (GitHub Actions)"

def common():
 d={"tool":"vetcardio_papers"}
 if API_KEY:d["api_key"]=API_KEY
 if EMAIL:d["email"]=EMAIL
 return d
def pause(): time.sleep(.12 if API_KEY else .38)
def norm(q): return re.sub(r"\s+"," ",q).strip()
def txt(e): return html.unescape("".join(e.itertext())).strip() if e is not None else ""
def clean(s): return re.sub(r"\s+"," ",s).strip()

def esearch(query):
 query=norm(query)
 r=S.post(f"{BASE}/esearch.fcgi",data={**common(),"db":"pubmed","term":query,"retmode":"json","retmax":"0"},timeout=60);r.raise_for_status()
 count=int(r.json()["esearchresult"]["count"]);print("검색 결과",count)
 ids=[]
 for start in range(0,count,5000):
  r=S.post(f"{BASE}/esearch.fcgi",data={**common(),"db":"pubmed","term":query,"retmode":"json","retstart":start,"retmax":5000,"sort":"pub date"},timeout=90);r.raise_for_status()
  ids+=r.json()["esearchresult"]["idlist"];pause()
 return list(dict.fromkeys(ids))

def fetch(pmids):
 for start in range(0,len(pmids),200):
  batch=pmids[start:start+200]
  r=S.post(f"{BASE}/efetch.fcgi",data={**common(),"db":"pubmed","id":",".join(batch),"retmode":"xml"},timeout=120);r.raise_for_status()
  yield from ET.fromstring(r.content).findall("./PubmedArticle")
  print("수집",min(start+200,len(pmids)),"/",len(pmids));pause()

def parse_date(n):
 a=n.find(".//Article/ArticleDate")
 if a is not None:
  y=txt(a.find("Year"));m=txt(a.find("Month")).zfill(2) or "01";d=txt(a.find("Day")).zfill(2) or "01"
  if y:return f"{y}-{m}-{d}",f"{y}-{m}-{d}"
 p=n.find(".//JournalIssue/PubDate")
 if p is not None:
  med=txt(p.find("MedlineDate"));y=txt(p.find("Year"))
  if not y and med:
   z=re.search(r"(19|20)\d{2}",med);y=z.group(0) if z else ""
  if y:
   mt=txt(p.find("Month"));m=MONTH.get(mt,int(mt) if mt.isdigit() else 1);dt=txt(p.find("Day"));d=int(dt) if dt.isdigit() else 1
   return f"{y}-{m:02d}-{d:02d}",med or f"{y}-{m:02d}"
 return "0000-01-01","날짜 정보 없음"

def parse_authors(n):
 rows=[];names=[]
 for a in n.findall(".//Article/AuthorList/Author"):
  coll=txt(a.find("CollectiveName"))
  if coll: rows.append({"last":coll,"fore":"","initials":""});names.append(coll);continue
  last=txt(a.find("LastName"));fore=txt(a.find("ForeName"));ini=txt(a.find("Initials"))
  if last: rows.append({"last":last,"fore":fore,"initials":ini});names.append(clean(f"{fore or ini} {last}"))
 return rows,", ".join(names)

def matched(rows):
 out=[]
 for name,(last,ini) in AUTHORS.items():
  if any(a["last"].casefold()==last.casefold() and re.sub("[^A-Za-z]","",a["initials"]).upper().startswith(ini) for a in rows):out.append(name)
 return out

def classify_species(text,mesh):
 x=(text+" "+" ".join(mesh)).lower()
 dog=bool(re.search(r"\b(dog|dogs|canine|canines)\b",x)) or "dogs" in mesh
 cat=bool(re.search(r"\b(cat|cats|feline|felines)\b",x)) or "cats" in mesh
 return "Both" if dog and cat else "Canine" if dog else "Feline" if cat else "Unclear"

def classify_topics(text):
 x=text.lower();out=[k for k,patterns in TOPICS.items() if any(re.search(p,x,re.I) for p in patterns)]
 return out or ["Other Cardiology"]

def parse(n,journal_ids):
 pmid=txt(n.find(".//MedlineCitation/PMID"));title=clean(txt(n.find(".//Article/ArticleTitle")))
 if not pmid or not title:return None
 parts=[]
 for a in n.findall(".//Article/Abstract/AbstractText"):
  label=a.attrib.get("Label","").strip();v=clean(txt(a))
  if v:parts.append(f"{label}: {v}" if label else v)
 abstract="\n".join(parts);rows,authors_text=parse_authors(n);ma=matched(rows)
 journal=clean(txt(n.find(".//Article/Journal/Title"))) or clean(txt(n.find(".//MedlineJournalInfo/MedlineTA")))
 sort_date,pub_date=parse_date(n);doi="";pmc=""
 for a in n.findall(".//PubmedData/ArticleIdList/ArticleId"):
  if a.attrib.get("IdType")=="doi":doi=txt(a)
  if a.attrib.get("IdType")=="pmc":pmc=txt(a)
 mesh=[clean(txt(a)).lower() for a in n.findall(".//MeshHeading/DescriptorName")]
 keywords=[clean(txt(a)) for a in n.findall(".//KeywordList/Keyword")]
 text=" ".join([title,abstract,journal," ".join(mesh)," ".join(keywords)])
 return {"pmid":pmid,"title":title,"authors_text":authors_text,"journal":journal,"publication_date":pub_date,"sort_date":sort_date,"abstract":abstract,"doi":doi,"pmcid":pmc,"pubmed_url":f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/","species":classify_species(text,mesh),"topics":classify_topics(text),"selected_journal":pmid in journal_ids,"matched_authors":ma}

def main():
 jq=" OR ".join(f'"{x}"[Journal]' for x in JOURNALS.values())
 aq=" OR ".join(f'"{l} {i}"[Author]' for l,i in AUTHORS.values())
 journal_ids=set(esearch(f"({jq}) AND {SPECIES} AND {CARDIO} {NOT_HUMAN_ONLY}"))
 author_ids=set(esearch(f"({aq}) AND {SPECIES} AND {CARDIO} {NOT_HUMAN_ONLY}"))
 ids=sorted(journal_ids|author_ids,key=int,reverse=True)
 if not ids:raise RuntimeError("검색 결과가 0개라서 기존 파일을 바꾸지 않습니다.")
 papers=[p for n in fetch(ids) if (p:=parse(n,journal_ids))]
 papers.sort(key=lambda p:(p["sort_date"],int(p["pmid"])),reverse=True)
 data={"generated_at":datetime.now(timezone.utc).isoformat(),"total":len(papers),"tracked_journals":list(JOURNALS),"tracked_authors":list(AUTHORS),"papers":papers}
 temp=OUT.with_suffix(".tmp");temp.write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding="utf-8");temp.replace(OUT)
 print("완료",len(papers))
if __name__=="__main__":
 try:main()
 except Exception as e:print("오류:",e,file=sys.stderr);raise
