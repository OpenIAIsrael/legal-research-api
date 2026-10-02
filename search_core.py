"""Deterministic query parsing; identifiers are never matched as substrings."""
import re
import unicodedata
from dataclasses import dataclass

STOP = set('a o as os de da do das dos em no na nos nas para por com e ou um uma ao aos sobre que lei leis numero n art artigo'.split())
KINDS = {'lei complementar':'lei_complementar','lc':'lei_complementar','decreto-lei':'decreto_lei','decreto lei':'decreto_lei','emenda constitucional':'emenda_constitucional','ec':'emenda_constitucional','medida provisoria':'medida_provisoria','mp':'medida_provisoria','decreto':'decreto','lei ordinaria':'lei_ordinaria','lei':'lei_ordinaria'}

def normalize(text):
    return ' '.join(''.join(c for c in unicodedata.normalize('NFKD', str(text).lower()) if not unicodedata.combining(c)).split())

def tokens(text):
    return [t for t in re.findall(r'[a-z0-9]+', normalize(text)) if len(t)>1 and t not in STOP]

@dataclass(frozen=True)
class Identity:
    number: str | None = None
    year: int | None = None
    kind: str | None = None
    jurisdiction: str | None = None

def identity(query):
    s=normalize(query)
    jurisdiction = 'non_federal' if re.search(r'\b(estadual|municipal|distrital)\b',s) else ('federal' if re.search(r'\bfederal\b',s) else None)
    s=re.sub(r'\b(?:art\.?|artigo)\s*\d+[a-zº°]*','',s)
    pattern='|'.join(re.escape(k) for k in KINDS)
    m=re.search(r'\b('+pattern+r')\s*(?:federal|estadual|municipal|distrital)?\s*(?:n[.º°o]*\s*)?(\d[\d.]*)\s*(?:/\s*(\d{4})|(?:,?\s*de\s+)(\d{4}))?',s)
    if m:
        return Identity(str(int(m[2].replace('.',''))),int(m[3] or m[4]) if m[3] or m[4] else None,KINDS[m[1]],jurisdiction)
    m=re.fullmatch(r'\s*(\d[\d.]*)\s*(?:/\s*(\d{4}))?\s*',s)
    if m:return Identity(str(int(m[1].replace('.',''))),int(m[2]) if m[2] else None,None,jurisdiction)
    return Identity(jurisdiction=jurisdiction)

def same_identity(wanted, found):
    return (not wanted.number or wanted.number==found.number) and (not wanted.year or wanted.year==found.year) and (not wanted.kind or wanted.kind==found.kind) and (not wanted.jurisdiction or wanted.jurisdiction==found.jurisdiction)

def score(query, item):
    wanted=identity(query)
    if wanted.number:
        found=identity(item.get('number',''))
        found=Identity(found.number,item.get('year') or found.year,item.get('act_type') if item.get('act_type') not in ('codigo','estatuto') else found.kind,item.get('jurisdiction','federal'))
        return 100 if same_identity(wanted,found) else 0
    if wanted.jurisdiction=='non_federal' and item.get('jurisdiction','federal')=='federal':return 0
    text=' '.join(str(item.get(k,'')) for k in ('title','summary','number','area'))+' '+' '.join(item.get('aliases',[])+item.get('themes',[]))
    wanted_tokens=set(tokens(query)); found_tokens=set(tokens(text))
    if not wanted_tokens:return 0
    overlap=len(wanted_tokens&found_tokens)
    if overlap < max(1, (len(wanted_tokens)+1)//2):return 0
    return overlap*10+(20 if normalize(query) in [normalize(a) for a in item.get('aliases',[])] else 0)
