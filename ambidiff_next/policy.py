"""Política conservadora para inspeção local. GET não é autorização de escrita."""
import ipaddress
import re
from urllib.parse import urlsplit, urlunsplit, unquote, parse_qsl, urlencode

_RISKY=re.compile(r'(?:^|[/_.;=\-])(logout|logoff|signout|sair|delete|destroy|remove|excluir|deletar|remover|update|save|salvar|create|criar|submit|enviar|checkout|purchase|transfer|payment|pagar)(?:$|[/_.;=\-])',re.I)
_SENSITIVE=re.compile(r'password|passwd|senha|token|secret|session|cookie|authorization|p_auth|csrf|credential',re.I)
_AUXILIARY=re.compile(r'analytics|recaptcha|doubleclick|googletagmanager|consent',re.I)


def normalize_url(url,base=None):
    """URL HTTP(S) absoluta; mantém query e fragmento funcionais integralmente."""
    from urllib.parse import urljoin
    if not isinstance(url,str) or any(ord(c)<32 for c in url):raise ValueError('URL inválida')
    if base:url=urljoin(base,url)
    try:
        p=urlsplit(url.strip());port=p.port;host=p.hostname
        if p.scheme.lower() not in ('http','https') or not host or p.username is not None or p.password is not None:raise ValueError()
        if any(c.isspace() for c in host) or any(c in host for c in '/\\%'):raise ValueError()
        if ':' in host:ipaddress.IPv6Address(host);host='['+host.lower()+']'
        else:
            host=host.encode('idna').decode('ascii').lower().rstrip('.')
            if not re.fullmatch(r'[a-z0-9](?:[a-z0-9.-]*[a-z0-9])?',host) or '..' in host:raise ValueError()
            if any(not part or part.startswith('-') or part.endswith('-') for part in host.split('.')):raise ValueError()
        if port and not ((p.scheme.lower()=='http' and port==80) or (p.scheme.lower()=='https' and port==443)):host+=':'+str(port)
        decoded=p.path
        for _ in range(3):
            decoded=unquote(decoded)
            if '\\' in decoded or any(seg in ('.','..') for seg in decoded.split('/')):raise ValueError()
        return urlunsplit((p.scheme.lower(),host,p.path or '/',p.query,p.fragment))
    except (ValueError,TypeError,UnicodeError) as exc:
        raise ValueError('Informe uma URL HTTP/HTTPS completa, sem credenciais e sem caminho ambíguo.') from exc


def safe_url(url):
    try:
        p=urlsplit(normalize_url(url))
        if _RISKY.search(unquote(p.path)):return False
        for key,value in parse_qsl(p.query,keep_blank_values=True):
            k=unquote(key);v=unquote(value)
            if _SENSITIVE.search(k):return False
            if k.lower() in ('p_p_lifecycle','lifecycle') and v not in ('0',''):return False
            if _RISKY.search(k) or _RISKY.search(v):return False
            if k.lower() in ('action','cmd','operation','op','method') and v.lower() not in ('','view','read','show','list','search','render','display'):return False
        return True
    except (TypeError,ValueError):return False


def allowed_url(url,root):
    try:
        p,r=map(lambda x:urlsplit(normalize_url(x)),(url,root))
        prefix=r.path.rstrip('/')
        return (p.scheme,p.netloc)==(r.scheme,r.netloc) and (not prefix or p.path==prefix or p.path.startswith(prefix+'/')) and safe_url(url)
    except (TypeError,ValueError):return False


def equivalent_url(a,b,roots):
    try:
        a,b=normalize_url(a),normalize_url(b)
        if a==b:return True
        if not allowed_url(a,roots[0]) or not allowed_url(b,roots[1]):return False
        def relative(url,root):
            p,r=urlsplit(url),urlsplit(normalize_url(root));prefix=r.path.rstrip('/')
            tail=p.path[len(prefix):] if prefix else p.path
            return tail or '/',p.query,p.fragment
        return relative(a,roots[0])==relative(b,roots[1])
    except (TypeError,ValueError):return False


def redact_url(url):
    try:
        p=urlsplit(normalize_url(url))
        # Conserva nomes de parâmetros para investigar; valores nunca vão a logs.
        query=urlencode([(k,'[redigido]') for k,_ in parse_qsl(p.query,keep_blank_values=True)])
        return urlunsplit((p.scheme,p.netloc,p.path,query,''))
    except (TypeError,ValueError):return '[referência inválida]'


def classify_resource(url,attrs=None):
    """Indícios de rota não bastam para afirmar o MIME de documentos Liferay."""
    attrs=attrs or {}
    try:path=unquote(urlsplit(url).path).lower()
    except (TypeError,ValueError):return 'unknown'
    mime=str(attrs.get('mime') or attrs.get('type') or '').lower()
    tag=str(attrs.get('tag','')).lower()
    if tag in ('img','video','audio','source') or mime.startswith(('image/','audio/','video/')) or re.search(r'\.(png|jpe?g|gif|svg|webp|avif|mp4|mp3|ico)(?:/|$)',path):return 'media'
    if _AUXILIARY.search(url) or re.search(r'\.(css|js|woff2?|ttf)(?:/|$)',path):return 'auxiliary'
    if attrs.get('download') or mime in ('application/pdf','application/msword') or re.search(r'\.(pdf|docx?|xlsx?|odt|ods|pptx?|zip)(?:/|$)',path):return 'document'
    if '/documents/' in path:return 'document_reference'
    if str(url).startswith(('http://','https://')):return 'navigation'
    return 'unknown'
