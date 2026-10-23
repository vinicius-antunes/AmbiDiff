"""Classificação de referências por evidência; nunca lê corpo ou faz requisição."""
import re
from urllib.parse import urlsplit
from .core import url_limpa

MIDIA=re.compile(r'\.(?:avif|webp|png|jpe?g|gif|svg|ico|bmp|jfif|mp[34]|webm|wav|ogg|mov)(?:/|$)',re.I)
DOCUMENTO=re.compile(r'\.(?:pdf|docx?|xlsx?|pptx?|od[st]|csv|zip|rar)(?:/|$)',re.I)


def classificar(url,contexto='',mime=''):
    mime=mime.lower().split(';')[0]
    if mime.startswith(('image/','audio/','video/')):return 'midia'
    if mime in ('application/pdf','application/msword','text/csv') or 'officedocument' in mime:return 'documento'
    try:url_limpa(url);path=urlsplit(url).path
    except (ValueError,TypeError):return 'inconclusivo'
    if DOCUMENTO.search(path):return 'documento'
    if MIDIA.search(path):return 'midia'
    if re.search(r'\.(?:css|js|woff2?|ttf|map)(?:/|$)',path,re.I):return 'auxiliar'
    if contexto in ('midia','documento'):return contexto
    if path.startswith('/documents/'):return 'inconclusivo'
    return 'navegacao'
