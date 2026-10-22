"""Metadados de documentos via HEAD/Range, sem ler arquivos integrais.

Não reutiliza cookies do navegador, não segue redirects automaticamente e não
desativa TLS. Limites são de leituras da aplicação; buffers de transporte podem
receber bytes antes do fechamento de uma resposta que ignore Range.
"""
from email.message import Message
import re
import time
from urllib.error import HTTPError
from urllib.parse import urlsplit, urljoin, unquote
from urllib.request import Request, build_opener, HTTPRedirectHandler,ProxyHandler

from .core import normalizar, url_limpa

MAX_PARES=20
MAX_REQUISICOES=100
MAX_REDIRECTS=3
MAX_BYTES=1
TIMEOUT=4
TEMPO_DOCUMENTO=10
TIPOS={'application/pdf','application/msword','application/vnd.ms-excel',
       'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
       'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
       'application/vnd.ms-powerpoint','application/vnd.openxmlformats-officedocument.presentationml.presentation',
       'application/zip','text/csv','application/vnd.oasis.opendocument.text',
       'application/vnd.oasis.opendocument.spreadsheet'}
ACOES_ESCRITA=re.compile(r'(?:^|[/?&=_\s-])(?:excluir|remover|apagar|delete|logout|salvar|enviar|gravar|update|alterar|cadastrar|incluir|criar|pagar|pagamento|submit|save|pay)(?:$|[/?&=_.\s-])',re.I)


class SemRedirect(HTTPRedirectHandler):
    def redirect_request(self,req,fp,code,msg,headers,newurl):return None


def autorizado(url,base):
    try:
        a,b=map(urlsplit,(url_limpa(url),url_limpa(base)))
        return (a.scheme,a.netloc)==(b.scheme,b.netloc)
    except ValueError:return False


