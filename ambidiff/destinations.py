"""HEAD restrito a destinos. Sem cookies, corpo, proxy ambiental ou crawling externo."""
import http.client
import ipaddress
import socket
import ssl
import time
from urllib.parse import urlsplit,urljoin,unquote,parse_qsl
from .documents import ACOES_ESCRITA

class Destinos:
    def __init__(self,metricas,parar,origens=(),externos=False,limite=100,transporte=None,resolver=None):
        self.metricas=metricas;self.parar=parar;self.origens={self.origem(u) for u in origens}
        self.externos=externos;self.limite=limite;self.pedidos=0;self.cache={};self.resultados=[]
        self.transporte=transporte or self._head;self.resolver=resolver or socket.getaddrinfo
    @staticmethod
    def origem(url):
        p=urlsplit(url);return p.scheme,p.hostname,p.port or (443 if p.scheme=='https' else 80)
    def autorizar(self,url):
        p=urlsplit(url)
        if p.scheme not in ('http','https') or not p.hostname or p.username or p.password:raise ValueError('URL não autorizada')
        if ACOES_ESCRITA.search(unquote(url)):raise ValueError('Indício de ação insegura')
        interna=self.origem(url) in self.origens
        if not interna and any(k.casefold() in {'token','auth','authorization','password','senha','sessionid','sid','jsessionid','phpsessid'} for k,v in parse_qsl(p.query)):
            raise ValueError('Possível credencial em URL externa; não enviada')
        if not interna and any('http://' in unquote(v).lower() or 'https://' in unquote(v).lower() for k,v in parse_qsl(p.query)):
            raise ValueError('URL externa contém outra URL; envio automático não autorizado')
        if not interna and not self.externos:raise ValueError('Verificação externa não habilitada')
        enderecos=self.resolver(p.hostname,p.port or (443 if p.scheme=='https' else 80),type=socket.SOCK_STREAM)
        ips=list(dict.fromkeys(x[4][0] for x in enderecos))
        if not ips:raise ValueError('DNS sem endereço verificável')
        if not interna and (p.port not in (None,80,443) or any(not ipaddress.ip_address(ip).is_global for ip in ips)):
            raise ValueError('Destino externo privado, reservado ou porta não autorizada')
        return p,ips[0]
    @staticmethod
    def _head(p,ip,timeout):
        # Conexão fixada no IP validado; preserva Host, SNI e verificação TLS.
        port=p.port or (443 if p.scheme=='https' else 80)
        conn=http.client.HTTPConnection(p.hostname,port,timeout=timeout)
        sock=socket.create_connection((ip,port),timeout=timeout)
        try:
            if p.scheme=='https':sock=ssl.create_default_context().wrap_socket(sock,server_hostname=p.hostname)
            conn.sock=sock
            conn.request('HEAD',(p.path or '/')+('?' +p.query if p.query else ''),headers={'User-Agent':'AmbiDiff destination-check','Accept-Encoding':'identity','Connection':'close'})
            response=conn.getresponse()
            try:return response.status,dict((k.lower(),v) for k,v in response.getheaders())
            finally:response.close() # Nunca ler corpo, nem em erro/HEAD não suportado.
        finally:conn.close();sock.close()
    def conferir(self,url):
        if url in self.cache:return dict(self.cache[url],reaproveitado=True)
        inicial=url;inicio=time.monotonic();cadeia=[]
        result={'url_inicial':inicial,'url_final':url,'classificacao':'VERIFICACAO_INCONCLUSIVA','bytes_lidos':0}
        try:
            for _ in range(4):
                if self.parar.is_set():raise ValueError('Interrupção solicitada')
                restante=8-(time.monotonic()-inicio)
                if restante<=0 or self.pedidos>=self.limite:raise ValueError('Limite de tempo/requisições')
                p,ip=self.autorizar(url)
                self.pedidos+=1;self.metricas.contagens['requisicoes_destinos']+=1
                status,headers=self.transporte(p,ip,min(3,restante));cadeia.append({'url':url,'status':status})
                result.update(url_final=url,status=status,cadeia=cadeia)
                if status in (301,302,303,307,308):
                    if not headers.get('location'):raise ValueError('Redirecionamento sem Location')
                    url=urljoin(url,headers['location']);continue
                if status in (405,501):raise ValueError('HEAD não suportado; GET não realizado')
                if status>=400:result.update(classificacao='LINK_INACESSIVEL',motivo='Resposta HTTP observada; não prova defeito permanente')
                elif 200<=status<300:result.update(classificacao='DESTINO_ACESSIVEL',motivo='Somente destino/cabeçalhos; conteúdo e autenticação não analisados')
                else:raise ValueError('Resposta insuficiente')
                break
            else:raise ValueError('Limite de redirecionamentos')
        except Exception as exc:result.update(classificacao='VERIFICACAO_INCONCLUSIVA',motivo=str(exc)[:220],destino_nao_seguido=url)
        # Cache apenas desta execução e desta observação; não prova permanência.
        self.cache[inicial]=dict(result);self.resultados.append(dict(result));return result
    def comparar(self,a,b,base_a,base_b):
        from .paired import link_equivalente
        ra=self.conferir(a);rb=self.conferir(b)
        classe='VERIFICACAO_INCONCLUSIVA'
        if ra['classificacao']==rb['classificacao']=='DESTINO_ACESSIVEL':
            classe='DESTINO_EQUIVALENTE' if link_equivalente(ra['url_final'],rb['url_final'],base_a,base_b) else 'DESTINO_DIVERGENTE'
        elif 'LINK_INACESSIVEL' in (ra['classificacao'],rb['classificacao']) and 'DESTINO_ACESSIVEL' in (ra['classificacao'],rb['classificacao']):classe='LINK_INACESSIVEL'
        return {'classificacao':classe,'a':ra,'b':rb,'destino_a':a,'destino_b':b,'escopo':'Somente referências, cabeçalhos e destinos; sem conteúdo ou login'}
