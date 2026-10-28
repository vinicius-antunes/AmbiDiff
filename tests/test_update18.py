"""Fila dinâmica: portais fabricados e Chromium loopback, sem rede corporativa."""
import copy
import os
from contextlib import ExitStack
from pathlib import Path
import tempfile
import threading
from types import SimpleNamespace as NS
import unittest
from unittest.mock import patch

from ambidiff.core import Item,Pagina
from ambidiff import checkpoints as cp
from ambidiff.paired import executar_pareado
from test_intermat import A,B,PW


def opcao(nome,url,local='Conteúdo principal',**kw):
    return Item('Opção',nome,nome,destino=url,local=local,**kw)


def executar(grafo,*,parar=None,retomada=None,checkpoint=None,falhas=(),mimes=None,ao_log=None):
    parar=parar or threading.Event();abertas=[];lancamentos=[]
    def abrir(page,url):
        abertas.append(url);page.url=url
        if url in falhas:raise RuntimeError('HTTP 503 simulado')
        return NS(status=200,url=url,headers={'content-type':(mimes or {}).get(url,'text/html')})
    def extrair(page,url,trilha,log,**kw):
        itens=grafo(url)
        return Pagina(url,'','Portal sintético',itens,trilha,coleta={'estavel':True,'rolagem_limitada':False})
    pw=PW();original=pw.__enter__
    class Launcher:
        def __enter__(self):
            obj=original();launch=obj.chromium.launch
            def registrar(**kw):lancamentos.append(kw);return launch(**kw)
            obj.chromium.launch=registrar;return obj
        def __exit__(self,*args):pass
    with ExitStack() as stack:
        stack.enter_context(patch('playwright.sync_api.sync_playwright',return_value=Launcher()))
        stack.enter_context(patch('ambidiff.paired._abrir',side_effect=abrir))
        stack.enter_context(patch('ambidiff.paired._extrair_page',side_effect=extrair))
        stack.enter_context(patch('ambidiff.paired.comparar_visuais',return_value=([],[])))
        stack.enter_context(patch('ambidiff.adaptive.decidir_releitura',return_value=[]))
        stack.enter_context(patch('ambidiff.paired.time.sleep'))
        stack.enter_context(patch('ambidiff.documents.Documentos.comparar',return_value={'classificacao':'Verificação inconclusiva','motivo':'Metadados simulados'}))
        r=executar_pareado(A,B,'PRD','DES',parar,ao_log or (lambda _:None),lambda _:None,retomada=retomada,checkpoint=checkpoint)
    return r,abertas,lancamentos


def cadeia(n):
    def grafo(url):
        base=A if url.startswith(A) else B
        idx=int(url[len(base):] or 0)
        itens=[opcao('Próximo',base+str(idx+1))] if idx+1<n else []
        if idx==0 and base==A:itens.append(opcao('ÁUDIOS',base+'audio.pdf','Menu lateral'))
        return itens
    return grafo


