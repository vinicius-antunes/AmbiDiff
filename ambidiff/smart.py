"""Equivalência observada no DOM; nunca comprova funcionamento ou conteúdo oculto."""
from collections import Counter, defaultdict
from contextlib import contextmanager
import hashlib
import json
import time
from datetime import datetime

from .core import normalizar, comparacao


class Metricas:
    def __init__(self):
        self.inicio=time.perf_counter()
        self.iniciado_em=datetime.now().astimezone().isoformat()
        self.finalizado_em=None;self.duracao=None;self.releituras=[];self.parar=None
        self.tempos=Counter({k:0 for k in ('navegacao','preparacao','extracao','comparacao','segunda_leitura','links','cliques','documentos','verificacao_template','capturas','auditoria')});self.contagens=Counter({k:0 for k in ('requisicoes_navegador','requisicoes_documentos','requisicoes_api_externa','bytes_documentos_lidos','verificacoes_reaproveitadas','documentos_reaproveitados','documentos_nao_verificados','preparacoes_profundas_evitadas')})

    @contextmanager
    def medir(self, etapa):
        inicio=time.perf_counter()
        try:yield
        finally:
            self.tempos[etapa]+=time.perf_counter()-inicio
            self.contagens['operacoes_'+etapa]+=1

    def temporal(self):
        return {'iniciado_em':self.iniciado_em,'finalizado_em':self.finalizado_em,
                'duracao_segundos':round(self.duracao if self.duracao is not None else time.perf_counter()-self.inicio,6)}

    def finalizar(self):
        self.duracao=time.perf_counter()-self.inicio
        self.finalizado_em=datetime.now().astimezone().isoformat()

    def resultado(self):
        self.contagens['requisicoes_total']=sum(self.contagens[k] for k in ('requisicoes_navegador','requisicoes_documentos','requisicoes_api_externa','requisicoes_destinos'))
        return {**self.temporal(),'tempo_total_segundos':self.temporal()['duracao_segundos'],
                'releituras':self.releituras,'nota_tempos':'Tempos de releitura incluem preparação e extração; operações aninhadas não devem ser somadas.',
                'tempos_segundos':{k:round(v,6) for k,v in self.tempos.items()},
                'contagens':dict(self.contagens),
                'nota_requisicoes':'Eventos observados pelo Playwright e pedidos HTTP de metadados; não mede DNS/TLS nem todo tráfego interno do navegador.'}


# A prova do template inclui a árvore efetivamente carregada, classes, papéis,
# controles e destinos. Não deriva equivalência apenas do título ou da rota.
JS_TEMPLATE=r'''base => {
 const root=new URL(base), art=document.querySelector('main article');
 const els=[...(document.body?.querySelectorAll('*')||[])];
 const canon=u=>{try{const p=new URL(u,location.href);if(p.origin!==root.origin)return p.href;
   const r=root.pathname.replace(/\/$/,'');const path=p.pathname===r?'/':r&&p.pathname.startsWith(r+'/')?p.pathname.slice(r.length):p.pathname;
   return path+p.search;}catch(e){return u;}};
 const elegivel=!!art&&document.querySelectorAll('article').length===1&&
   !!art.querySelector('h1')&&!!art.querySelector('time[datetime]')&&
   /^\/(?:w\/|noticias\/|notícias\/|blog\/)/i.test(location.pathname)&&els.length<2000&&
   !document.querySelector('script,[onclick],[onload],form,[role="tab"],button,iframe,video,[loading="lazy"],[data-src]');
 const tree=els.map(e=>[e.tagName,e.getAttribute('role')||'',e.className?.baseVal??e.className,
   e.getAttribute('type')||'',e.hasAttribute('disabled'),e.getAttribute('aria-haspopup')||'',
   e.children.length,e.tagName==='A'?canon(e.href):'',e.tagName==='A'?e.textContent.trim():'',
   art?.contains(e)?'':(['P','H1','H2','H3','LI'].includes(e.tagName)?e.textContent.trim():'')]);
 const title=[...document.querySelectorAll('h1,h2,h3')].find(e=>/^not[ií]cias$/i.test(e.textContent.trim()));
 const sec=title?.closest('section')||(document.querySelectorAll('article').length===1?art:null);
 const editorialLink=e=>e.tagName==='A'&&/^\/(?:w\/|noticias\/|blog\/)/i.test(new URL(e.href,location.href).pathname);
 const shape=e=>[e.tagName,e.getAttribute('role')||'',e.getAttribute('type')||'',
   e.tagName==='A'?(editorialLink(e)?'@publicacao':canon(e.href)):'',
   ['A','BUTTON','SELECT','OPTION'].includes(e.tagName)?(editorialLink(e)?'@titulo':e.textContent.trim()):''];
 const section=sec?[sec,...sec.querySelectorAll('*')].map(shape):null;
 return {elegivel,arvore:tree,secao:section};
}'''


