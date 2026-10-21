"""Escopo explícito e sinais de autenticação; não realiza login."""
from urllib.parse import urlsplit, parse_qsl
import re
from .core import url_limpa, permitido


def rota_autenticacao(url):
    p = urlsplit(url)
    return bool(re.search(r'/(?:login|sign-?in|autenticacao|autenticar)(?:/|$)', p.path, re.I)
                or any(k.lower() == 'p_p_id' and 'login' in v.lower()
                       for k, v in parse_qsl(p.query)))


def pagina_autenticacao(page, url):
    if rota_autenticacao(url):
        return 'Rota de autenticação reconhecida; nenhum login foi tentado.'
    if page.locator('input[type="password"]:visible').count():
        return 'Campo de senha visível; conteúdo tratado como possível autenticação.'
    return ''


def validar_rotas(rotas, base_a, base_b):
    if rotas is None:
        return []
    if not isinstance(rotas, list) or len(rotas) > 10:
        raise ValueError('Informe no máximo 10 pares de rotas equivalentes.')
    saida = []
    for par in rotas:
        if not isinstance(par, dict) or set(par) != {'a', 'b'}:
            raise ValueError('Cada par de rotas deve conter as URLs a e b.')
        a, b = url_limpa(par['a']), url_limpa(par['b'])
        for url, base in ((a, base_a), (b, base_b)):
            if (urlsplit(url).scheme, urlsplit(url).netloc) != (urlsplit(base).scheme, urlsplit(base).netloc):
                raise ValueError('As rotas equivalentes devem manter a origem de cada ambiente.')
            if rota_autenticacao(url):
                raise ValueError('Não configure rotas de autenticação como conteúdo equivalente.')
        if {'a': a, 'b': b} not in saida:
            saida.append({'a': a, 'b': b})
    return saida


def equivalente_declarado(a, b, rotas):
    """Relaciona raízes e descendentes apenas de pares confirmados pelo usuário."""
    a, b = url_limpa(a), url_limpa(b)
    for par in rotas:
        if a == par['a'] and b == par['b']:
            return True
        if not permitido(a, par['a']) or not permitido(b, par['b']):
            continue
        pa, pb, ra, rb = map(urlsplit, (a, b, par['a'], par['b']))
        ca = pa.path[len(ra.path.rstrip('/')):] or '/'
        cb = pb.path[len(rb.path.rstrip('/')):] or '/'
        if (ca, pa.query) == (cb, pb.query):
            return True
    return False


def proteger_contexto(contexto, bases, bloqueios):
    """Bloqueia métodos de escrita e navegação fora do escopo declarado.

    GET não é uma garantia de ausência de efeitos no servidor; destinos com
    nomes de ações conhecidas também são bloqueados. Nenhum formulário é enviado.
    """
    from .functional import PROIBIDOS
    def filtro(route):
        req = route.request
        origem = any((urlsplit(req.url).scheme, urlsplit(req.url).netloc) ==
                     (urlsplit(b).scheme, urlsplit(b).netloc) for b in bases)
        navegacao = req.is_navigation_request()
        escopo = any(permitido(req.url, b) for b in bases)
        auth = origem and rota_autenticacao(req.url)
        if (req.method not in ('GET', 'HEAD') or PROIBIDOS.search(req.url)
                or (navegacao and not (escopo or auth))):
            bloqueios.append({'url':req.url,'metodo':req.method,
                             'motivo':'Método, ação ou destino fora da política de leitura.'})
            route.abort()
        else:
            route.continue_()
    contexto.route('**/*', filtro)