class FilaDinamicaTests(unittest.TestCase):
    def test_teto_exato_mil_html_drena_fila_e_preserva_audios(self):
        r,abertas,_=executar(cadeia(1007))
        self.assertEqual(r['andamento']['pares_admitidos_html'],1000)
        self.assertEqual(r['andamento']['pares_comparados'],1000)
        self.assertEqual(len(abertas),2000);self.assertEqual(r['andamento']['pares_pendentes'],0)
        self.assertEqual(len(r['estados_pares']),1000)
        self.assertTrue(r['cobertura']['teto_atingido']);self.assertEqual(r['situacao_analise'],'parcial')
        self.assertTrue(any(d['elemento']=='ÁUDIOS' for d in r['divergencias']))

    def test_menos_de_mil_ciclo_e_urls_duplicadas_em_menus(self):
        def grafo(url):
            base=A if url.startswith(A) else B
            return [opcao('Área',base+'1','Menu lateral'),opcao('Outra opção',base+'1','Rodapé')] if url==base else [opcao('Voltar',base)]
        r,abertas,_=executar(grafo)
        self.assertEqual(r['andamento']['pares_comparados'],2);self.assertEqual(len(abertas),4)
        self.assertGreater(r['metricas']['contagens']['urls_duplicadas'],0)
        self.assertFalse(r['cobertura']['teto_atingido'])

    def test_prioridades_e_cotas_progressivas_sem_inanicao(self):
        from ambidiff.frontier import Fila,categoria
        nomes=['Menu','Serviço','Notícia','Legislação','Institucional','Arquivo histórico']
        pares=[(A+str(i),B+str(i),['Início',nome]) for i,nome in enumerate(nomes)]
        cats={tuple(p[:2]):categoria(p,'Menu lateral' if i==0 else '') for i,p in enumerate(pares)}
        self.assertEqual(list(cats.values()),list(range(6)))
        f=Fila(reversed(pares),dinamica=True,categorias=cats)
        self.assertEqual([f.popleft() for _ in range(6)],pares)
        f=Fila(dinamica=True)
        antigo=(A+'historico/9',B+'historico/9',['Início','Arquivo histórico']);f.append(antigo)
        vistos=[]
        for i in range(64):
            f.append((A+str(i),B+str(i),['Início','Serviço']));vistos.append(f.popleft())
            if antigo in vistos:break
        self.assertIn(antigo,vistos)

    def test_mil_noticias_nao_bloqueiam_servicos_e_representantes_nao_concluem_outros(self):
        stop=threading.Event();snaps=[];root_count=0
        def grafo(url):
            base=A if url.startswith(A) else B
            if url==base:
                return [opcao('Notícia '+str(i),base+'noticias/'+str(i),'Notícias') for i in range(1001)]+[opcao('Serviço',base+'servicos/2','Menu lateral')]
            return []
        def log(msg):
            if msg.startswith('[PRD/DES] 4 pares'):stop.set()
        r,abertas,_=executar(grafo,parar=stop,ao_log=log,checkpoint=lambda d:snaps.append(copy.deepcopy(d)))
        self.assertLess(abertas.index(A+'servicos/2'),abertas.index(A+'noticias/0'))
        self.assertEqual(r['andamento']['pares_comparados'],4)
        self.assertGreater(r['andamento']['referencias_candidatas'],0)
        self.assertGreater(r['andamento']['pares_pendentes'],0)
        self.assertFalse(any(p['estado']=='comparado' and p['par'][0] not in abertas for p in r['estados_pares']))
        cp.validar(snaps[-1]['retomada'])

    def test_exclusivas_ambos_sentidos_sem_inventar_contraparte(self):
        def grafo(url):
            base=A if url.startswith(A) else B
            return [opcao('Somente PRD' if base==A else 'Somente DES',base+'exclusiva','Menu lateral')] if url==base else []
        r,abertas,_=executar(grafo)
        self.assertEqual(r['andamento']['pares_comparados'],1)
        self.assertEqual(r['andamento']['pares_visitados'],3)
        self.assertEqual(r['cobertura']['paginas_exclusivas_inspecionadas'],2)
        self.assertEqual(set(abertas),{A,B,A+'exclusiva',B+'exclusiva'})
        self.assertEqual(sum(p['estado']=='sem_contraparte' for p in r['estados_pares']),2)

    def test_falhas_individuais_nao_contam_comparadas_nem_cancelam_demais(self):
        def grafo(url):
            base=A if url.startswith(A) else B
            return [opcao('Página '+str(i),base+str(i)) for i in range(1,23)] if url==base else []
        r,_,_=executar(grafo,falhas=[A+str(i) for i in range(1,21)])
        self.assertEqual(r['andamento']['pares_comparados'],3)
        self.assertEqual(r['andamento']['pares_com_falha'],20)
        self.assertEqual(r['andamento']['pares_pendentes'],0)
        self.assertEqual(len(r['estados_pares']),23)

    def test_midia_documentos_e_resposta_nao_html_nao_consumem_teto(self):
        def grafo(url):
            base=A if url.startswith(A) else B
            if url!=base:return []
            return [opcao('HTML',base+'1'),opcao('PDF',base+'manual.pdf'),opcao('Imagem',base+'foto.png'),opcao('CSS',base+'estilo.css'),opcao('Arquivo sem extensão',base+'2')]
        r,abertas,_=executar(grafo,mimes={A+'2':'application/pdf',B+'2':'application/pdf'})
        self.assertEqual(r['andamento']['pares_admitidos_html'],2)
        self.assertEqual(r['andamento']['pares_comparados'],2)
        self.assertEqual(sum(p['estado']=='nao_html' for p in r['estados_pares']),1)
        self.assertFalse(any(u.endswith(('.png','.pdf','.css')) for u in abertas))
        self.assertTrue(r['documentos_verificados'])

    def test_destino_divergente_interrompe_so_ramo_e_query_conteudo_preservada(self):
        def grafo(url):
            base=A if url.startswith(A) else B
            return [opcao('Destino diferente',base+('1' if base==A else '2')),opcao('Notícia 1',base+'3?c=1&e=2'),opcao('Notícia 2',base+'3?c=2&e=2')] if url==base else []
        r,abertas,_=executar(grafo)
        self.assertNotIn(A+'1',abertas);self.assertNotIn(B+'2',abertas)
        self.assertEqual(r['andamento']['pares_comparados'],3)
        self.assertTrue(any(d['tipo']=='Redirecionamento' for d in r['divergencias']))

    def test_retomada_proxima_teto_nao_reinicia_contagem_nem_repete_concluidos(self):
        stop=threading.Event();snaps=[]
        def log(msg):
            if msg.startswith('[PRD/DES] 995 pares'):stop.set()
        r,abertas,_=executar(cadeia(1007),parar=stop,ao_log=log,checkpoint=lambda d:snaps.append(copy.deepcopy(d)))
        self.assertEqual(r['andamento']['pares_comparados'],995)
        payload=snaps[-1]['retomada'];cp.validar(payload)
        r2,mais,_=executar(cadeia(1007),retomada=payload)
        self.assertEqual(r2['andamento']['pares_admitidos_html'],1000)
        self.assertEqual(r2['andamento']['pares_comparados'],1000)
        self.assertEqual(len(mais),10);self.assertFalse(set(mais)&set(abertas))
        self.assertEqual(r['divergencias'][0]['id'],r2['divergencias'][0]['id'])

    def test_retomada_legada_sem_perda_orcamento_nao_interrompe_dinamica(self):
        from ambidiff.strategy import Escopo
        e=Escopo('dinamica',20)
        with patch('ambidiff.strategy.time.perf_counter',return_value=e.inicio+7200):self.assertFalse(e.expirou())
        snaps=[];stop=threading.Event()
        def log(msg):
            if msg.startswith('[PRD/DES] 1 pares'):stop.set()
        executar(cadeia(4),parar=stop,ao_log=log,checkpoint=lambda d:snaps.append(copy.deepcopy(d)))
        estado=snaps[-1]['retomada']['estado']
        for k in ('politica_html','estados_pares'):estado.pop(k)
        estado['configuracao'].pop('estrategia');estado['configuracao'].pop('orcamento_minutos')
        r,abertas,_=executar(cadeia(4),retomada=cp.empacotar(estado))
        self.assertEqual(r['andamento']['pares_comparados'],4);self.assertNotIn(A,abertas)

    def test_browser_oculto_default_sequencial_e_contextos_independentes(self):
        with patch.dict(os.environ,{},clear=True):
            _,abertas,launch=executar(cadeia(2))
        self.assertTrue(launch[0]['headless']);self.assertEqual(abertas,[A,B,A+'1',B+'1'])

    def test_url_invalida_nao_destroi_restante_e_sem_navegacao_externa(self):
        def grafo(url):
            base=A if url.startswith(A) else B
            return [opcao('Inválido','https://['),opcao('Fora','https://externo.test/'),opcao('HTML',base+'1')] if url==base else []
        r,abertas,_=executar(grafo)
        self.assertEqual(r['andamento']['pares_comparados'],2)
        self.assertTrue(any('URL inválida' in p.get('motivo','') for p in r['pendencias']))
        self.assertNotIn('https://externo.test/',abertas)


