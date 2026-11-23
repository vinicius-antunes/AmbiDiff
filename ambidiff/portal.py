"""Pertencimento lógico Liferay, independente por ambiente e sem listas de órgãos."""
import re
from urllib.parse import urlsplit, parse_qsl, unquote


def site_subdominio_dedicado(url):
    """Indício conservador em *.orgao.estado.gov.br (não em *.estado.gov.br)."""
    labels=(urlsplit(url).hostname or '').casefold().rstrip('.').split('.')
    if len(labels)<4 or labels[-2:]!=['gov','br']:
        return ''
    anteriores=labels[:-2]
    while anteriores and anteriores[0] in ('www','lab','des','homolog','homologacao','homol','prd','prod'):
        anteriores=anteriores[1:]
    if len(anteriores)<2 or anteriores[0] in ('portal','sites','sistemas','intranet'):
        return ''
    return anteriores[0]


def site_url(url):
    p = urlsplit(url)
    # Friendly URLs públicas/privadas e rotas com locale antes de /web/.
    m = re.search(r'/(?:web|group)/([^/]+)(?:/|$)', p.path)
    return unquote(m[1]).casefold() if m else ''


def grupo_url(url):
    values = {v for k, v in parse_qsl(urlsplit(url).query)
              if re.search(r'(?:^|_)(?:groupId|siteId)$', k, re.I) and v.isdecimal()}
    return next(iter(values)) if len(values) == 1 else ''


class EscopoPortal:
    def __init__(self, base, estado=None):
        self.base = base
        self.site = (estado or {}).get('site') or site_url(base)
        self.grupo = (estado or {}).get('grupo', '')
        self.fonte_site = (estado or {}).get('fonte_site', 'url_inicial' if site_url(base) else 'checkpoint_legado' if self.site else 'indeterminada')
        if self.fonte_site == 'metadados_conflitantes':
            self.site = ''
        self.sites_explicitos=set((estado or {}).get('sites_explicitos',[]))
        if site_url(base):self.sites_explicitos.add(site_url(base))
        if self.site and self.fonte_site in ('url_inicial','metadados_raiz'):self.sites_explicitos.add(self.site)
        self.compartilhados = set((estado or {}).get('compartilhados', []))

    def observar(self, url, dados, raiz=False):
        # Somente a entrada explicitamente escolhida estabelece a identidade.
        # Metadados de uma página estrangeira não alargam o escopo.
        if not raiz or urlsplit(url).netloc != urlsplit(self.base).netloc:
            return
        candidato = site_url(url)
        canonical = dados.get('canonical', '')
        friendly = dados.get('friendly_url', '')
        sites = {candidato} if candidato else set()
        for ref in (friendly, canonical):
            if ref and urlsplit(ref).netloc == urlsplit(url).netloc:
                if site_url(ref): sites.add(site_url(ref))
        self.sites_explicitos.update(sites)
        if self.sites_explicitos:
            if len(self.sites_explicitos)==1:
                self.site=next(iter(self.sites_explicitos))
                self.fonte_site='url_inicial' if site_url(self.base) else 'metadados_raiz'
            else:
                self.site='';self.fonte_site='metadados_conflitantes'
        elif self.fonte_site!='metadados_conflitantes':
            refs={ref for ref in dados.get('navegacao',[]) if urlsplit(ref).netloc==urlsplit(url).netloc and site_url(ref)}
            if len(refs)>=2:
                candidatos_navegacao={site_url(ref) for ref in refs}
                # Navegação com vários portais não estabelece identidade.
                # Host dedicado prevalece sobre um único link genérico.
                if len(candidatos_navegacao)==1 and not site_subdominio_dedicado(self.base):
                    if not self.site:self.site=next(iter(candidatos_navegacao));self.fonte_site='navegacao_raiz'
            if not self.site:
                sugerido=site_subdominio_dedicado(self.base)
                if sugerido:self.site=sugerido;self.fonte_site='subdominio_heuristico'
        # A observação inicial sem HTML pode sugerir o host; a coleta seguinte
        # sempre pode substituí-lo por metadados. Conflitos sobrevivem à retomada.
        grupo = str(dados.get('group_id', ''))
        if grupo.isdecimal(): self.grupo = grupo

    def outro(self, url):
        if not url or urlsplit(url).netloc != urlsplit(self.base).netloc:
            return False  # A autorização de rede existente continua responsável.
        if url in self.compartilhados: return False
        site, grupo = site_url(url), grupo_url(url)
        return bool((site and self.site and site != self.site) or
                    (grupo and self.grupo and grupo != self.grupo))

    def estado(self):
        return {'site': self.site, 'grupo': self.grupo,
                'fonte_site':self.fonte_site,
                'sites_explicitos':sorted(self.sites_explicitos),
                'compartilhados': sorted(self.compartilhados)}