class Documentos:
    def __init__(self,metricas,parar,permitir_range=True):
        self.permitir_range=permitir_range
        self.metricas=metricas;self.parar=parar
        self.opener=build_opener(ProxyHandler({}),SemRedirect())
        self.resultados=[];self.cache={};self.requisicoes=0

    def conferir(self,url,base):
        inicial=url;metodo='HEAD';redirects=0;inicio=time.monotonic()
        while True:
            if self.parar.is_set():return {'situacao':'inconclusivo','motivo':'Interrompido','url':url}
            restante=TEMPO_DOCUMENTO-(time.monotonic()-inicio)
            if restante<=0 or self.requisicoes>=MAX_REQUISICOES:
                return {'situacao':'inconclusivo','motivo':'Limite de tempo/requisições','url':url}
            if not autorizado(url,base):
                return {'situacao':'inconclusivo','motivo':'Destino fora da origem autorizada; não acessado','url':url}
            if ACOES_ESCRITA.search(unquote(url)):
                return {'situacao':'inconclusivo','motivo':'Destino com indício de ação de escrita; não acessado','url':url}
            headers={'User-Agent':'AmbiDiff/1.5 document-metadata','Accept-Encoding':'identity'}
            if metodo=='GET':headers['Range']=f'bytes=0-{MAX_BYTES-1}'
            self.requisicoes+=1;self.metricas.contagens['requisicoes_documentos']+=1
            try:
                try:r=self.opener.open(Request(url,method=metodo,headers=headers),timeout=min(TIMEOUT,restante))
                except HTTPError as ex:r=ex
                try:
                    status=r.code
                    if status in (301,302,303,307,308):
                        destino=r.headers.get('Location')
                        if not destino or redirects>=MAX_REDIRECTS:
                            return {'situacao':'inconclusivo','motivo':'Limite/redirecionamento sem destino','url':url,'status':status}
                        url=urljoin(url,destino);redirects+=1
                        continue
                    if metodo=='HEAD' and status in (405,501):
                        if not self.permitir_range:return {'situacao':'inconclusivo','url':url,'status':status,'motivo':'HEAD não suportado; GET não realizado','bytes_lidos':0}
                        metodo='GET';continue
                    if status>=400:
                        return {'situacao':'falha_acesso','url':url,'status':status,
                                'motivo':'Resposta HTTP observada; não comprova defeito do site.'}
                    lidos=0
                    if metodo=='GET':
                        cr=re.fullmatch(r'bytes 0-(\d+)/(?:\d+|\*)',r.headers.get('Content-Range',''))
                        if status!=206 or not cr or int(cr[1])>=MAX_BYTES or (r.headers.get('Content-Length','').isdigit() and int(r.headers['Content-Length'])>MAX_BYTES):
                            return {'situacao':'inconclusivo','url':url,'status':status,
                                    'motivo':'Servidor não confirmou Range limitado; corpo não lido','bytes_lidos':0}
                        # Não fazer read() sem tamanho, nem ler até EOF.
                        # Os metadados já estão nos cabeçalhos: nem esse byte é lido.
                        self.metricas.contagens['bytes_documentos_lidos']+=0
                    mime=r.headers.get('Content-Type','').split(';')[0].strip().lower()
                    msg=Message();msg['Content-Disposition']=r.headers.get('Content-Disposition','')
                    nome=msg.get_filename() or unquote(urlsplit(url).path.rsplit('/',1)[-1])
                    return {'situacao':'acessivel' if mime in TIPOS and status in (200,206) else 'inconclusivo',
                        'url_inicial':inicial,'url':url,'status':status,'mime':mime,'nome':nome[:250],
                        'tamanho_declarado':r.headers.get('Content-Length'),
                        'ultima_modificacao':r.headers.get('Last-Modified'),
                        'etag':r.headers.get('ETag'),'cache_control':r.headers.get('Cache-Control',''),
                        'age':r.headers.get('Age','0'),'metodo':metodo,'redirects':redirects,
                        'bytes_lidos':lidos,'motivo':'Somente metadados; identidade do conteúdo não verificada.'}
                finally:r.close()
            except Exception as ex:
                return {'situacao':'inconclusivo','url':url,'motivo':'Falha na verificação: '+str(ex)[:200]}

    def comparar(self,ia,ib,base_a,base_b):
        if ACOES_ESCRITA.search(ia.nome+' '+ib.nome):
            self.metricas.contagens['documentos_nao_verificados']+=1
            return {'classificacao':'Verificação inconclusiva','elemento':ia.nome,
                    'destino_a':ia.destino,'destino_b':ib.destino,
                    'motivo':'Rótulo com indício de ação; acesso documental não realizado.'}
        chave=(ia.destino,ib.destino,normalizar(ia.nome),normalizar(ib.nome),ia.local,ib.local)
        if chave in self.cache and time.monotonic()<self.cache[chave][1]:
            self.metricas.contagens['documentos_reaproveitados']+=1
            return {**self.cache[chave][0],'reaproveitado':True}
        if len(self.resultados)>=MAX_PARES:
            resultado={'classificacao':'Verificação inconclusiva','elemento':ia.nome,
                'destino_a':ia.destino,'destino_b':ib.destino,'motivo':'Limite de pares de documentos; não verificados'}
            self.metricas.contagens['documentos_nao_verificados']+=1
            return resultado
        with self.metricas.medir('documentos'):
            a=self.conferir(ia.destino,base_a);recebido_a=time.monotonic()
            b=self.conferir(ib.destino,base_b);recebido_b=time.monotonic()
        classificacao='Verificação inconclusiva'
        if (a['situacao']=='falha_acesso') != (b['situacao']=='falha_acesso') and 'acessivel' in (a['situacao'],b['situacao']):
            classificacao='Falha de acesso confirmada em um ambiente'
        elif a.get('mime') and b.get('mime') and a['mime']!=b['mime']:
            classificacao='Possível divergência de destino, tipo ou finalidade'
        elif a['situacao']==b['situacao']=='acessivel':
            def termos(nome):
                return {t for t in re.findall(r'[a-zà-ú]{3,}',normalizar(nome))
                        if t not in {'pdf','doc','docx','xls','xlsx','download','manual','documento','arquivo','publicacao'}}
            ta,tb=termos(a['nome']),termos(b['nome'])
            similaridade=len(ta&tb)/max(1,len(ta|tb))
            if a['mime']!=b['mime'] or (ta and tb and similaridade<0.5):
                classificacao='Possível divergência de destino, tipo ou finalidade'
            elif ta and tb and similaridade>=0.75 and normalizar(ia.nome)==normalizar(ib.nome):
                classificacao='Documento acessível e provavelmente equivalente'
        resultado={'classificacao':classificacao,'elemento':ia.nome,'contexto':ia.local,
                   'destino_a':ia.destino,'destino_b':ib.destino,'a':a,'b':b,
                   'nota':'Metadados não comprovam arquivos idênticos nem identidade do conteúdo.'}
        def validade(meta):
            cc=meta.get('cache_control','').lower()
            if 'no-cache' in cc or 'no-store' in cc:return 0
            m=re.search(r'(?:^|,)\s*max-age=(\d+)',cc)
            idade=meta.get('age','0')
            if not idade.isdigit():return 0
            return max(0,min(30,int(m[1])-int(idade))) if m else 0
        self.cache[chave]=(resultado,min(recebido_a+validade(a),recebido_b+validade(b)))
        self.resultados.append(resultado)
        return resultado
