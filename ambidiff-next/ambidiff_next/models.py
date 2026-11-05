"""Contratos independentes do AmbiDiff legado; JSON serializável e IDs determinísticos."""
from dataclasses import dataclass, field, asdict
import hashlib
import json
import re
import unicodedata


def normalized(text):
    value=unicodedata.normalize('NFKD',str(text or '')).casefold()
    return re.sub(r'\s+',' ',''.join(c for c in value if not unicodedata.combining(c))).strip()


def stable_id(prefix,*parts):
    return prefix+'-'+hashlib.sha256(json.dumps(parts,sort_keys=True,ensure_ascii=False,default=str).encode()).hexdigest()[:20]


@dataclass
class Element:
    id: str
    kind: str
    name: str
    role: str = ''
    section: str = ''
    parent: str = ''
    path: list = field(default_factory=list)
    url: str = ''
    visible: bool = True
    enabled: bool = True
    selector: str = ''
    bbox: dict = field(default_factory=dict)
    attrs: dict = field(default_factory=dict)
    editorial: bool = False
    confidence: str = 'confirmado'


@dataclass
class Page:
    url: str
    final_url: str
    title: str
    elements: list = field(default_factory=list)
    status: int = 200
    redirects: list = field(default_factory=list)
    screenshot: str = ''
    diagnostics: list = field(default_factory=list)

    def to_dict(self):return asdict(self)

    @classmethod
    def from_dict(cls,data):
        d=dict(data);d['elements']=[Element(**x) for x in d.get('elements',[])]
        return cls(**d)


def finding(code,nature,element='',page_a='',page_b='',*,impact='medio',confidence='possivel',observed_a='',observed_b='',evidence=None,section='',cause='',recommendation='',**extra):
    occurrence=stable_id('occ',code,nature,page_a,page_b,section,element,observed_a,observed_b)
    return {'id':occurrence,'code':code,'nature':nature,'impact':impact,'confidence':confidence,
            'element':element,'page_a':page_a,'page_b':page_b,'section':section,
            'observed_a':observed_a,'observed_b':observed_b,'fact':code.replace('_',' '),
            'possible_cause':cause,'recommendation':recommendation,'evidence':evidence or {},**extra}
