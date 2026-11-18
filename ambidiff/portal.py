"""Pertencimento lógico Liferay, independente por ambiente e sem listas de órgãos."""
import re
from urllib.parse import urlsplit, parse_qsl, unquote


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
        if not sites:
            refs={ref for ref in dados.get('navegacao',[]) if urlsplit(ref).netloc==urlsplit(url).netloc and site_url(ref)}
            if len(refs)>=2: sites={site_url(ref) for ref in refs}
        # Metadados conflitantes não comprovam pertencimento.
        if len(sites)==1:self.site=self.site or next(iter(sites))
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
                'compartilhados': sorted(self.compartilhados)}
