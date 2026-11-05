"""Descoberta por relevância: amostragem explícita, sem meta artificial de páginas."""
import re
from urllib.parse import urlsplit, urlunsplit
from .models import normalized
from .policy import normalize_url,classify_resource,allowed_url


def priority(e):
    text=normalized(e.name+' '+e.section+' '+urlsplit(e.url).path)
    if e.kind in ('menu','tab') or any(t in normalized(e.section) for t in ('menu','header','navigation','cabecalho')):return 0
    if re.search(r'servic|consult|sistema|atendimento|audio|acessib',text):return 1
    if classify_resource(e.url,e.attrs) in ('document','document_reference') or re.search(r'legisla|normativ|portaria|document',text):return 2
    if e.editorial or re.search(r'noticia|evento|galeria|historico|/w/',text):return 4
    return 3


def editorial_group(e):
    p=urlsplit(e.url)
    is_page=bool(re.search(r'proxim|anterior|next|previous',normalized(e.name)) or re.search(r'(?:[?&]|_)(?:page|pagina|cur|start)=',p.query))
    if is_page:return 'pagination:'+re.sub(r'/\d+(?=/|$)','/{n}',p.path)
    if e.editorial or re.search(r'/(?:noticias?|news|eventos?|galerias?|historico)/',p.path,re.I):return 'editorial:'+p.path.rsplit('/',1)[0]+':'+normalized(e.section)
    return ''


def visit_url(url):
    p=urlsplit(normalize_url(url));return urlunsplit((p.scheme,p.netloc,p.path,p.query,''))


class Planner:
    def __init__(self,store,rid,config):
        self.store=store;self.rid=rid;self.config=config
        self.roots=tuple(config['roots']);self.limit=int(config.get('max_pages',config.get('capacity',1000)))
    def propose(self,a,b,trail,element=None,reason='Referências observadas nos ambientes'):
        urls=[a,b];kind='page_pair';rank=priority(element) if element else 0
        resource=classify_resource(element.url,element.attrs) if element else 'navigation'
        if resource in ('document','document_reference'):kind='document'
        if not any(urls):return False
        for side,url in enumerate(urls):
            if url and not allowed_url(url,self.roots[side]):
                self.store.diagnose(self.rid,{'urls':urls,'status':'not_planned','reason':'Fora do escopo ou URL insegura; referência não explorada'})
                return False
        try:urls=[visit_url(u) if u else '' for u in urls]
        except ValueError:
            self.store.diagnose(self.rid,{'urls':urls,'status':'invalid','reason':'Referência malformada não navegada'});return False
        payload={'urls':urls,'trail':list(trail),'group':editorial_group(element) if element else '',
                 'element':element.name if element else 'Página inicial','category':rank,'exclusive':not all(urls)}
        tasks=self.store.tasks(self.rid)
        if any(t['kind']==kind and t['payload'].get('urls')==urls for t in tasks):return False
        admitted=[t for t in tasks if t['kind']=='page_pair' and t['state'] not in ('sampled','blocked')]
        state=''
        if kind=='page_pair' and len(admitted)>=self.limit:state='Proteção de capacidade: referência não admitida'
        group=payload['group']
        if group:
            quota=1 if group.startswith('pagination:') else int(self.config.get('editorials_per_template',2))
            count=sum(t['payload'].get('group')==group and t['state'] not in ('sampled','blocked') for t in tasks)
            if count>=quota:state='Amostragem explícita: template/paginação já representado; página não validada'
        inserted=self.store.enqueue(self.rid,kind,payload,rank,reason)
        if inserted and state:
            task=next(t for t in self.store.tasks(self.rid) if t['payload']==payload)
            self.store.finish(self.rid,task['id'],'sampled',state)
        return inserted
