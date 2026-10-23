"""Diagnóstico de bloqueios: resume sem alterar a política de requisições."""
import re
import time
from urllib.parse import urlsplit,urlunsplit


def url_diagnostica(url):
    try:
        p=urlsplit(str(url));host=p.hostname or ''
        path='/'.join('[identificador]' if len(s)>32 else s for s in re.sub(r';[^/]*','',p.path).split('/')[:8])
        return urlunsplit((p.scheme,host,path,'',''))[:220]
    except (ValueError,TypeError):return '[referência inválida omitida]'


def categoria(url):
    try:
        p=urlsplit(url);h=p.hostname or '';path=p.path.lower()
    except (ValueError,TypeError):return 'Outras'
    if (h=='google.com' or h.endswith('.google.com') or h.endswith('.gstatic.com') or h=='recaptcha.net' or h.endswith('.recaptcha.net')) and 'recaptcha' in path:return 'reCAPTCHA'
    if any(h==d or h.endswith('.'+d) for d in ('google-analytics.com','googletagmanager.com','doubleclick.net')):return 'Google Analytics'
    if any(h==d or h.endswith('.'+d) for d in ('cookiebot.com','onetrust.com','consent.google.com')):return 'Consentimento'
    return 'Outras'


def registrar(grupos,url,metodo,motivo,origem=''):
    cat=categoria(url);safe=url_diagnostica(url);host=urlsplit(safe).hostname or 'inválido'
    key='|'.join((cat,host,metodo,motivo))
    g=grupos.setdefault(key,{'tipo_erro':'POLITICA_SEGURANCA','categoria':cat,'dominio':host,
        'metodo':metodo,'motivo':motivo,'quantidade':0,'urls':{},'origens':{},
        'impacto_possivel':cat!='Google Analytics'})
    g['quantidade']+=1
    # Todos os pedidos são contados; exemplos limitados e sem query/credenciais.
    if safe in g['urls'] or len(g['urls'])<20:g['urls'][safe]=g['urls'].get(safe,0)+1
    else:g['exemplos_omitidos']=g.get('exemplos_omitidos',0)+1
    fonte=url_diagnostica(origem)
    if fonte and len(g['origens'])<20:g['origens'][fonte]=g['origens'].get(fonte,0)+1
    return g


def resumo(grupos):
    counts={}
    for g in grupos.values():counts[g.get('categoria','Outras')]=counts.get(g.get('categoria','Outras'),0)+g['quantidade']
    return '[Segurança] '+str(sum(counts.values()))+' requisições bloqueadas: '+', '.join(f'{k} ({v})' for k,v in sorted(counts.items()))+'. Restrições e possíveis impactos no diagnóstico.'


class Resumos:
    def __init__(self):self.ultimo=0;self.total=0
    def emitir(self,grupos,log,final=False):
        total=sum(g['quantidade'] for g in grupos.values());agora=time.monotonic()
        if total!=self.total and (final or total-self.total>=1000 or agora-self.ultimo>=10):
            log(resumo(grupos));self.total=total;self.ultimo=agora


def restaurar(grupos):
    """Migra exemplos legados sem perder contagens ou conservar queries."""
    out={}
    for g in grupos.values() if isinstance(grupos,dict) else grupos:
        vistos=0;destino=None
        urls=g.get('urls',{}) or {'https://'+g.get('dominio','invalido')+'/':0}
        for url,qtd in urls.items():
            destino=registrar(out,url,g.get('metodo','GET'),g.get('motivo','Legado'))
            extra=max(0,qtd)-1
            destino['quantidade']+=extra;vistos+=max(0,qtd)
            safe=url_diagnostica(url)
            if safe in destino['urls']:destino['urls'][safe]+=extra
            else:destino['exemplos_omitidos']+=extra
        if destino is not None:
            restante=max(0,g.get('quantidade',vistos)-vistos);destino['quantidade']+=restante
            destino['exemplos_omitidos']=destino.get('exemplos_omitidos',0)+restante
            for origem,qtd in g.get('origens',{}).items():
                safe=url_diagnostica(origem)
                if safe in destino['origens'] or len(destino['origens'])<20:destino['origens'][safe]=destino['origens'].get(safe,0)+qtd
    return out