class Evidencias18Tests(unittest.TestCase):
    def test_captura_reutiliza_destino_e_area_identicos_sem_compartilhar_contextos(self):
        from test_smart import navegador
        from playwright.sync_api import sync_playwright
        from ambidiff.paired import _salvar_evidencias
        from ambidiff.smart import Metricas
        from fixtures_perf import portais_perf
        with tempfile.TemporaryDirectory() as td,portais_perf(1) as (bases,reqs),sync_playwright() as pw:
            browser=navegador(pw)
            try:
                rows=[{'id':f'DIV-{i:04}','presente_em':'PRD','nao_identificado_em':'DES','url_presente':bases[0],'url_comparada':bases[1]} for i in range(1,4)]
                m=Metricas();_salvar_evidencias(browser,rows,td,threading.Event(),lambda _:None,metricas=m)
                self.assertEqual(m.contagens['capturas_geradas'],2)
                self.assertEqual(m.contagens['referencias_evidencias'],6)
                self.assertEqual(m.contagens['capturas_reutilizadas'],4)
                self.assertEqual(m.contagens['navegacoes_evidencias'],2)
                for r in rows:
                    self.assertEqual(len(r['evidencias']),2)
                    for path in r['evidencias'].values():self.assertTrue((Path(td).parent/path).exists())
            finally:browser.close()