def assinatura(valor):
    return hashlib.sha256(json.dumps(valor,ensure_ascii=False,sort_keys=True).encode()).hexdigest()


def estrutura_funcional(valor):
    partes=valor.split('|')
    return tuple(partes[1:6]+partes[7:]) if len(partes)>=8 else valor


class Inteligencia:
    def __init__(self, metricas):
        self.metricas=metricas
        self.equivalencias=[];self.inconclusivos=[];self.omissoes=[]
        self.componentes=set();self.templates=Counter();self.estruturas=[];self.nao_pareadas=set()

    def comparar(self, a, b, pa, pb, nome_a, nome_b, base_a, base_b):
        from .paired import link_equivalente
        def chave(i):return i.tipo,normalizar(i.nome),normalizar(i.local)
        ga=defaultdict(list);gb=defaultdict(list)
        for i in a:ga[chave(i)].append(i)
        for i in b:gb[chave(i)].append(i)
        usados_a=set();usados_b=set();extras=[]
        for k in ga.keys() & gb.keys():
            if len(ga[k])!=1 or len(gb[k])!=1:continue
            ia,ib=ga[k][0],gb[k][0]
            destinos=(not ia.destino and not ib.destino) or (ia.destino and ib.destino and link_equivalente(ia.destino,ib.destino,base_a,base_b))
            estrutura=ia.estrutura and estrutura_funcional(ia.estrutura)==estrutura_funcional(ib.estrutura)
            funcao=ia.funcao and ia.funcao==ib.funcao
            estatico=ia.funcao not in ('button','select','tab','menuitem') and 'dinamico' not in ia.estrutura+ib.estrutura
            if destinos and estrutura and funcao and estatico:
                # Interações dinâmicas não são prova de equivalência funcional.
                fingerprint=assinatura([k,ia.estrutura,ia.funcao,ia.destino,ib.destino])
                reutilizado=fingerprint in self.componentes
                self.metricas.contagens['verificacoes_reaproveitadas']+=int(reutilizado)
                self.componentes.add(fingerprint)
                self.equivalencias.append({'tipo':ia.tipo,'elemento':ia.nome,'contexto':ia.local,
                    'url_a':pa.url,'url_b':pb.url,'destino_a':ia.destino,'destino_b':ib.destino,
                    'nivel':'DOM estático observado','funcionamento':'Não comprovado por esta equivalência',
                    'evidencias':['rótulo','contexto','papel','estrutura do elemento','destino'],
                    'reaproveitada':reutilizado})
                usados_a.add(id(ia));usados_b.add(id(ib))
            else:
                self.inconclusivos.append({'elemento':ia.nome,'url_a':pa.url,'url_b':pb.url,
                    'motivo':'Equivalência insuficiente: destino, estrutura ou função não coincidem; comparação normal mantida.'})
                if ia.funcao and ib.funcao and ia.funcao!=ib.funcao:
                    extras.append({'tipo':'Função','categoria':'Estrutura e função','elemento':ia.nome,
                        'presente_em':nome_a,'nao_identificado_em':nome_b,'url_presente':pa.url,
                        'url_comparada':pb.url,'local':ia.local,'caminho':' → '.join(pa.trilha),
                        'descricao':f'Papéis DOM diferentes: {ia.funcao} / {ib.funcao}. Requer revisão; não comprova defeito funcional.',
                        'situacao':'Papéis diferentes para revisão'})
        # Rótulos distintos exigem destino único equivalente, contexto, papel e estrutura.
        for ia in a:
            if id(ia) in usados_a or ia.tipo not in ('Opção','Documento') or not ia.destino or not ia.funcao or not ia.estrutura:continue
            if any(ib.tipo==ia.tipo and normalizar(ib.nome)==normalizar(ia.nome) and normalizar(ib.local)==normalizar(ia.local) for ib in b):continue
            candidatos=[ib for ib in b if id(ib) not in usados_b and ib.tipo==ia.tipo and
                normalizar(ib.nome)!=normalizar(ia.nome) and normalizar(ib.local)==normalizar(ia.local) and
                ib.funcao==ia.funcao and estrutura_funcional(ib.estrutura)==estrutura_funcional(ia.estrutura) and ib.destino and
                link_equivalente(ia.destino,ib.destino,base_a,base_b)]
            if len(candidatos)!=1:continue
            ib=candidatos[0]
            reversos=[other for other in a if id(other) not in usados_a and other.tipo==ia.tipo and other.destino and
                normalizar(other.local)==normalizar(ib.local) and other.funcao==ib.funcao and estrutura_funcional(other.estrutura)==estrutura_funcional(ib.estrutura) and
                link_equivalente(other.destino,ib.destino,base_a,base_b)]
            if len(reversos)!=1:continue
            usados_a.add(id(ia));usados_b.add(id(ib))
            extras.append({'tipo':'Rótulo','categoria':'Menus e opções','elemento':ia.nome+' / '+ib.nome,
                'texto_a':ia.nome,'texto_b':ib.nome,'presente_em':nome_a,'nao_identificado_em':nome_b,
                'destino_a':ia.destino,'destino_b':ib.destino,'url_presente':pa.url,'url_comparada':pb.url,
                'local':ia.local,'seletor':ia.seletor,'componente_id':ia.componente_id,'secao_id':ia.secao_id,
                'caminho':' → '.join(pa.trilha),'situacao':'Rótulos diferentes em controles correspondentes',
                'descricao':'Destino equivalente único, contexto, papel e estrutura coincidem, mas os rótulos diferem. Não comprova funcionamento.'})
        restante_a=[i for i in a if id(i) not in usados_a]
        restante_b=[i for i in b if id(i) not in usados_b]
        # O comparador legado usa presença global. Mesmo rótulo em outra região
        # não deve esconder uma diferença de contexto no modo inteligente.
        for ia in restante_a:
            candidatos=[ib for ib in restante_b if (ib.tipo,normalizar(ib.nome))==(ia.tipo,normalizar(ia.nome))]
            if len(candidatos)!=1:continue
            ib=candidatos[0]
            if normalizar(ia.local)==normalizar(ib.local):continue
            if ia.natureza==ib.natureza=='editorial':continue
            self.inconclusivos.append({'elemento':ia.nome,'url_a':pa.url,'url_b':pb.url,
                'motivo':'Mesmo rótulo com contextos diferentes; equivalência não comprovada.'})
            extras.append({'tipo':'Contexto','categoria':'Estrutura e função','elemento':ia.nome,
                'presente_em':nome_a,'nao_identificado_em':nome_b,'url_presente':pa.url,
                'url_comparada':pb.url,'local':ia.local,'caminho':' → '.join(pa.trilha),
                'descricao':f'O rótulo existe em contextos distintos: {ia.local} / {ib.local}. Não foi presumida equivalência; revisar a posição funcional.',
                'situacao':'Contextos diferentes para revisão'})
        return comparacao(restante_a,restante_b,pa,pb,nome_a,nome_b)+extras

    def sondas(self,page_a,page_b,base_a,base_b):
        with self.metricas.medir('verificacao_template'):
            return page_a.evaluate(JS_TEMPLATE,base_a),page_b.evaluate(JS_TEMPLATE,base_b)

    @staticmethod
    def chave_template(a,b):
        if a['elegivel'] and b['elegivel'] and a['arvore']==b['arvore']:
            return assinatura(a['arvore'])
        return None

    def sondar(self, page_a, page_b, base_a, base_b):
        return self.chave_template(*self.sondas(page_a,page_b,base_a,base_b))

    def preparar_par(self, page_a, page_b, ua, ub, trilha, log, base_a, base_b,
                     defasado, extrair, parar):
        # Ausência/alteração de seção não pode ser apagada por defasagem editorial.
        dados_a,dados_b=self.sondas(page_a,page_b,base_a,base_b)
        sa=dados_a['secao'];sb=dados_b['secao']
        if sa!=sb and (sa is not None or sb is not None):
            self.estruturas.append({'url_a':ua,'url_b':ub,'motivo':'Estrutura observada da seção editorial difere ou a seção não foi identificada em um ambiente. Revisão necessária; dados desatualizados não comprovam a causa.'})
        chave=self.chave_template(dados_a,dados_b)
        if defasado and chave and self.templates[chave]>=2 and not parar.is_set():
            # Confirma estabilidade local; não elimina navegação nem prova runtime.
            page_a.wait_for_timeout(250);page_b.wait_for_timeout(250)
            if self.sondar(page_a,page_b,base_a,base_b)==chave:
                pa=extrair(page_a,ua,trilha,log,metricas=self.metricas,profunda=False)
                pb=extrair(page_b,ub,trilha,log,metricas=self.metricas,profunda=False)
                self.omissoes.append({'categoria':'Notícia de template repetido','url_a':ua,'url_b':ub,
                    'motivo':'DOM estrutural conferido nesta página e em duas amostras profundas anteriores. Rolagem, abas e conteúdo tardio não inspecionados.',
                    'template':chave,'amostras_profundas':self.templates[chave]})
                self.metricas.contagens['preparacoes_profundas_evitadas']+=2
                return pa,pb
        pa=extrair(page_a,ua,trilha,log,metricas=self.metricas)
        pb=extrair(page_b,ub,trilha,log,metricas=self.metricas)
        if chave and pa.coleta.get('estavel') and pb.coleta.get('estavel') and not any(
                p.coleta.get('rolagem_limitada') for p in (pa,pb)):
            if self.sondar(page_a,page_b,base_a,base_b)==chave:self.templates[chave]+=1
        return pa,pb

    def resultado(self):
        return {'equivalencias_verificadas':self.equivalencias,
                'equivalencias_inconclusivas':self.inconclusivos,
                'inspecoes_profundas_omitidas':self.omissoes,'estruturas_editoriais_para_revisao':self.estruturas,
                'paginas_sem_par':sum(x.get('quantidade_paginas',1) for x in self.omissoes if x.get('categoria')=='Página sem par inequívoco'),
                'preparacoes_realmente_dispensadas':self.metricas.contagens['preparacoes_profundas_evitadas'],
                'nota_contagens':'Página sem par não é uma preparação evitada. Preparação com espera reduzida continua sendo inspeção profunda.',
                'quantidade_paginas_sem_inspecao_profunda':sum(x.get('quantidade_paginas',2) for x in self.omissoes),
                'nota':'Equivalência estática não comprova funcionamento nem conteúdo oculto. Notícias pareadas otimizadas ainda recebem navegação e inspeção estrutural; links sem par são listados como não inspecionados.'}