class Recuperacao18Tests(unittest.TestCase):
    def test_editoriais_admitidos_continuam_sem_pausa_e_descobrem_menu_profundo(self):
        from test_update17 import portal_editorial
        from test_intermat import pipeline
        r,opened=pipeline(n=2,ajustar=portal_editorial)
        self.assertEqual(r['andamento']['pares_comparados'],303)
        self.assertEqual(r['cobertura']['pares_adiados_editoriais'],0)
        self.assertEqual(r['andamento']['pares_pendentes'],0)
        self.assertIn(A+'consulta/1000',opened)
        self.assertTrue(any(d['elemento']=='ÁUDIOS' for d in r['divergencias']))

    def test_checkpoint_recuperado_preserva_estado_terminal_e_evidencias(self):
        snaps=[];stop=threading.Event()
        def log(msg):
            if msg.startswith('[PRD/DES] 1 pares'):stop.set()
        executar(cadeia(3),parar=stop,ao_log=log,checkpoint=lambda d:snaps.append(copy.deepcopy(d)))
        snapshot=snaps[-1];estado=snapshot['retomada']['estado']
        estado['evidencias_preservadas']={'DIV-0001':{'evidencias':{'PRD':'evidencia_sintetica.png'}}}
        snapshot['retomada']=cp.empacotar(estado)
        r=cp.recuperar(snapshot)
        self.assertEqual(r['andamento']['pares_comparados'],1)
        self.assertEqual(r['estados_pares'],estado['estados_pares'])
        self.assertEqual(r['divergencias'][0]['evidencias'],{'PRD':'evidencia_sintetica.png'})
        for mutate in (lambda e:e.update(limite_html=10),lambda e:e['estados_pares'].append({'par':[A+'999',B+'999'],'estado':'comparado'})):
            bad=copy.deepcopy(estado);mutate(bad)
            with self.assertRaises(ValueError):cp.validar(cp.empacotar(bad))

    def test_conversao_checkpoint_legado_ja_acima_teto_preserva_admissoes(self):
        snaps=[];executar(cadeia(2),checkpoint=lambda d:snaps.append(copy.deepcopy(d)))
        e=snaps[0]['retomada']['estado'];e['configuracao']['estrategia']='profunda'
        e['fila']=[[A+str(i),B+str(i),['Início','Página '+str(i)]] for i in range(1002)]
        e['pares_enfileirados']=[p[:2] for p in e['fila']]
        e.pop('politica_html');e.pop('estados_pares')
        # Nenhum trabalho legado é descartado nem cria novas vagas na migração.
        stop=threading.Event();out=[]
        def log(msg):
            if msg.startswith('[PARES]'):stop.set()
        r,_,_=executar(cadeia(1002),retomada=cp.empacotar(e),parar=stop,ao_log=log,checkpoint=lambda d:out.append(copy.deepcopy(d)))
        # API web solicita explicitamente a política dinâmica; simulação direta
        # abaixo testa o mesmo parâmetro sem chamar portais reais.
        from test_intermat import pipeline
        r,_=pipeline(n=1002,retomada=cp.empacotar(e),estrategia='dinamica',orcamento_minutos=0)
        self.assertEqual(r['andamento']['pares_comparados'],1002)
        self.assertEqual(r['cobertura']['limite_pares_html'],1002)

class Tipos18Tests(unittest.TestCase):
    def test_pdf_em_um_lado_nao_oculta_falha_no_outro(self):
        r,_,_=executar(cadeia(1),falhas=[A],mimes={B:'application/pdf'})
        self.assertEqual(r['andamento']['pares_com_falha'],1)
        self.assertEqual(r['andamento']['pares_comparados'],0)
        self.assertEqual(r['estados_pares'][0]['estado'],'falha')

    def test_html_em_um_lado_reserva_vaga_e_fica_inconclusivo(self):
        r,_,_=executar(cadeia(1),mimes={B:'application/pdf'})
        self.assertEqual(r['andamento']['pares_admitidos_html'],1)
        self.assertEqual(r['andamento']['pares_comparados'],0)
        self.assertEqual(r['estados_pares'][0]['estado'],'inconclusivo')
        self.assertEqual(r['andamento']['pares_pendentes'],0)

class Worker18Tests(unittest.TestCase):
    def test_fila_drenada_no_teto_preserva_checkpoint_para_auditoria(self):
        from web import server
        r,_,_=executar(cadeia(2));r['cobertura'].update(teto_atingido=True,referencias_nao_admitidas=50)
        rid='20261027_120000_abcdef'
        params={'url_a':A,'url_b':B,'nome_a':'PRD','nome_b':'DES','site_nome':'Portal sintético','auditar_externos':False}
        with tempfile.TemporaryDirectory() as td,patch.object(server,'PASTA',Path(td)),patch.object(server,'HISTORY_PATH',Path(td)/'historico.json'),patch.dict(server.STATE,copy.deepcopy(server.STATE),clear=True),patch.object(server.PARAR,'is_set',return_value=False),patch.object(server,'executar',return_value=r),patch.object(server,'exportar'),patch.object(server,'exportar_diagnostico'):
            path=Path(td)/f'checkpoint_{rid}.json';path.write_text('{"auditoria":"sintética"}',encoding='utf-8')
            server.worker(params,rid)
            self.assertTrue(path.exists());self.assertNotEqual(server.STATE['status'],'erro')
            r['cobertura'].update(teto_atingido=False,referencias_nao_admitidas=0)
            server.worker(params,rid);self.assertFalse(path.exists())
